import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db import get_session
from app.models.resource import Resource
from app.models.user import User
from app.schemas.resource import ResourceCreate, ResourceOut, ResourceUpdate

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


@router.post("", response_model=ResourceOut, status_code=status.HTTP_201_CREATED)
async def create_resource(
    payload: ResourceCreate,
    user: Annotated[User, Depends(get_current_user)],
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
    user: Annotated[User, Depends(get_current_user)],
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
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    resource = await _get_owned_resource(resource_id, user, session)
    resource.is_active = False
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
