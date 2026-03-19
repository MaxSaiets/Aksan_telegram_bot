from celery import Celery
from celery.signals import worker_process_init
from config import settings


@worker_process_init.connect
def init_db(**kwargs):
    from app.database.client import db_client
    db_client.init()


celery_app = Celery(
    "telegram_bot",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.video_pipeline",
        "app.tasks.photo_pipeline",
        "app.tasks.export_task",
        "app.tasks.files_task",
        "app.tasks.undo_task",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=3600,
    task_track_started=True,
    worker_prefetch_multiplier=1,   # one task at a time per worker slot
    task_acks_late=True,            # ack only after completion (safer)
    worker_pool="solo",             # Windows: prefork not supported, use solo pool
)
