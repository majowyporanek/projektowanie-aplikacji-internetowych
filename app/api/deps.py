import uuid
from typing import Annotated

import jwt
from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.cookies import ACCESS_TOKEN_COOKIE
from app.auth.tokens import decode_access_token
from app.db import get_session
from app.models.organization import Organization
from app.models.user import User


async def get_current_user(
    access_token: Annotated[str | None, Cookie(alias=ACCESS_TOKEN_COOKIE)] = None,
    session: AsyncSession = Depends(get_session),
) -> User:
    if access_token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")

    try:
        payload = decode_access_token(access_token)
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from exc

    user_id = uuid.UUID(payload["sub"])
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")

    return user


async def get_current_user_optional(
    access_token: Annotated[str | None, Cookie(alias=ACCESS_TOKEN_COOKIE)] = None,
    session: AsyncSession = Depends(get_session),
) -> User | None:
    if access_token is None:
        return None
    try:
        payload = decode_access_token(access_token)
    except jwt.PyJWTError:
        return None
    user = await session.get(User, uuid.UUID(payload["sub"]))
    return user


async def get_current_org(
    user: Annotated[User, Depends(get_current_user)],
    session: AsyncSession = Depends(get_session),
) -> Organization:
    org = await session.get(Organization, user.organization_id)
    if org is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Organization not found")
    return org
