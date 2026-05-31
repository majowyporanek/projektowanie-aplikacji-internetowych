from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_optional
from app.db import get_session
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
