import asyncio
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_G2_INTEGRATION_TESTS") != "1",
    reason="set RUN_G2_INTEGRATION_TESTS=1 to exercise the configured Supabase database",
)


@dataclass(frozen=True)
class Seed:
    auth_user_id: UUID
    organization_id: UUID
    doctor_id: UUID
    assignment_id: UUID
    contact_id: UUID
    phone_id: UUID
    patient_id: UUID
    token_session_id: UUID
    exact_session_id: UUID
    exact_slot_id: UUID


async def _set_identity(session: AsyncSession, user_id: UUID) -> None:
    await session.execute(
        text("select set_config('request.jwt.claim.sub', :user_id, true)"),
        {"user_id": str(user_id)},
    )


async def _seed(session: AsyncSession, *, token_capacity: int = 30) -> Seed:
    auth_user_id = (
        await session.execute(text("select id from auth.users order by created_at limit 1"))
    ).scalar_one_or_none()
    if auth_user_id is None:
        pytest.skip("the configured Supabase project has no authenticated test user")

    organization_id = uuid4()
    location_id = uuid4()
    department_id = uuid4()
    doctor_id = uuid4()
    assignment_id = uuid4()
    contact_id = uuid4()
    phone_id = uuid4()
    patient_id = uuid4()
    token_session_id = uuid4()
    exact_session_id = uuid4()
    exact_slot_id = uuid4()
    starts_at = datetime.now(UTC) + timedelta(days=30)

    await session.execute(
        text(
            "insert into public.organizations "
            "(id,name,organization_type,timezone,status) "
            "values (:id,:name,'CLINIC','Asia/Kolkata','ACTIVE')"
        ),
        {"id": organization_id, "name": f"G2 Test {organization_id}"},
    )
    await session.execute(
        text(
            "insert into public.organization_users (organization_id,auth_user_id,role) "
            "values (:org,:user,'ORG_ADMIN')"
        ),
        {"org": organization_id, "user": auth_user_id},
    )
    await _set_identity(session, auth_user_id)
    await session.execute(
        text(
            "insert into public.locations (id,organization_id,name,timezone) "
            "values (:id,:org,'Test Branch','Asia/Kolkata')"
        ),
        {"id": location_id, "org": organization_id},
    )
    await session.execute(
        text(
            "insert into public.departments (id,organization_id,name) "
            "values (:id,:org,'G2 Medicine')"
        ),
        {"id": department_id, "org": organization_id},
    )
    await session.execute(
        text("insert into public.doctors (id,canonical_name) values (:id,'Dr G2 Test')"),
        {"id": doctor_id},
    )
    await session.execute(
        text(
            "insert into public.doctor_assignments "
            "(id,organization_id,doctor_id,location_id,department_id,"
            "display_name,fee_minor,currency) "
            "values (:id,:org,:doctor,:location,:department,'Dr G2 Test',1000,'INR')"
        ),
        {
            "id": assignment_id,
            "org": organization_id,
            "doctor": doctor_id,
            "location": location_id,
            "department": department_id,
        },
    )
    await session.execute(
        text(
            "insert into public.contacts (id,organization_id,display_name) "
            "values (:id,:org,'G2 Caller')"
        ),
        {"id": contact_id, "org": organization_id},
    )
    await session.execute(
        text(
            "insert into public.contact_phones "
            "(id,organization_id,contact_id,phone_e164) "
            "values (:id,:org,:contact,'+919800000000')"
        ),
        {"id": phone_id, "org": organization_id, "contact": contact_id},
    )
    await session.execute(
        text(
            "insert into public.patients (id,organization_id,display_name) "
            "values (:id,:org,'G2 Patient')"
        ),
        {"id": patient_id, "org": organization_id},
    )
    await session.execute(
        text(
            "insert into public.patient_contacts "
            "(organization_id,patient_id,contact_id,relationship,recorded_by_auth_user_id) "
            "values (:org,:patient,:contact,'SELF',:user)"
        ),
        {
            "org": organization_id,
            "patient": patient_id,
            "contact": contact_id,
            "user": auth_user_id,
        },
    )
    await session.execute(
        text(
            "insert into public.appointment_sessions "
            "(id,organization_id,assignment_id,doctor_id,starts_at,ends_at,timezone,"
            "booking_mode,max_patients) "
            "values (:id,:org,:assignment,:doctor,:starts,:ends,'Asia/Kolkata',"
            "'SESSION_TOKEN',:capacity)"
        ),
        {
            "id": token_session_id,
            "org": organization_id,
            "assignment": assignment_id,
            "doctor": doctor_id,
            "starts": starts_at,
            "ends": starts_at + timedelta(hours=2),
            "capacity": token_capacity,
        },
    )
    exact_starts_at = starts_at + timedelta(days=1)
    await session.execute(
        text(
            "insert into public.appointment_sessions "
            "(id,organization_id,assignment_id,doctor_id,starts_at,ends_at,timezone,"
            "booking_mode,slot_minutes) "
            "values (:id,:org,:assignment,:doctor,:starts,:ends,'Asia/Kolkata',"
            "'EXACT_TIME',20)"
        ),
        {
            "id": exact_session_id,
            "org": organization_id,
            "assignment": assignment_id,
            "doctor": doctor_id,
            "starts": exact_starts_at,
            "ends": exact_starts_at + timedelta(hours=2),
        },
    )
    await session.execute(
        text(
            "insert into public.appointment_slots "
            "(id,organization_id,session_id,assignment_id,starts_at,ends_at) "
            "values (:id,:org,:session,:assignment,:starts,:ends)"
        ),
        {
            "id": exact_slot_id,
            "org": organization_id,
            "session": exact_session_id,
            "assignment": assignment_id,
            "starts": exact_starts_at,
            "ends": exact_starts_at + timedelta(minutes=20),
        },
    )
    return Seed(
        auth_user_id=auth_user_id,
        organization_id=organization_id,
        doctor_id=doctor_id,
        assignment_id=assignment_id,
        contact_id=contact_id,
        phone_id=phone_id,
        patient_id=patient_id,
        token_session_id=token_session_id,
        exact_session_id=exact_session_id,
        exact_slot_id=exact_slot_id,
    )


