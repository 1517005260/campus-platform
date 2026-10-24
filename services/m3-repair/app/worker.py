"""M3 的 Celery worker 与 Beat 调度表（启动：celery -A app.worker worker / beat）。"""

from campus_common.worker import ServiceWorker

from app import jobs
from app.config import settings
from app.models import Outbox

worker = ServiceWorker(settings, outbox_model=Outbox)
celery = worker.celery

worker.scan(jobs.escalate_overdue, every=300)
