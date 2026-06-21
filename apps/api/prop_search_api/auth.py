"""Auth dependency: verify the Supabase user JWT and return the user_id (the `sub` claim).

Modern Supabase projects sign user tokens with **asymmetric keys (ES256)** and publish the
public keys at `<project>/auth/v1/.well-known/jwks.json`. We verify against that JWKS
(cached). Audience is `authenticated`. (Legacy HS256-shared-secret projects would instead
set SUPABASE_JWT_SECRET; this project uses ES256.)
"""

import jwt
from fastapi import Header, HTTPException
from jwt import PyJWKClient

from .config import settings

_jwk_client: PyJWKClient | None = None


def _jwks() -> PyJWKClient:
    global _jwk_client
    if _jwk_client is None:
        if not settings.supabase_url:
            raise HTTPException(status_code=500, detail="SUPABASE_URL not configured")
        url = settings.supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json"
        _jwk_client = PyJWKClient(url)
    return _jwk_client


def get_user_id(authorization: str = Header(default="")) -> str:
    """FastAPI dependency → the authenticated user's id. 401 on any problem."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization[len("Bearer "):]
    try:
        # Legacy HS256 fallback if a shared secret is configured; else verify via JWKS.
        if settings.jwt_secret:
            payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"],
                                 audience="authenticated")
        else:
            signing_key = _jwks().get_signing_key_from_jwt(token)
            payload = jwt.decode(token, signing_key.key, algorithms=["ES256", "RS256"],
                                 audience="authenticated")
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing subject")
    return user_id
