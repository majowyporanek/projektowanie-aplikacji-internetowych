from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.version import APP_VERSION

router = APIRouter(tags=["health"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


async def check_health(session: AsyncSession) -> dict[str, str]:
    """Sprawdza komponenty (db, redis) i zwraca status systemu.

    Jedno źródło prawdy dla JSON-owego `/health` (monitoring) i dla
    wyrenderowanej karty `/health/card` (UI). Nigdy nie rzuca — endpoint
    obserwowalności ma odpowiadać nawet gdy komponent leży.
    """
    db_ok = False
    try:
        await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    redis_ok = False
    try:
        r = Redis.from_url(settings.redis_url)
        redis_ok = await r.ping()
        await r.aclose()
    except Exception:
        pass

    return {
        "status": "ok" if db_ok and redis_ok else "degraded",
        "version": APP_VERSION,
        "db": "ok" if db_ok else "down",
        "redis": "ok" if redis_ok else "down",
    }


@router.get("/health")
async def health(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    return await check_health(session)


@router.get("/health/card", response_class=HTMLResponse)
async def health_card(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Fragment HTML dla panelu 'Stan systemu' na stronie głównej.

    Czyta te same dane co `/health`, ale renderuje czytelną kartę zamiast
    surowego JSON-a. Bez auth — jak `/health`, bo to obserwowalność, nie
    zasób tenanta.
    """
    return templates.TemplateResponse(
        request,
        "_health_card.html",
        {"health": await check_health(session)},
    )
