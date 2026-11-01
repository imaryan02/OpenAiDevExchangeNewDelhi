from dataclasses import dataclass
from functools import lru_cache
from uuid import UUID

import anyio
import httpx
import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError, PyJWKClient
from jwt.exceptions import PyJWKClientError

from app.core.config import Settings, get_settings
from app.core.errors import ApiError

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    email: str | None


@lru_cache
def get_jwks_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url, cache_keys=True, lifespan=300)


def _decode_token(token: str, settings: Settings) -> dict[str, object]:
    if settings.supabase_jwt_secret is not None:
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience=settings.supabase_jwt_audience,
            issuer=settings.supabase_issuer,
            options={"require": ["exp", "sub"]},
        )

    jwks_url = settings.supabase_jwks_url
    if jwks_url is None:
        raise ApiError(
            code="AUTH_NOT_CONFIGURED",
            message="Authentication is not configured.",
            status_code=503,
        )
    signing_key = get_jwks_client(jwks_url).get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256", "ES256", "EdDSA"],
        audience=settings.supabase_jwt_audience,
        issuer=settings.supabase_issuer,
        options={"require": ["exp", "sub"]},
    )


async def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> Principal:
    if credentials is None:
        raise ApiError(code="AUTH_REQUIRED", message="A bearer token is required.", status_code=401)

    # Supabase Auth is authoritative and also supports projects that still use
    # legacy HS256 signing keys that cannot be resolved from the JWKS endpoint.
    if settings.supabase_url is not None and settings.supabase_publishable_key is not None:
        return await _resolve_principal_with_supabase(credentials.credentials, settings)

    try:
        claims = await anyio.to_thread.run_sync(_decode_token, credentials.credentials, settings)
        user_id = UUID(str(claims["sub"]))
        email_value = claims.get("email")
        return Principal(
            user_id=user_id, email=email_value if isinstance(email_value, str) else None
        )
    except ApiError:
        raise
    except (InvalidTokenError, PyJWKClientError, KeyError, ValueError):
        return await _resolve_principal_with_supabase(credentials.credentials, settings)


async def _resolve_principal_with_supabase(token: str, settings: Settings) -> Principal:
    """Use Supabase Auth as a safe compatibility fallback for legacy signing keys.

    Some Supabase projects still issue HS256 access tokens, whose signing secret is not
    exposed through JWKS. The Auth user endpoint validates the token at its source.
    """
    if settings.supabase_url is None or settings.supabase_publishable_key is None:
        raise ApiError(
            code="AUTH_NOT_CONFIGURED",
            message="Authentication is not configured.",
            status_code=503,
        )
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{str(settings.supabase_url).rstrip('/')}/auth/v1/user",
                headers={
                    "apikey": settings.supabase_publishable_key,
                    "Authorization": f"Bearer {token}",
                },
            )
        if response.status_code != 200:
            raise ApiError(
                code="INVALID_TOKEN",
                message="The access token is invalid.",
                status_code=401,
            )
        payload = response.json()
        user_id = UUID(str(payload["id"]))
        email_value = payload.get("email")
        return Principal(
            user_id=user_id, email=email_value if isinstance(email_value, str) else None
        )
    except ApiError:
        raise
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise ApiError(
            code="INVALID_TOKEN",
            message="The access token could not be verified.",
            status_code=401,
        ) from exc
