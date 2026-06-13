import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.cache import cache_invalidate_prefix
from app.db import get_session
from app.models.booking import Booking
from app.models.resource import Resource
from app.models.user import User
from app.schemas.booking import BookingCreate, BookingOut, BookingUpdate

router = APIRouter(prefix="/bookings", tags=["bookings"])

PG_EXCLUSION_VIOLATION = "23P01"
PG_CHECK_VIOLATION = "23514"


@router.get("", response_model=list[BookingOut])
async def list_bookings(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    mine: bool = False,
) -> list[Booking]:
    stmt = select(Booking).where(Booking.organization_id == user.organization_id)
    if mine:
        stmt = stmt.where(Booking.user_id == user.id)
    result = await session.scalars(stmt)
    return list(result)


@router.patch("/{booking_id}", response_model=BookingOut)
async def update_booking(
    booking_id: uuid.UUID,
    payload: BookingUpdate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Booking:
    """Pozwala ownerowi przenieść swoją przyszłą rezerwację na inny aktywny zasób.

    Nie zmienia czasu (na razie - upraszczamy UX i unikamy dodatkowej walidacji).
    Slot czasowy musi być wolny na nowym zasobie - EXCLUDE constraint to wymusi.
    """
    booking = await session.get(Booking, booking_id)
    if booking is None or booking.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    if booking.user_id != user.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "You can only edit your own bookings"
        )
    if booking.status == "cancelled":
        raise HTTPException(status.HTTP_409_CONFLICT, "Cannot edit a cancelled booking")
    if booking.starts_at <= datetime.now(timezone.utc):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Cannot edit a booking that has already started"
        )

    if payload.resource_id == booking.resource_id:
        return booking  # no-op

    new_resource = await session.get(Resource, payload.resource_id)
    if new_resource is None or new_resource.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Target resource not found")
    if not new_resource.is_active:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Target resource is not active"
        )

    old_resource_id = booking.resource_id
    booking.resource_id = payload.resource_id
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        pgcode = getattr(exc.orig, "sqlstate", None)
        if pgcode == PG_EXCLUSION_VIOLATION:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Time slot conflicts with an existing booking on the target resource",
            ) from exc
        raise
    await session.refresh(booking)
    # Invalidate cache dla obu zasobów - starego (slot zwolniony) i nowego (slot zajęty)
    await cache_invalidate_prefix(
        f"availability:{booking.organization_id}:{old_resource_id}:"
    )
    await cache_invalidate_prefix(
        f"availability:{booking.organization_id}:{booking.resource_id}:"
    )
    return booking


@router.post("/{booking_id}/cancel", response_model=BookingOut)
async def cancel_booking(
    booking_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Booking:
    booking = await session.get(Booking, booking_id)
    if booking is None or booking.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    if booking.user_id != user.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "You can only cancel your own bookings"
        )
    if booking.status == "cancelled":
        raise HTTPException(status.HTTP_409_CONFLICT, "Booking is already cancelled")
    if booking.starts_at <= datetime.now(timezone.utc):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Cannot cancel a booking that has already started"
        )
    booking.status = "cancelled"
    await session.commit()
    await session.refresh(booking)
    await cache_invalidate_prefix(
        f"availability:{booking.organization_id}:{booking.resource_id}:"
    )
    return booking


@router.post("", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
async def create_booking(
    payload: BookingCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Booking:
    resource = await session.get(Resource, payload.resource_id)
    if resource is None or resource.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resource not found")
    if not resource.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "Resource is not active")

    booking = Booking(
        organization_id=user.organization_id,
        resource_id=resource.id,
        user_id=user.id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        notes=payload.notes,
    )
    session.add(booking)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        pgcode = getattr(exc.orig, "sqlstate", None)
        if pgcode == PG_EXCLUSION_VIOLATION:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Time slot conflicts with an existing booking",
            ) from exc
        if pgcode == PG_CHECK_VIOLATION:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Booking violates a database check constraint",
            ) from exc
        raise
    await session.refresh(booking)
    await cache_invalidate_prefix(
        f"availability:{booking.organization_id}:{booking.resource_id}:"
    )
    return booking
