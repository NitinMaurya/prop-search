"""Auth dependency: verify the Supabase user JWT and return the user_id (the `sub` claim).

Supabase signs user tokens with HS256 using the project's JWT secret and the audience
`authenticated`. The web app sends it as `Authorization: Bearer <token>`.
"""

import jwt
from fastapi import Header, HTTPException

from .config import settings


def get_user_id(authorization: str = Header(default="")) -> str:
    """FastAPI dependency → the authenticated user's id. 401 on any problem."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization[len("Bearer "):]
    if not settings.jwt_secret:
        raise HTTPException(status_code=500, detail="SUPABASE_JWT_SECRET not configured")
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=["HS256"], audience="authenticated")
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing subject")
    return user_id