async def _hold(
    session: AsyncSession,
    seed: Seed,
    *,
    session_id: UUID,
    slot_id: UUID | None,
    key: str,
    request_hash: str | None = None,
    source: str = "STAFF",
) -> dict[str, object]:
    result = await session.execute(
        text(
            "select * from public.create_simulated_appointment_hold("
            ":org,:patient,:contact,:phone,:assignment,:session,:slot,"
            ":source,:key,:request_hash,true,'en',:consent_channel,600)"
        ),
        {
            "org": seed.organization_id,
            "patient": seed.patient_id,
            "contact": seed.contact_id,
            "phone": seed.phone_id,
            "assignment": seed.assignment_id,
            "session": session_id,
            "slot": slot_id,
            "key": key,
            "request_hash": request_hash or (key.encode().hex() + "0" * 32)[:64],
            "source": source,
            "consent_channel": "STAFF_UI" if source in {"STAFF", "WALK_IN"} else source,
        },
    )
    return dict(result.mappings().one())


async def _confirm(session: AsyncSession, seed: Seed, appointment_id: UUID) -> dict[str, object]:
    result = await session.execute(
        text("select * from public.confirm_simulated_appointment(:org,:appointment)"),
        {"org": seed.organization_id, "appointment": appointment_id},
    )
    return dict(result.mappings().one())


@pytest_asyncio.fixture
async def transactional_seed() -> AsyncIterator[tuple[AsyncSession, Seed]]:
    database_url = get_settings().database_url
    if not database_url:
        pytest.skip("DATABASE_URL is not configured")
    engine = create_async_engine(database_url, pool_pre_ping=True)
    connection = await engine.connect()
    transaction = await connection.begin()
    session = AsyncSession(bind=connection, expire_on_commit=False)
    try:
        seed = await _seed(session)
        yield session, seed
    finally:
        await transaction.rollback()
        await session.close()
        await connection.close()
        await engine.dispose()


