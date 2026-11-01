"""Run explicitly with HOSPITALOS_TEST_DATABASE_URL on an isolated localhost PostgreSQL DB."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.errors import ApiError
from app.hospitalos.request_routes import (
    CreateRequest,
    Decision,
    OrgAction,
    PublicCase,
    PublicEta,
    TaskAction,
    create_request,
    decide_request,
    public_tracking,
    run_operational_task,
    staff_inbox,
    suggest_operational_task,
    update_eta,
    withdraw_request,
)
from app.hospitalos.routes import (
    ResourceUpdate,
    public_facilities,
    staff_resources,
    update_resources,
)
from app.hospitalos.supervisor import SupervisorChoice
from app.security.auth import Principal

DATABASE_URL = os.environ.get("HOSPITALOS_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="Set HOSPITALOS_TEST_DATABASE_URL for isolated database test"
)
ORG = UUID("c562e817-bfae-4428-904d-15ac84b9acd7")
ADMIN = UUID("22222222-2222-4222-8222-222222222222")
OTHER_ORG = UUID("33333333-3333-4333-8333-333333333333")


async def scenario() -> None:
    assert urlsplit(DATABASE_URL).hostname in ("127.0.0.1", "localhost")
    engine = create_async_engine(DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings.model_construct(
        hospitalos_demo_enabled=True, hospitalos_response_seconds=120,
        hospitalos_hold_minutes=15,
    )
    try:
        async with factory() as session, session.begin():
            await session.execute(text("""truncate public.hospitalos_events,
                public.hospitalos_holds,public.hospitalos_requests,
                public.hospitalos_cases restart identity"""))
            await session.execute(text("""update public.hospitalos_facilities
                set ed_bays_ready=1,icu_beds_ready=1,verified_at=now()
                where slug='geeta-medicine'"""))
            await session.execute(text("delete from public.organization_users"))
            await session.execute(text("""insert into public.organization_users
                (organization_id,auth_user_id,role,active)
                values (:org,:actor,'ORG_ADMIN',true)"""),
                {"org": ORG, "actor": ADMIN})

        first = CreateRequest(case_id=uuid4(), tracking_token="a" * 43,
                              facility_slug="geeta-medicine", origin="CENTRAL_DELHI")
        async with factory() as session:
            created = await create_request(first, session, settings)
        assert created["status"] == "PENDING"
        async with factory() as session:
            replay = await create_request(first, session, settings)
        assert replay["id"] == created["id"]

        async with factory() as session:
            inbox = await staff_inbox(ORG, session, Principal(ADMIN, None), settings)
        assert len(inbox) == 1
        decision = Decision(organization_id=ORG, expected_version=created["version"],
                            decision_key=uuid4(), decision="ACCEPT",
                            arrival_note="Meet the demo receiving desk")
        async with factory() as session:
            accepted = await decide_request(created["id"], decision, session,
                                            Principal(ADMIN, None), settings)
        assert accepted["status"] == "ACCEPTED"
        assert accepted["hold_state"] == "ACTIVE"
        assert accepted["arrival_note"] == "Meet the demo receiving desk"
        async with factory() as session:
            eta_changed = await update_eta(PublicEta(case_id=first.case_id,
                tracking_token=first.tracking_token, eta_minutes=12), session, settings)
        assert eta_changed["eta_minutes"] == 12
        async with factory() as session:
            replayed = await decide_request(created["id"], decision, session,
                                            Principal(ADMIN, None), settings)
        assert replayed["id"] == accepted["id"]

        second = CreateRequest(case_id=uuid4(), tracking_token="b" * 43,
                               facility_slug="geeta-medicine", origin="CENTRAL_DELHI")
        async with factory() as session:
            second_created = await create_request(second, session, settings)
        async with factory() as session:
            conflict = await decide_request(
                second_created["id"],
                Decision(organization_id=ORG, expected_version=1,
                         decision_key=uuid4(), decision="ACCEPT"),
                session, Principal(ADMIN, None), settings,
            )
        assert conflict["status"] == "HOLD_CONFLICT"
        assert any(event["event_type"] == "HOLD_CONFLICT" for event in conflict["events"])

        async def fake_choice(*_args: object, **_kwargs: object) -> SupervisorChoice:
            return SupervisorChoice(kind="MATCHING_REVIEW")

        with patch("app.hospitalos.request_routes.choose_task", new=fake_choice):
            async with factory() as session:
                suggestion = await suggest_operational_task(
                    second_created["id"], OrgAction(organization_id=ORG),
                    session, Principal(ADMIN, None), settings,
                )
        assert any(event["event_type"] == "AGENT_TASK_CREATED" for event in suggestion["events"])

        async with factory() as session:
            task = await run_operational_task(
                second_created["id"], TaskAction(organization_id=ORG, kind="MATCHING_REVIEW"),
                session, Principal(ADMIN, None), settings,
            )
        assert any(event["event_type"] == "TASK_COMPLETED" for event in task["events"])

        async with factory() as session:
            with pytest.raises(ApiError) as forbidden:
                await decide_request(second_created["id"],
                                     Decision(organization_id=OTHER_ORG, expected_version=1,
                                              decision_key=uuid4(), decision="DECLINE"),
                                     session, Principal(ADMIN, None), settings)
        assert forbidden.value.status_code == 403

        async with factory() as session:
            withdrawn = await withdraw_request(PublicCase(case_id=first.case_id,
                tracking_token=first.tracking_token), session, settings)
        assert withdrawn["status"] == "WITHDRAWN"
        assert withdrawn["hold_state"] == "RELEASED"

        third = CreateRequest(case_id=uuid4(), tracking_token="c" * 43,
                              facility_slug="geeta-medicine", origin="CENTRAL_DELHI")
        async with factory() as session:
            await create_request(third, session, settings)
        async with factory() as session, session.begin():
            await session.execute(text("""update public.hospitalos_requests
                set deadline_at=:past where case_id=:case_id"""),
                {"past": datetime.now(UTC) - timedelta(seconds=1), "case_id": third.case_id})
        async with factory() as session:
            expired = await public_tracking(PublicCase(case_id=third.case_id,
                tracking_token=third.tracking_token), session, settings)
        assert expired["status"] == "EXPIRED"
        async with factory() as session:
            with pytest.raises(ApiError) as expired_eta:
                await update_eta(PublicEta(case_id=third.case_id,
                    tracking_token=third.tracking_token, eta_minutes=10), session, settings)
        assert expired_eta.value.status_code == 409
        async with factory() as session:
            with pytest.raises(ApiError) as late:
                await decide_request(
                    expired["id"], Decision(organization_id=ORG, expected_version=1,
                        decision_key=uuid4(), decision="ACCEPT"),
                    session, Principal(ADMIN, None), settings,
                )
        assert late.value.status_code == 409
        async with factory() as session:
            with pytest.raises(ApiError) as wrong_token:
                await public_tracking(PublicCase(case_id=third.case_id,
                    tracking_token="z" * 43), session, settings)
        assert wrong_token.value.status_code == 404

        fourth = CreateRequest(case_id=uuid4(), tracking_token="d" * 43,
                               facility_slug="geeta-medicine", origin="CENTRAL_DELHI")
        async with factory() as session:
            fourth_created = await create_request(fourth, session, settings)
        async with factory() as session:
            declined = await decide_request(
                fourth_created["id"], Decision(organization_id=ORG, expected_version=1,
                    decision_key=uuid4(), decision="DECLINE"),
                session, Principal(ADMIN, None), settings,
            )
        assert declined["status"] == "DECLINED"

        fifth = CreateRequest(case_id=uuid4(), tracking_token="e" * 43,
                              facility_slug="geeta-medicine", origin="CENTRAL_DELHI")
        async with factory() as session:
            fifth_created = await create_request(fifth, session, settings)
        async with factory() as session, session.begin():
            await session.execute(text("""update public.hospitalos_facilities
                set verified_at=now()-interval '25 hours' where slug='geeta-medicine'"""))
        async with factory() as session:
            stale = await decide_request(
                fifth_created["id"], Decision(organization_id=ORG, expected_version=1,
                    decision_key=uuid4(), decision="ACCEPT"),
                session, Principal(ADMIN, None), settings,
            )
        assert stale["status"] == "PENDING"
        assert stale["events"][-1]["detail"]["ready"] is False

        async with factory() as session:
            resources = await staff_resources(ORG, session, Principal(ADMIN, None), settings)
        assert len(resources) == 1
        current = resources[0]
        async with factory() as session:
            updated = await update_resources(current["id"], ResourceUpdate(
                organization_id=ORG, expected_version=current["version"],
                emergency_open=True, ed_bays_ready=0, icu_beds_ready=1,
                ventilators_ready=1, ct_available=True, trauma_available=True,
                pediatric_available=False, obstetric_available=False,
            ), session, Principal(ADMIN, None), settings)
        assert updated["ed_bays_ready"] == 0
        async with factory() as session:
            listing = await public_facilities("CENTRAL_DELHI", "ANY", "GENERAL", session, settings)
        geeta = next(item for item in listing["facilities"] if item["slug"] == "geeta-medicine")
        assert geeta["recommended"] is False
        assert "NO_READY_RECEIVING_SPACE" in geeta["reason_codes"]

        async with factory() as session, session.begin():
            await session.execute(text("""update public.hospitalos_facilities
                set ed_bays_ready=1,verified_at=now() where slug='geeta-medicine'"""))
        concurrent_cases = [
            CreateRequest(case_id=uuid4(), tracking_token=char * 43,
                          facility_slug="geeta-medicine", origin="CENTRAL_DELHI")
            for char in ("f", "g")
        ]
        created_pair = []
        for payload in concurrent_cases:
            async with factory() as session:
                created_pair.append(await create_request(payload, session, settings))

        async def accept_one(request: dict[str, object]) -> str:
            async with factory() as session:
                result = await decide_request(
                    request["id"], Decision(organization_id=ORG, expected_version=1,
                        decision_key=uuid4(), decision="ACCEPT"),
                    session, Principal(ADMIN, None), settings,
                )
            return result["status"]

        outcomes = await asyncio.gather(*(accept_one(item) for item in created_pair))
        assert sorted(outcomes) == ["ACCEPTED", "HOLD_CONFLICT"]
    finally:
        await engine.dispose()


def test_request_hold_conflict_and_expiry_on_isolated_database() -> None:
    asyncio.run(scenario())
