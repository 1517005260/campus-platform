"""common 定时扫描任务。"""

from datetime import datetime

from campus_common.inbox import purge_processed
from sqlalchemy.orm import Session

from app.models import Inbox


def send_pending_emails(session: Session, at: datetime) -> list[int]:
    """待实现（REQ-D-06）：channels 含 email 且 email_sent_at 为空的通知：SKIP LOCKED 抢行，查用户邮箱，
    经 SMTP（开发/测试环境为 Mailpit）发送，成功后写 email_sent_at。
    settings.email_enabled 为假（未配置 SMTP）时不发送，通知保留为站内信。"""
    return []


def purge_inbox(session: Session, at: datetime) -> int:
    """删除保留期（30 天）之前的消息去重记录，返回删除条数。"""
    return purge_processed(session, Inbox, at)
