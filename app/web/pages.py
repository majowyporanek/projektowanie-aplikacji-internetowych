from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_optional
from app.db import get_session
from app.models.booking import Booking
from app.models.resource import Resource
from app.models.user import User

router = APIRouter(prefix="/app", tags=["pages"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/resources", response_class=HTMLResponse)
async def resources_page(
    request: Request,
    user: Annotated[User | None, Depends(get_current_user_optional)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    result = await session.scalars(
        select(Resource)
        .where(Resource.organization_id == user.organization_id)
        .order_by(Resource.name)
    )
    return templates.TemplateResponse(
        request,
        "resources_list.html",
        {"title": "Zasoby", "resources": list(result), "user": user},
    )


@router.get("/bookings", response_class=HTMLResponse)
async def bookings_page(
    request: Request,
    user: Annotated[User | None, Depends(get_current_user_optional)],
    session: Annotated[AsyncSession, Depends(get_session)],
    scope: str = "mine",
):
    if user is None:
        return RedirectResponse("/login", status_code=303)

    scope = scope if scope in ("mine", "all") else "mine"

    stmt = (
        select(Booking, Resource.name, User.email)
        .join(Resource, Booking.resource_id == Resource.id)
        .join(User, Booking.user_id == User.id)
        .where(Booking.organization_id == user.organization_id)
        .order_by(Booking.starts_at.desc())
    )
    if scope == "mine":
        stmt = stmt.where(Booking.user_id == user.id)

    rows = await session.execute(stmt)
    now = datetime.now(timezone.utc)
    bookings = [
        {
            "id": b.id,
            "resource_name": resource_name,
            "user_email": user_email,
            "starts_at": b.starts_at,
            "ends_at": b.ends_at,
            "status": b.status,
            "notes": b.notes,
            "is_mine": b.user_id == user.id,
            "can_cancel": (
                b.user_id == user.id
                and b.status != "cancelled"
                and b.starts_at > now
            ),
        }
        for b, resource_name, user_email in rows.all()
    ]

    resources = await session.scalars(
        select(Resource)
        .where(
            Resource.organization_id == user.organization_id,
            Resource.is_active.is_(True),
        )
        .order_by(Resource.name)
    )

    return templates.TemplateResponse(
        request,
        "bookings_list.html",
        {
            "title": "Rezerwacje",
            "bookings": bookings,
            "resources": list(resources),
            "user": user,
            "scope": scope,
        },
    )