async def test_hold_replay_exact_slot_and_confirmation_are_idempotent(
    transactional_seed: tuple[AsyncSession, Seed],
) -> None:
    session, seed = transactional_seed
    key = f"exact-replay-{uuid4()}"
    first = await _hold(
        session,
        seed,
        session_id=seed.exact_session_id,
        slot_id=seed.exact_slot_id,
        key=key,
    )
    replay = await _hold(
        session,
        seed,
        session_id=seed.exact_session_id,
        slot_id=seed.exact_slot_id,
        key=key,
    )
    assert replay["appointment_id"] == first["appointment_id"]

    with pytest.raises(DBAPIError):
        async with session.begin_nested():
            await _hold(
                session,
                seed,
                session_id=seed.exact_session_id,
                slot_id=seed.exact_slot_id,
                key=key,
                request_hash="d" * 64,
            )

    confirmed = await _confirm(session, seed, first["appointment_id"])  # type: ignore[arg-type]
    confirmed_replay = await _confirm(
        session, seed, first["appointment_id"]  # type: ignore[arg-type]
    )
    assert confirmed_replay == confirmed
    assert confirmed["token_number"] is None

    with pytest.raises(DBAPIError):
        async with session.begin_nested():
            await _hold(
                session,
                seed,
                session_id=seed.exact_session_id,
                slot_id=seed.exact_slot_id,
                key=f"exact-conflict-{uuid4()}",
            )

    outbox_count = (
        await session.execute(
            text(
                "select count(*) from public.outbox_jobs "
                "where organization_id=:org and aggregate_id=:appointment "
                "and job_type='APPOINTMENT_CONFIRMED'"
            ),
            {"org": seed.organization_id, "appointment": first["appointment_id"]},
        )
    ).scalar_one()
    assert outbox_count == 1


async def test_expired_hold_releases_slot_and_fails_simulated_payment(
    transactional_seed: tuple[AsyncSession, Seed],
) -> None:
    session, seed = transactional_seed
    expired = await _hold(
        session,
        seed,
        session_id=seed.exact_session_id,
        slot_id=seed.exact_slot_id,
        key=f"expiry-{uuid4()}",
    )
    await session.execute(
        text(
            "update public.appointments set hold_expires_at=now()-interval '1 second' "
            "where organization_id=:org and id=:appointment"
        ),
        {"org": seed.organization_id, "appointment": expired["appointment_id"]},
    )
    replacement = await _hold(
        session,
        seed,
        session_id=seed.exact_session_id,
        slot_id=seed.exact_slot_id,
        key=f"expiry-replacement-{uuid4()}",
    )
    assert replacement["appointment_id"] != expired["appointment_id"]
    old_status, payment_status = (
        await session.execute(
            text(
                "select appointment.status, payment.status "
                "from public.appointments appointment "
                "join public.payment_attempts payment "
                "on payment.organization_id=appointment.organization_id "
                "and payment.appointment_id=appointment.id "
                "where appointment.organization_id=:org and appointment.id=:appointment"
            ),
            {"org": seed.organization_id, "appointment": expired["appointment_id"]},
        )
    ).one()
    assert old_status == "EXPIRED"
    assert payment_status == "SIMULATED_FAILURE"


async def test_token_cancellation_frees_capacity_without_reusing_numbers(
    transactional_seed: tuple[AsyncSession, Seed],
) -> None:
    session, seed = transactional_seed
    await session.execute(
        text(
            "update public.appointment_sessions set max_patients=2 "
            "where organization_id=:org and id=:session"
        ),
        {"org": seed.organization_id, "session": seed.token_session_id},
    )
    first = await _hold(
        session,
        seed,
        session_id=seed.token_session_id,
        slot_id=None,
        key=f"token-one-{uuid4()}",
    )
    second = await _hold(
        session,
        seed,
        session_id=seed.token_session_id,
        slot_id=None,
        key=f"token-two-{uuid4()}",
    )
    first_confirmed = await _confirm(session, seed, first["appointment_id"])  # type: ignore[arg-type]
    second_confirmed = await _confirm(session, seed, second["appointment_id"])  # type: ignore[arg-type]
    assert [first_confirmed["token_number"], second_confirmed["token_number"]] == [1, 2]

    await session.execute(
        text("select * from public.cancel_appointment(:org,:appointment,2,'G2 test')"),
        {"org": seed.organization_id, "appointment": first["appointment_id"]},
    )
    third = await _hold(
        session,
        seed,
        session_id=seed.token_session_id,
        slot_id=None,
        key=f"token-three-{uuid4()}",
    )
    third_confirmed = await _confirm(session, seed, third["appointment_id"])  # type: ignore[arg-type]
    assert third_confirmed["token_number"] == 3


