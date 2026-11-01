from uuid import UUID

from pydantic import BaseModel, EmailStr


class MembershipResponse(BaseModel):
    organization_id: UUID
    role: str


class PrincipalResponse(BaseModel):
    user_id: UUID
    email: EmailStr | None = None
    memberships: list[MembershipResponse]
