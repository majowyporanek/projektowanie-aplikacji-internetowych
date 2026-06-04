import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.cache import cache_get_json, cache_set_json
from app.db import get_session
from app.models.booking import Booking
from app.models.resource import Resource
from app.models.user import User
from app.schemas.booking import AvailabilityResponse, AvailabilitySlot
from app.schemas.resource import ResourceCreate, ResourceOut, ResourceUpdate

AVAILABILITY_CACHE_TTL = 60

router = APIRouter(prefix="/resources", tags=["resources"])


async def _get_owned_resource(
    resource_id: uuid.UUID, user: User, session: AsyncSession
) -> Resource:
    resource = await session.get(Resource, resource_id)
    if resource is None or resource.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resource not found")
    return resource


@router.get("", response_model=list[ResourceOut])
async def list_resources(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[Resource]:
    result = await session.scalars(
        select(Resource).where(Resource.organization_id == user.organization_id)
    )
    return list(result)


@router.get("/{resource_id}", response_model=ResourceOut)
async def get_resource(
    resource_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Resource:
    return await _get_owned_resource(resource_id, user, session)


@router.get("/{resource_id}/availability", response_model=AvailabilityResponse)
async def get_resource_availability(
    resource_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    from_: Annotated[datetime, Query(alias="from")],
    to: Annotated[datetime, Query()],
) -> AvailabilityResponse:
    if to <= from_:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "`to` must be after `from`"
        )
    await _get_owned_resource(resource_id, user, session)

    cache_key = (
        f"availability:{user.organization_id}:{resource_id}"
        f":{from_.isoformat()}:{to.isoformat()}"
    )
    cached = await cache_get_json(cache_key)
    if cached is not None:
        return AvailabilityResponse(
            resource_id=resource_id,
            **{"from": from_},
            to=to,
            busy=[AvailabilitySlot(**slot) for slot in cached],
            cached=True,
        )

    result = await session.scalars(
        select(Booking)
        .where(
            Booking.organization_id == user.organization_id,
            Booking.resource_id == resource_id,
            Booking.status.in_(("pending", "confirmed")),
            Booking.starts_at < to,
            Booking.ends_at > from_,
        )
        .order_by(Booking.starts_at)
    )
    busy = [
        AvailabilitySlot(starts_at=b.starts_at, ends_at=b.ends_at, status=b.status)
        for b in result
    ]
    await cache_set_json(
        cache_key,
        [slot.model_dump(mode="json") for slot in busy],
        AVAILABILITY_CACHE_TTL,
    )
    return AvailabilityResponse(
        resource_id=resource_id,
        **{"from": from_},
        to=to,
        busy=busy,
        cached=False,
    )


@router.post("", response_model=ResourceOut, status_code=status.HTTP_201_CREATED)
async def create_resource(
    payload: ResourceCreate,
    user: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Resource:
    resource = Resource(
        organization_id=user.organization_id,
        name=payload.name,
        description=payload.description,
        is_active=payload.is_active,
    )
    session.add(resource)
    await session.commit()
    await session.refresh(resource)
    return resource


@router.patch("/{resource_id}", response_model=ResourceOut)
async def update_resource(
    resource_id: uuid.UUID,
    payload: ResourceUpdate,
    user: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Resource:
    resource = await _get_owned_resource(resource_id, user, session)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(resource, field, value)
    await session.commit()
    await session.refresh(resource)
    return resource


@router.delete("/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resource(
    resource_id: uuid.UUID,
    user: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    resource = await _get_owned_resource(resource_id, user, session)
    resource.is_active = False
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