async def test_failed_reschedule_preserves_original_appointment(
    transactional_seed: tuple[AsyncSession, Seed],
) -> None:
    session, seed = transactional_seed
    original = await _hold(
        session,
        seed,
        session_id=seed.exact_session_id,
        slot_id=seed.exact_slot_id,
        key=f"reschedule-original-{uuid4()}",
    )
    await _confirm(session, seed, original["appointment_id"])  # type: ignore[arg-type]
    await session.execute(
        text(
            "update public.appointment_sessions set max_patients=1 "
            "where organization_id=:org and id=:session"
        ),
        {"org": seed.organization_id, "session": seed.token_session_id},
    )
    target = await _hold(
        session,
        seed,
        session_id=seed.token_session_id,
        slot_id=None,
        key=f"reschedule-target-{uuid4()}",
    )
    await _confirm(session, seed, target["appointment_id"])  # type: ignore[arg-type]

    with pytest.raises(DBAPIError):
        async with session.begin_nested():
            await session.execute(
                text(
                    "select * from public.reschedule_appointment("
                    ":org,:appointment,2,:new_session,null)"
                ),
                {
                    "org": seed.organization_id,
                    "appointment": original["appointment_id"],
                    "new_session": seed.token_session_id,
                },
            )

    original_state = (
        await session.execute(
            text(
                "select status, version from public.appointments "
                "where organization_id=:org and id=:appointment"
            ),
            {"org": seed.organization_id, "appointment": original["appointment_id"]},
        )
    ).one()
    assert original_state == ("CONFIRMED", 2)


async def test_successful_reschedule_refreshes_snapshots_and_payment_visibility(
    transactional_seed: tuple[AsyncSession, Seed],
) -> None:
    session, seed = transactional_seed
    original = await _hold(
        session, seed, session_id=seed.exact_session_id, slot_id=seed.exact_slot_id,
        key=f"reschedule-snapshots-{uuid4()}",
    )
    await _confirm(session, seed, original["appointment_id"])  # type: ignore[arg-type]
    params = {"org": seed.organization_id, "appointment": original["appointment_id"],
              "assignment": seed.assignment_id, "target": seed.token_session_id}
    prior = (await session.execute(text(
        "select booking_reference, quote_snapshot, consent_snapshot from public.appointments "
        "where organization_id=:org and id=:appointment"
    ), params)).mappings().one()
    payment = (await session.execute(text(
        "select provider,mode,payment_method,amount_minor,currency,status from public.payment_attempts "
        "where organization_id=:org and appointment_id=:appointment order by created_at desc limit 1"
    ), params)).mappings().one()
    await session.execute(text(
        "update public.doctor_assignments set display_name='Dr Destination' "
        "where organization_id=:org and id=:assignment"
    ), params)
    await session.execute(text(
        "update public.locations set name='Destination Branch' "
        "where organization_id=:org and id=(select location_id from public.doctor_assignments "
        "where organization_id=:org and id=:assignment)"
    ), params)
    replacement = (await session.execute(text(
        "select * from public.reschedule_appointment(:org,:appointment,2,:target,null)"
    ), params)).mappings().one()
    new_params = {"org": seed.organization_id, "appointment": replacement["replacement_appointment_id"]}
    new = (await session.execute(text(
        "select status, session_id, supersedes_appointment_id, quote_snapshot, consent_snapshot "
        "from public.appointments where organization_id=:org and id=:appointment"
    ), new_params)).mappings().one()
    target = (await session.execute(text(
        "select starts_at, ends_at from public.appointment_sessions where organization_id=:org and id=:target"
    ), params)).mappings().one()
    assert new["status"] == "CONFIRMED"
    assert new["session_id"] == seed.token_session_id
    assert new["supersedes_appointment_id"] == original["appointment_id"]
    quote = new["quote_snapshot"]
    assert quote["doctor_name"] == "Dr Destination"
    assert quote["location_name"] == "Destination Branch"
    assert datetime.fromisoformat(quote["starts_at"]) == target["starts_at"]
    assert datetime.fromisoformat(quote["ends_at"]) == target["ends_at"]
    assert quote["fee_minor"] == 1000 and quote["currency"] == "INR"
    assert quote["quote_version"] != prior["quote_snapshot"]["quote_version"]
    assert new["consent_snapshot"]["rescheduled_from_reference"] == prior["booking_reference"]
    assert new["consent_snapshot"].get("rescheduled_at")
    assert all(new["consent_snapshot"][key] == value for key, value in prior["consent_snapshot"].items())
    copied = (await session.execute(text(
        "select provider,mode,payment_method,amount_minor,currency,status from public.payment_attempts "
        "where organization_id=:org and appointment_id=:appointment"
    ), new_params)).mappings().one()
    assert dict(copied) == dict(payment)
    old = (await session.execute(text(
        "select status, version, quote_snapshot from public.appointments where organization_id=:org and id=:appointment"
    ), params)).mappings().one()
    assert old["status"] == "RESCHEDULED" and old["version"] == 3
    assert old["quote_snapshot"] == prior["quote_snapshot"]


