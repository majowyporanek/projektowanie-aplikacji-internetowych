import calendar as _calendar
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
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

    now = datetime.now(timezone.utc)
    active_bookings_subq = (
        select(Booking.resource_id, func.count().label("active_count"))
        .where(
            Booking.status.in_(("pending", "confirmed")),
            Booking.starts_at > now,
        )
        .group_by(Booking.resource_id)
        .subquery()
    )
    stmt = (
        select(Resource, func.coalesce(active_bookings_subq.c.active_count, 0))
        .outerjoin(
            active_bookings_subq,
            Resource.id == active_bookings_subq.c.resource_id,
        )
        .where(Resource.organization_id == user.organization_id)
        .order_by(Resource.name)
    )
    rows = (await session.execute(stmt)).all()
    resources = [
        {
            "id": r.id,
            "name": r.name,
            "description": r.description,
            "is_active": r.is_active,
            "active_bookings_count": int(active_count),
        }
        for r, active_count in rows
    ]
    return templates.TemplateResponse(
        request,
        "resources_list.html",
        {"title": "Zasoby", "resources": resources, "user": user},
    )


_SORT_COLUMNS = {
    "starts_at": Booking.starts_at,
    "ends_at": Booking.ends_at,
    "status": Booking.status,
}

_MONTH_NAMES_PL = [
    "styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec",
    "lipiec", "sierpień", "wrzesień", "październik", "listopad", "grudzień",
]
_WEEKDAY_NAMES_PL = ["Pon", "Wt", "Śr", "Czw", "Pt", "Sob", "Ndz"]


@router.get("/calendar", response_class=HTMLResponse)
async def calendar_page(
    request: Request,
    user: Annotated[User | None, Depends(get_current_user_optional)],
    session: Annotated[AsyncSession, Depends(get_session)],
    year: int | None = None,
    month: int | None = None,
    scope: str = "all",
):
    if user is None:
        return RedirectResponse("/login", status_code=303)

    scope = scope if scope in ("mine", "all") else "all"

    today = datetime.now(timezone.utc).date()
    if year is None or month is None or not (1 <= month <= 12):
        year, month = today.year, today.month

    # granice miesiąca w UTC — bierzemy wszystkie rezerwacje które zaczynają się
    # w tym miesiącu (anulowane też, oznaczone osobnym kolorem)
    month_start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        next_month_start = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        next_month_start = datetime(year, month + 1, 1, tzinfo=timezone.utc)

    stmt = (
        select(Booking, Resource.name)
        .join(Resource, Booking.resource_id == Resource.id)
        .where(
            Booking.organization_id == user.organization_id,
            Booking.starts_at >= month_start,
            Booking.starts_at < next_month_start,
        )
        .order_by(Booking.starts_at.asc())
    )
    if scope == "mine":
        stmt = stmt.where(Booking.user_id == user.id)

    rows = (await session.execute(stmt)).all()

    # bucket rezerwacji po dniu rozpoczęcia
    by_day: dict[int, list[dict]] = {}
    for b, resource_name in rows:
        day = b.starts_at.day
        by_day.setdefault(day, []).append(
            {
                "id": b.id,
                "resource_name": resource_name,
                "starts_at": b.starts_at,
                "ends_at": b.ends_at,
                "status": b.status,
                "is_mine": b.user_id == user.id,
            }
        )

    # siatka tygodni (poniedziałek pierwszy); 0 = dzień spoza miesiąca
    cal = _calendar.Calendar(firstweekday=0)
    weeks = []
    for week in cal.monthdayscalendar(year, month):
        cells = []
        for day in week:
            cells.append(
                {
                    "day": day,
                    "is_today": day != 0
                    and date(year, month, day) == today,
                    "bookings": by_day.get(day, []) if day != 0 else [],
                }
            )
        weeks.append(cells)

    prev_year, prev_month = (year, month - 1) if month > 1 else (year - 1, 12)
    next_year, next_month = (year, month + 1) if month < 12 else (year + 1, 1)

    return templates.TemplateResponse(
        request,
        "calendar.html",
        {
            "title": "Kalendarz",
            "user": user,
            "scope": scope,
            "year": year,
            "month": month,
            "month_name": _MONTH_NAMES_PL[month - 1],
            "weekday_names": _WEEKDAY_NAMES_PL,
            "weeks": weeks,
            "prev_year": prev_year,
            "prev_month": prev_month,
            "next_year": next_year,
            "next_month": next_month,
            "today_year": today.year,
            "today_month": today.month,
        },
    )


@router.get("/bookings", response_class=HTMLResponse)
async def bookings_page(
    request: Request,
    user: Annotated[User | None, Depends(get_current_user_optional)],
    session: Annotated[AsyncSession, Depends(get_session)],
    scope: str = "mine",
    resource: str | None = None,
    status: str = "all",
    when: str = "upcoming",
    q: str | None = None,
    sort: str = "starts_at",
    dir: str = "desc",
):
    if user is None:
        return RedirectResponse("/login", status_code=303)

    scope = scope if scope in ("mine", "all") else "mine"
    when = when if when in ("upcoming", "all", "past") else "upcoming"
    status = (
        status
        if status in ("all", "confirmed", "pending", "cancelled", "needs_action")
        else "all"
    )
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
        select(Booking, Resource.name, Resource.is_active, User.email)
        .join(Resource, Booking.resource_id == Resource.id)
        .join(User, Booking.user_id == User.id)
        .where(Booking.organization_id == user.organization_id)
    )
    if scope == "mine":
        stmt = stmt.where(Booking.user_id == user.id)
    if resource_uuid is not None:
        stmt = stmt.where(Booking.resource_id == resource_uuid)
    if status == "confirmed":
        stmt = stmt.where(Booking.status == "confirmed")
    elif status == "pending":
        stmt = stmt.where(Booking.status == "pending")
    elif status == "cancelled":
        stmt = stmt.where(Booking.status == "cancelled")
    elif status == "needs_action":
        # rezerwacja aktywna (nie anulowana) na nieaktywnym zasobie —
        # user musi zdecydować: anulować albo przenieść
        stmt = stmt.where(
            Booking.status != "cancelled", Resource.is_active.is_(False)
        )

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
            "resource_active": resource_active,
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
        for b, resource_name, resource_active, user_email in rows.all()
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
        "status": status if status != "all" else None,
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
            "status": status,
            "when": when,
            "q": q or "",
            "sort": sort,
            "dir": dir,
            "url_with": url_with,
        },
    )
