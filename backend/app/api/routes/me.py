from fastapi import APIRouter, Depends

from app.repositories.memberships import list_active_memberships
from app.schemas.identity import MembershipResponse, PrincipalResponse
from app.security.auth import Principal, get_current_principal

router = APIRouter()


@router.get("/me", response_model=PrincipalResponse)
async def get_me(principal: Principal = Depends(get_current_principal)) -> PrincipalResponse:
    memberships = await list_active_memberships(principal.user_id)
    return PrincipalResponse(
        user_id=principal.user_id,
        email=principal.email,
        memberships=[
            MembershipResponse(organization_id=item.organization_id, role=item.role)
            for item in memberships
        ],
    )