@pytest.mark.parametrize("invalid_destination,expected_error", [
    ("past", "replacement session is not bookable"),
    ("cutoff", "replacement session is not bookable"),
    ("inactive_assignment", "replacement doctor assignment is inactive"),
    ("inactive_location", "replacement location is inactive"),
    ("fee", "fee change requires staff review"),
    ("currency", "fee or currency change requires a new staff-reviewed booking"),
])
async def test_reschedule_rejects_invalid_destination_without_partial_writes(
    transactional_seed: tuple[AsyncSession, Seed], invalid_destination: str, expected_error: str,
) -> None:
    session, seed = transactional_seed
    original = await _hold(
        session, seed, session_id=seed.exact_session_id, slot_id=seed.exact_slot_id,
        key=f"reschedule-reject-{uuid4()}",
    )
    await _confirm(session, seed, original["appointment_id"])  # type: ignore[arg-type]
    params = {"org": seed.organization_id, "appointment": original["appointment_id"],
              "assignment": seed.assignment_id, "target": seed.token_session_id}
    queries = {
        "past": "update public.appointment_sessions set starts_at=now()-interval '2 hours', ends_at=now()-interval '1 hour' where organization_id=:org and id=:target",
        "cutoff": "update public.appointment_sessions set starts_at=now()+interval '5 minutes', ends_at=now()+interval '2 hours', booking_cutoff_minutes=10 where organization_id=:org and id=:target",
        "inactive_assignment": "update public.doctor_assignments set active=false where organization_id=:org and id=:assignment",
        "inactive_location": "update public.locations set active=false where organization_id=:org and id=(select location_id from public.doctor_assignments where organization_id=:org and id=:assignment)",
        "fee": "update public.doctor_assignments set fee_minor=2000 where organization_id=:org and id=:assignment",
        "currency": "update public.doctor_assignments set currency='USD' where organization_id=:org and id=:assignment",
    }
    await session.execute(text(queries[invalid_destination]), params)
    before_token = (await session.execute(text(
        "select next_token from public.appointment_sessions where organization_id=:org and id=:target"
    ), params)).scalar_one()
    with pytest.raises(DBAPIError, match=expected_error):
        async with session.begin_nested():
            await session.execute(text(
                "select * from public.reschedule_appointment(:org,:appointment,2,:target,null)"
            ), params)
    original_state = (await session.execute(text(
        "select status,version from public.appointments where organization_id=:org and id=:appointment"
    ), params)).one()
    assert original_state == ("CONFIRMED", 2)
    assert (await session.execute(text(
        "select count(*) from public.appointments where organization_id=:org and supersedes_appointment_id=:appointment"
    ), params)).scalar_one() == 0
    assert (await session.execute(text(
        "select next_token from public.appointment_sessions where organization_id=:org and id=:target"
    ), params)).scalar_one() == before_token
    assert (await session.execute(text(
        "select count(*) from public.outbox_jobs where organization_id=:org and job_type='APPOINTMENT_RESCHEDULED'"
    ), params)).scalar_one() == 0


