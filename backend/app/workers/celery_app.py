"""AML Monitor — Celery application configuration.

Async task queue for processing transactions and running detectors.
Also includes periodic tasks for blockchain polling.
"""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "aml_monitor",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks", "app.workers.blockchain_poller"],
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,  # Results expire after 1 hour
)

# Celery beat schedule - periodic blockchain polling tasks
celery_app.conf.beat_schedule = {
    "poll-bitcoin-every-5min": {
        "task": "app.workers.blockchain_poller.poll_bitcoin_chain",
        "schedule": 300.0,  # Every 5 minutes
    },
    "poll-ethereum-every-5min": {
        "task": "app.workers.blockchain_poller.poll_ethereum_chain",
        "schedule": 300.0,
    },
    "poll-usdt-every-5min": {
        "task": "app.workers.blockchain_poller.poll_usdt_chain",
        "schedule": 300.0,
    },
    "poll-monero-every-5min": {
        "task": "app.workers.blockchain_poller.poll_monero_chain",
        "schedule": 300.0,
    },
    "check-exchanges-every-10min": {
        "task": "app.workers.blockchain_poller.check_high_risk_exchanges",
        "schedule": 600.0,
    },
}


@celery_app.task(bind=True)
def debug_task(self):
    """Debug task to verify Celery is working."""
    print(f"Request: {self.request!r}")
    return {"status": "ok", "task_id": self.request.id}
