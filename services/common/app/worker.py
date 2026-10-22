"""common 的 Celery worker 与 Beat 调度表（启动：celery -A app.worker worker / beat）。"""

from campus_common.worker import ServiceWorker
from celery.schedules import crontab

from app import jobs
from app.config import settings

worker = ServiceWorker(settings)
celery = worker.celery

worker.scan(jobs.send_pending_emails, every=10)
worker.scan(jobs.purge_inbox, cron=crontab(hour=3, minute=30))