async def test_verification_attempts_lock_and_success_rejects_replay(
    transactional_seed: tuple[AsyncSession, Seed],
) -> None:
    session, seed = transactional_seed
    issued = (
        await session.execute(
            text(
                "select * from public.issue_verification_challenge("
                ":org,:phone,1,:digest,null,300)"
            ),
            {"org": seed.organization_id, "phone": seed.phone_id, "digest": "a" * 64},
        )
    ).mappings().one()
    for expected_remaining in (4, 3, 2, 1):
        attempt = (
            await session.execute(
                text(
                    "select * from public.verify_verification_challenge("
                    ":org,:challenge,:digest,600)"
                ),
                {
                    "org": seed.organization_id,
                    "challenge": issued["challenge_id"],
                    "digest": "b" * 64,
                },
            )
        ).mappings().one()
        assert attempt["verified"] is False
        assert attempt["attempts_remaining"] == expected_remaining
    locked = (
        await session.execute(
            text(
                "select * from public.verify_verification_challenge("
                ":org,:challenge,:digest,600)"
            ),
            {
                "org": seed.organization_id,
                "challenge": issued["challenge_id"],
                "digest": "b" * 64,
            },
        )
    ).mappings().one()
    assert locked["challenge_status"] == "LOCKED"

    successful_issue = (
        await session.execute(
            text(
                "select * from public.issue_verification_challenge("
                ":org,:phone,1,:digest,null,300)"
            ),
            {"org": seed.organization_id, "phone": seed.phone_id, "digest": "c" * 64},
        )
    ).mappings().one()
    success = (
        await session.execute(
            text(
                "select * from public.verify_verification_challenge("
                ":org,:challenge,:digest,600)"
            ),
            {
                "org": seed.organization_id,
                "challenge": successful_issue["challenge_id"],
                "digest": "c" * 64,
            },
        )
    ).mappings().one()
    replay = (
        await session.execute(
            text(
                "select * from public.verify_verification_challenge("
                ":org,:challenge,:digest,600)"
            ),
            {
                "org": seed.organization_id,
                "challenge": successful_issue["challenge_id"],
                "digest": "c" * 64,
            },
        )
    ).mappings().one()
    assert success["verified"] is True
    assert success["challenge_status"] == "VERIFIED"
    assert replay["verified"] is False


async def test_tenant_and_doctor_session_invariants_fail_closed(
    transactional_seed: tuple[AsyncSession, Seed],
) -> None:
    session, seed = transactional_seed
    other = await _seed(session)

    with pytest.raises(DBAPIError):
        async with session.begin_nested():
            await session.execute(
                text(
                    "select * from public.create_simulated_appointment_hold("
                    ":org,:patient,:contact,:phone,:assignment,:session,null,"
                    "'STAFF',:key,:request_hash,true,'en','STAFF_UI',600)"
                ),
                {
                    "org": seed.organization_id,
                    "patient": seed.patient_id,
                    "contact": seed.contact_id,
                    "phone": seed.phone_id,
                    "assignment": other.assignment_id,
                    "session": other.token_session_id,
                    "key": f"cross-tenant-{uuid4()}",
                    "request_hash": "e" * 64,
                },
            )

    existing_session = (
        await session.execute(
            text(
                "select doctor_id, starts_at, ends_at from public.appointment_sessions "
                "where organization_id=:org and id=:session"
            ),
            {"org": seed.organization_id, "session": seed.token_session_id},
        )
    ).mappings().one()
    with pytest.raises(DBAPIError):
        async with session.begin_nested():
            await session.execute(
                text(
                    "insert into public.appointment_sessions "
                    "(organization_id,assignment_id,doctor_id,starts_at,ends_at,timezone,"
                    "booking_mode,max_patients) values "
                    "(:org,:assignment,:doctor,:starts,:ends,'Asia/Kolkata',"
                    "'SESSION_TOKEN',30)"
                ),
                {
                    "org": seed.organization_id,
                    "assignment": seed.assignment_id,
                    "doctor": existing_session["doctor_id"],
                    "starts": existing_session["starts_at"] + timedelta(minutes=10),
                    "ends": existing_session["ends_at"] + timedelta(minutes=10),
                },
            )


async def test_outbox_lease_rejects_stale_completion(
    transactional_seed: tuple[AsyncSession, Seed],
) -> None:
    session, seed = transactional_seed
    held = await _hold(
        session,
        seed,
        session_id=seed.exact_session_id,
        slot_id=seed.exact_slot_id,
        key=f"outbox-{uuid4()}",
    )
    await _confirm(session, seed, held["appointment_id"])  # type: ignore[arg-type]
    lease_token = uuid4()
    claimed = (
        await session.execute(
            text(
                "update public.outbox_jobs set status='PROCESSING', attempts=1, "
                "lease_until=now()+interval '15 seconds', lease_token=:lease "
                "where organization_id=:org and aggregate_id=:appointment "
                "returning id"
            ),
            {
                "org": seed.organization_id,
                "appointment": held["appointment_id"],
                "lease": lease_token,
            },
        )
    ).mappings().one()

    stale_completion = (
        await session.execute(
            text("select public.complete_outbox_job(:job,:lease)"),
            {"job": claimed["id"], "lease": uuid4()},
        )
    ).scalar_one_or_none()
    assert stale_completion is None
    completed = (
        await session.execute(
            text("select public.complete_outbox_job(:job,:lease)"),
            {"job": claimed["id"], "lease": lease_token},
        )
    ).scalar_one()
    assert completed is True


