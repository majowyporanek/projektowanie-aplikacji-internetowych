import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db import get_session
from app.models.resource import Resource
from app.models.user import User
from app.schemas.resource import ResourceOut

router = APIRouter(prefix="/resources", tags=["resources"])


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
    resource = await session.get(Resource, resource_id)
    if resource is None or resource.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resource not found")
    return resource
