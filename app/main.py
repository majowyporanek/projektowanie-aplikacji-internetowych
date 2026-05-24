from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.api.auth import router as auth_router
from app.api.health import router as health_router

app = FastAPI(title="Booking System", version="0.1.0")
app.include_router(health_router)
app.include_router(auth_router)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {"title": "Booking System"})