async def _cleanup(engine: AsyncEngine, seed: Seed) -> None:
    async with engine.begin() as connection:
        parameters = {"org": seed.organization_id}
        for statement in (
            "delete from public.voice_operation_records where organization_id=:org",
            "delete from public.voice_call_sessions where organization_id=:org",
            "delete from public.verification_challenges where organization_id=:org",
            "delete from public.outbox_jobs where organization_id=:org",
            "delete from public.idempotency_records where organization_id=:org",
            "delete from public.payment_attempts where organization_id=:org",
            "delete from public.appointment_contact_permissions where organization_id=:org",
            "delete from public.appointments where organization_id=:org",
            "delete from public.appointment_slots where organization_id=:org",
            "delete from public.appointment_sessions where organization_id=:org",
            "delete from public.patient_contacts where organization_id=:org",
            "delete from public.contact_phones where organization_id=:org",
            "delete from public.patients where organization_id=:org",
            "delete from public.contacts where organization_id=:org",
            "delete from public.audit_events where organization_id=:org",
            "delete from public.inbox_events where organization_id=:org",
            "delete from public.doctor_assignments where organization_id=:org",
            "delete from public.organization_users where organization_id=:org",
            "delete from public.departments where organization_id=:org",
            "delete from public.locations where organization_id=:org",
            "delete from public.organizations where id=:org",
        ):
            await connection.execute(text(statement), parameters)
        await connection.execute(
            text("delete from public.doctors where canonical_name='Dr G2 Test' and id=:doctor"),
            {"doctor": seed.doctor_id},
        )


async def test_capacity_30_and_exact_slot_hold_under_concurrency() -> None:
    database_url = get_settings().database_url
    if not database_url:
        pytest.skip("DATABASE_URL is not configured")
    engine = create_async_engine(database_url, pool_pre_ping=True, pool_size=10, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as setup_session, setup_session.begin():
        seed = await _seed(setup_session, token_capacity=30)

    async def competing_hold(index: int, *, exact: bool) -> tuple[bool, object]:
        try:
            async with factory() as worker, worker.begin():
                await _set_identity(worker, seed.auth_user_id)
                held = await _hold(
                    worker,
                    seed,
                    session_id=seed.exact_session_id if exact else seed.token_session_id,
                    slot_id=seed.exact_slot_id if exact else None,
                    key=f"{'exact' if exact else 'token'}-{index}-{uuid4()}",
                    source="AI_TEXT" if index % 2 else "STAFF",
                )
                return True, held["appointment_id"]
        except DBAPIError as error:
            return False, str(error.orig)

    try:
        token_results = await asyncio.gather(
            *(competing_hold(index, exact=False) for index in range(50))
        )
        token_appointments = [value for succeeded, value in token_results if succeeded]
        token_failures = [value for succeeded, value in token_results if not succeeded]
        assert len(token_appointments) == 30
        assert len(token_failures) == 20
        assert all("session capacity is full" in str(error) for error in token_failures)

        async def confirm(appointment_id: object) -> int:
            async with factory() as worker, worker.begin():
                await _set_identity(worker, seed.auth_user_id)
                result = await _confirm(worker, seed, appointment_id)  # type: ignore[arg-type]
                return int(result["token_number"])

        tokens = await asyncio.gather(*(confirm(item) for item in token_appointments))
        assert sorted(tokens) == list(range(1, 31))

        exact_results = await asyncio.gather(
            *(competing_hold(index, exact=True) for index in range(10))
        )
        assert sum(1 for succeeded, _ in exact_results if succeeded) == 1
        assert sum(1 for succeeded, _ in exact_results if not succeeded) == 9
    finally:
        await _cleanup(engine, seed)
        await engine.dispose()
