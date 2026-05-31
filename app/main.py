from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.api.auth import router as auth_router
from app.api.bookings import router as bookings_router
from app.api.deps import get_current_user_optional
from app.api.health import router as health_router
from app.api.resources import router as resources_router
from app.models.user import User
from app.web.pages import router as pages_router

app = FastAPI(title="Booking System", version="0.1.0")
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(resources_router)
app.include_router(bookings_router)
app.include_router(pages_router)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    user: Annotated[User | None, Depends(get_current_user_optional)],
) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "index.html", {"title": "Booking System", "user": user}
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    user: Annotated[User | None, Depends(get_current_user_optional)],
):
    if user is not None:
        return RedirectResponse("/app/resources", status_code=303)
    return templates.TemplateResponse(
        request, "login.html", {"title": "Zaloguj się", "user": None}
    )


@app.get("/register", response_class=HTMLResponse)
async def register_page(
    request: Request,
    user: Annotated[User | None, Depends(get_current_user_optional)],
):
    if user is not None:
        return RedirectResponse("/app/resources", status_code=303)
    return templates.TemplateResponse(
        request, "register.html", {"title": "Rejestracja", "user": None}
    )
