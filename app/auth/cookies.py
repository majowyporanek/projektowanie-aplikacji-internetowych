from fastapi import Response

from app.config import settings

ACCESS_TOKEN_COOKIE = "access_token"


def set_access_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=settings.jwt_ttl_seconds,
    )


def clear_access_cookie(response: Response) -> None:
    response.delete_cookie(ACCESS_TOKEN_COOKIE)
