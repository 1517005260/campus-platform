"""M3 定时扫描任务。模式与 M1 jobs.py 相同：SKIP LOCKED 抢行 + 状态条件 + 同事务写 outbox。"""

from datetime import datetime

from sqlalchemy.orm import Session


def escalate_overdue(session: Session, at: datetime) -> list[int]:
    """待实现（REQ-M3-07）：按 escalation_rules：工单在某状态停留超过 timeout_hours，escalation_level + 1，
    写时间线，通知拥有 notify_perm 的人。用"上次升级时间"判断，避免每轮重复升级。"""
    return []
