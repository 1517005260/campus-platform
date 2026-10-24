"""M1 的 Celery worker 与 Beat 调度表（启动：celery -A app.worker worker / beat）。"""

from campus_common.worker import ServiceWorker

from app import jobs
from app.config import settings
from app.models import Outbox

worker = ServiceWorker(settings, outbox_model=Outbox)
celery = worker.celery

worker.scan(jobs.send_reminders_before, every=60)
worker.scan(jobs.send_reminders_late, every=60)
worker.scan(jobs.mark_no_shows, every=60)
worker.scan(jobs.complete_finished, every=300)
