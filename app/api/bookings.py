import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db import get_session
from app.models.booking import Booking
from app.models.resource import Resource
from app.models.user import User
from app.schemas.booking import BookingCreate, BookingOut

router = APIRouter(prefix="/bookings", tags=["bookings"])

PG_EXCLUSION_VIOLATION = "23P01"
PG_CHECK_VIOLATION = "23514"


@router.get("", response_model=list[BookingOut])
async def list_bookings(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[Booking]:
    result = await session.scalars(
        select(Booking).where(Booking.organization_id == user.organization_id)
    )
    return list(result)


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
        status=payload.status,
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
    return booking
