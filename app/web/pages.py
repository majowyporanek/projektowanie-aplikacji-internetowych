import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode

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


_SORT_COLUMNS = {
    "starts_at": Booking.starts_at,
    "ends_at": Booking.ends_at,
    "status": Booking.status,
}


@router.get("/bookings", response_class=HTMLResponse)
async def bookings_page(
    request: Request,
    user: Annotated[User | None, Depends(get_current_user_optional)],
    session: Annotated[AsyncSession, Depends(get_session)],
    scope: str = "mine",
    resource: str | None = None,
    when: str = "upcoming",
    q: str | None = None,
    sort: str = "starts_at",
    dir: str = "desc",
):
    if user is None:
        return RedirectResponse("/login", status_code=303)

    scope = scope if scope in ("mine", "all") else "mine"
    when = when if when in ("upcoming", "all", "past") else "upcoming"
    sort = sort if sort in _SORT_COLUMNS else "starts_at"
    dir = dir if dir in ("asc", "desc") else "desc"
    q = q.strip() if q else None
    q = q or None  # pusty string → None

    resource_uuid: uuid.UUID | None = None
    if resource:
        try:
            resource_uuid = uuid.UUID(resource)
        except ValueError:
            resource_uuid = None

    stmt = (
        select(Booking, Resource.name, User.email)
        .join(Resource, Booking.resource_id == Resource.id)
        .join(User, Booking.user_id == User.id)
        .where(Booking.organization_id == user.organization_id)
    )
    if scope == "mine":
        stmt = stmt.where(Booking.user_id == user.id)
    if resource_uuid is not None:
        stmt = stmt.where(Booking.resource_id == resource_uuid)

    now = datetime.now(timezone.utc)
    if when == "upcoming":
        stmt = stmt.where(Booking.starts_at >= now)
    elif when == "past":
        stmt = stmt.where(Booking.ends_at < now)

    if q:
        stmt = stmt.where(Booking.notes.ilike(f"%{q}%"))

    sort_col = _SORT_COLUMNS[sort]
    stmt = stmt.order_by(sort_col.asc() if dir == "asc" else sort_col.desc())

    rows = await session.execute(stmt)
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

    current_filters = {
        "scope": scope,
        "resource": resource if resource_uuid else None,
        "when": when,
        "q": q,
        "sort": sort,
        "dir": dir,
    }

    def url_with(**overrides) -> str:
        merged = {**current_filters, **overrides}
        params = {k: v for k, v in merged.items() if v}
        return "/app/bookings?" + urlencode(params) if params else "/app/bookings"

    return templates.TemplateResponse(
        request,
        "bookings_list.html",
        {
            "title": "Rezerwacje",
            "bookings": bookings,
            "resources": list(resources),
            "user": user,
            "scope": scope,
            "resource_id": resource if resource_uuid else "",
            "when": when,
            "q": q or "",
            "sort": sort,
            "dir": dir,
            "url_with": url_with,
        },
    )
