"""common 定时扫描任务（同步会话，由 worker.py 调度；模式同 services/m1-seat/app/jobs.py）。"""

import logging
import smtplib
from datetime import datetime, timedelta

from campus_common.inbox import purge_processed
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import mailer
from app.config import settings
from app.models import Inbox, Notification, User

log = logging.getLogger(__name__)

BATCH = 100
MAX_EMAIL_ATTEMPTS = 3
MAIL_FOOTER = "\n\n——\n校园资源服务平台（系统自动发送，请勿回复）"

# SMTP 服务器层面的错误：本轮其余邮件也发不出去，停止本轮且不计入单条邮件的失败次数
SERVER_SMTP_ERRORS = (
    smtplib.SMTPServerDisconnected,
    smtplib.SMTPConnectError,
    smtplib.SMTPHeloError,
    smtplib.SMTPAuthenticationError,
)


def is_server_error(exc: Exception) -> bool:
    """连接失败、超时、DNS 等网络错误（不是 SMTP 协议应答的 OSError），以及上面几种 SMTP 错误。"""
    if isinstance(exc, SERVER_SMTP_ERRORS):
        return True
    return isinstance(exc, OSError) and not isinstance(exc, smtplib.SMTPException)


def send_pending_emails(session: Session, at: datetime) -> list[int]:
    """发送待发的通知邮件（REQ-D-06），返回本轮发送成功的通知 ID。

    选取 channels 含 email、email_sent_at 为空、失败次数未达 MAX_EMAIL_ATTEMPTS、
    创建不超过 email_max_age_hours 的通知，收件人为启用且有邮箱的用户；未尝试过的排在前面，
    失败过的不会挡住新通知。FOR UPDATE SKIP LOCKED 抢行，多个 worker 不会重复发送同一条。
    - 发送成功：写 email_sent_at；
    - 这封邮件自身的错误（收件人被拒、内容被拒、地址无法编码等）：失败次数加一并记录错误，继续发送其他邮件，
      之后的轮次重试，达到上限后不再发送；
    - 连接失败、超时、认证失败等服务器错误：停止本轮，不计入失败次数，下一轮重试；
    - 未配置 SMTP（settings.email_enabled 为假）：不发送，通知只作为站内信。
    超过保留期仍未发出的通知不再发送（SMTP 长时间故障恢复后不补发过时的提醒）。
    邮件发出后、事务提交前进程崩溃时，下一轮会再发一次（至少一次）。
    """
    if not settings.email_enabled:
        return []
    rows = session.execute(
        select(Notification, User.email)
        .join(User, User.id == Notification.user_id)
        .where(
            Notification.channels.contains(["email"]),
            Notification.email_sent_at.is_(None),
            Notification.email_attempts < MAX_EMAIL_ATTEMPTS,
            Notification.created_at >= at - timedelta(hours=settings.email_max_age_hours),
            User.active.is_(True),
            User.email.is_not(None),
        )
        .order_by(Notification.email_attempts, Notification.id)
        .limit(BATCH)
        .with_for_update(of=Notification, skip_locked=True)
    ).all()

    sent: list[int] = []
    for notification, email in rows:
        try:
            mailer.send_mail(settings, email, notification.title, notification.content + MAIL_FOOTER)
        except Exception as exc:
            if is_server_error(exc):
                log.warning("SMTP 服务器不可用，本轮停止，未发送的留待下一轮", exc_info=True)
                break
            # 这一封邮件自身的问题，不影响其他邮件
            notification.email_attempts += 1
            notification.email_last_error = f"{type(exc).__name__}: {exc}"[:200]
            log.warning(
                "通知 %s 的邮件发送失败（第 %s 次）：%s", notification.id, notification.email_attempts, exc
            )
            continue
        notification.email_sent_at = at
        sent.append(notification.id)
    return sent


def purge_inbox(session: Session, at: datetime) -> int:
    """删除保留期（30 天）之前的消息去重记录，返回删除条数。"""
    return purge_processed(session, Inbox, at)
