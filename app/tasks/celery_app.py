from celery import Celery

from app.config import settings

celery_app = Celery(
    "booking_system",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_track_started=True,
    task_time_limit=120,
    task_soft_time_limit=90,
    worker_prefetch_multiplier=1,
)


@celery_app.task(name="ping")
def ping() -> str:
    return "pong"
