import asyncio
import os
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest

from app.core.config import Settings
from app.core.errors import ApiError
from app.hospitalos.routes import ResourceUpdate, staff_resources, update_resources
from app.security.auth import Principal

ORG = UUID("11111111-1111-4111-8111-111111111111")
USER = UUID("22222222-2222-4222-8222-222222222222")
FACILITY = UUID("33333333-3333-4333-8333-333333333333")
pytestmark = pytest.mark.skipif(os.name == "nt", reason="Sandbox blocks Windows asyncio loop socketpair")


class DeniedSession:
    def __init__(self) -> None:
        self.execute = AsyncMock(return_value=Mock(first=Mock(return_value=None)))

    @asynccontextmanager
    async def begin(self):
        yield


def test_staff_cannot_read_another_organizations_resources() -> None:
    session = DeniedSession()
    with pytest.raises(ApiError) as error:
        asyncio.run(staff_resources(ORG, session, Principal(USER, None), Settings.model_construct(hospitalos_demo_enabled=True)))  # type: ignore[arg-type]
    assert error.value.status_code == 403
    assert session.execute.await_count == 1


def test_non_admin_cannot_update_resource() -> None:
    session = DeniedSession()
    payload = ResourceUpdate(
        organization_id=ORG, expected_version=1, emergency_open=True,
        ed_bays_ready=1, icu_beds_ready=0, ventilators_ready=0,
        ct_available=False, trauma_available=False,
        pediatric_available=False, obstetric_available=False,
    )
    with pytest.raises(ApiError) as error:
        asyncio.run(update_resources(FACILITY, payload, session, Principal(USER, None), Settings.model_construct(hospitalos_demo_enabled=True)))  # type: ignore[arg-type]
    assert error.value.status_code == 403
    assert session.execute.await_count == 1
