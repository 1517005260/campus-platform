"""M2 申请、审批和查询的业务逻辑。

- 状态迁移只走 transition()：检查当前状态、写 ApprovalRecord、状态变化时发 m2.application.status_changed；
  定时任务共用。
- "谁此刻能处理申请的当前级别"只在 turn_rules() 定义一次（SQL 条件）：审批时逐条检查给出错误码，
  待办列表用同一组条件在数据库里筛选。
- 看不到申请的人（不是申请人、没有审批记录、也不能审批其中任一级）做任何操作都得到 404；
  看得到但无权执行该操作时 403。
- 最终通过：先记下占用请求时间并提交，再调用 M1 占用，成功后才改为 approved。M1 失败时申请仍是 pending；
  M1 可能已建立占用（例如超时）而申请随后未通过就结束时，由 jobs.release_leftover_blocks 释放。
- 显示用的人员信息来自提交和审批时的登录凭证，读接口只调用 M1 查询待办的受影响预约数（失败时为空）。
- 通知经 outbox 发出；发给审批人时按该级权限码寻址，院系级只发给申请人院系，由 common 解析收件人。
"""

import asyncio
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from campus_common.auth import CurrentUser
from campus_common.clients.m1 import M1Room
from campus_common.db import constraint_errors
from campus_common.errors import AppError, not_found
from campus_common.events import ApplicationStatusChanged, NotificationSend, Ref
from campus_common.outbox import add_event
from campus_common.pagination import Page, PageParams, page_of, paginate
from campus_common.params import aload_params, asave_params
from campus_common.timeutil import at_hour, now, to_biz
from sqlalchemy import ColumnElement, and_, column, delete, exists, false, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app import clients
from app import schemas as s
from app.config import settings
from app.models import Application, ApprovalFlow, ApprovalRecord, Outbox, Setting

PRODUCER = settings.service_name
ACTIVE_STATUSES = ("pending", "approved")
TIME_CONFLICT = (409, "APPLICATION_TIME_CONFLICT", "该教室在申请时段内已有有效申请")
FROM_STATUS: dict[s.RecordAction, str] = {
    "approve": "pending",
    "reject": "pending",
    "withdraw": "pending",
    "expire": "pending",
    "cancel": "approved",
}


# ---------- 申请人 ----------


async def eligibility(session: AsyncSession, user: CurrentUser) -> s.Eligibility:
    rules = await aload_params(session, Setting, s.RoomSettings)
    reasons = await _ineligible_reasons(user, rules, now())
    return s.Eligibility(eligible=not reasons, reasons=reasons)


async def submit(session: AsyncSession, user: CurrentUser, body: s.ApplicationCreate) -> s.Application:
    at = now()
    rules = await aload_params(session, Setting, s.RoomSettings)
    days = (to_biz(body.start_at).date() - at.date()).days
    if body.start_at <= at or not rules.advance_days_min <= days <= rules.advance_days_max:
        raise AppError(
            400,
            "ADVANCE_DAYS_OUT_OF_RANGE",
            f"开始时间须晚于现在，且在今天之后第 {rules.advance_days_min} 至 {rules.advance_days_max} 天内"
            "（按自然日）",
        )
    if reasons := await _ineligible_reasons(user, rules, at):
        raise AppError(403, "NOT_ELIGIBLE", "当前不满足整教室申请资格", reasons)
    room = await clients.get_room(body.room_id)
    _check_room(room, user, body)

    flow = await session.scalar(
        select(ApprovalFlow)
        .where(
            or_(ApprovalFlow.room_type.is_(None), ApprovalFlow.room_type == room.type),
            or_(ApprovalFlow.dept_scoped.is_(None), ApprovalFlow.dept_scoped == (room.dept_id is not None)),
        )
        .order_by(ApprovalFlow.priority.desc(), ApprovalFlow.id)
        .limit(1)
    )
    if flow is None:
        raise AppError(409, "APPROVAL_FLOW_NOT_FOUND", "没有适用于该教室的审批流")
    levels = [s.FlowLevel.model_validate(level) for level in flow.levels]
    if user.dept_id is None and any(level.scope == "dept" for level in levels):
        raise AppError(400, "APPLICANT_DEPT_REQUIRED", "该教室的审批流含院系级审批，申请人须属于某个院系")

    # 预检查只为给出友好的错误，并发提交由排除约束 no_application_overlap 保证
    if await session.scalar(
        select(Application.id).where(
            Application.room_id == body.room_id,
            Application.status.in_(ACTIVE_STATUSES),
            Application.start_at < body.end_at,
            Application.end_at > body.start_at,
        )
    ):
        raise AppError(*TIME_CONFLICT)
    application = Application(
        applicant_id=user.id,
        applicant_username=user.username,
        applicant_name=user.name,
        applicant_dept_id=user.dept_id,
        room_id=room.id,
        room_name=f"{room.building} {room.name}",
        start_at=body.start_at,
        end_at=body.end_at,
        purpose=body.purpose,
        attendees=body.attendees,
        status="pending",
        flow_snapshot=[level.model_dump(mode="json") for level in levels],
        current_level=1,
        deadline_at=at + timedelta(hours=levels[0].timeout_hours),
    )
    session.add(application)
    with constraint_errors({"no_application_overlap": TIME_CONFLICT}):
        await session.flush()
    _status_changed(session, application, "")
    notify(
        session,
        application,
        "room.application_submitted",
        approvers=levels[0],
        applicant=user.name,
        attendees=application.attendees,
        level=1,
    )
    await session.commit()
    return await _present(session, application)


async def list_mine(
    session: AsyncSession, user: CurrentUser, status: s.ApplicationStatus | None, params: PageParams
) -> Page[s.Application]:
    stmt = select(Application).where(Application.applicant_id == user.id)
    if status is not None:
        stmt = stmt.where(Application.status == status)
    page = await paginate(
        session, stmt.order_by(Application.created_at.desc(), Application.id.desc()), params, lambda a: a
    )
    return page_of(await _present_all(session, page.items), page.total, params)


async def detail(session: AsyncSession, user: CurrentUser, application_id: int) -> s.Application:
    return await _present(session, await _load(session, user, application_id))


async def withdraw(session: AsyncSession, user: CurrentUser, application_id: int) -> s.Application:
    at = now()
    application = await _load(session, user, application_id)
    if application.applicant_id != user.id:
        raise AppError(403, "FORBIDDEN", "只有申请人可以撤回或取消申请")
    if application.status == "approved":
        await _cancel(session, user, application, at)
    else:
        transition(session, application, "withdraw", "withdrawn", at, actor=user)
        notify(
            session,
            application,
            "room.application_withdrawn",
            approvers=level_of(application),
            applicant=application.applicant_name,
            level=application.current_level,
        )
        await _commit(session)
    return await _present(session, application)


async def _cancel(session: AsyncSession, user: CurrentUser, application: Application, at: datetime) -> None:
    """取消已通过的申请：先在 M1 释放，成功后才改为 cancelled。

    本地提交失败时教室已释放、申请仍是 approved，重试取消会再次释放（幂等，返回 False）后照常完成。"""
    if at >= application.start_at:
        raise AppError(409, "APPLICATION_STATE_CONFLICT", "申请时段已开始，不能取消")
    await clients.release_room(application.id)
    transition(session, application, "cancel", "cancelled", at, actor=user)
    application.occupy_requested_at = None
    approvers = await session.scalars(
        select(ApprovalRecord.approver_id)
        .where(ApprovalRecord.application_id == application.id, ApprovalRecord.action == "approve")
        .order_by(ApprovalRecord.id)
    )
    notify(
        session,
        application,
        "room.application_cancelled",
        user_ids=approvers.all(),
        applicant=application.applicant_name,
    )
    await _commit(session)


# ---------- 审批人 ----------


async def todo(
    session: AsyncSession, user: CurrentUser, params: PageParams
) -> Page[s.ApplicationForApprover]:
    stmt = (
        select(Application)
        .where(*(rule.holds for rule in turn_rules(user, now())))
        .order_by(Application.deadline_at, Application.id)
    )
    page = await paginate(session, stmt, params, lambda a: a)
    affected = await asyncio.gather(*(_affected_reservations(a) for a in page.items))
    items = [
        s.ApplicationForApprover(**base.model_dump(), affected_reservations=count)
        for base, count in zip(await _present_all(session, page.items), affected, strict=True)
    ]
    return page_of(items, page.total, params)


async def approve(
    session: AsyncSession, user: CurrentUser, application_id: int, body: s.ApprovalAction
) -> s.Application:
    at = now()
    application = await _load(session, user, application_id)
    await _check_turn(session, user, application, at)
    level = level_of(application)
    if level.level < len(application.flow_snapshot):
        transition(session, application, "approve", "pending", at, actor=user, comment=body.comment)
        application.current_level += 1
        next_level = level_of(application)
        application.deadline_at = at + timedelta(hours=next_level.timeout_hours)
        notify(
            session,
            application,
            "room.level_approved",
            user_ids=[application.applicant_id],
            level=level.level,
            next_level=next_level.level,
        )
        notify(
            session,
            application,
            "room.approval_requested",
            approvers=next_level,
            applicant=application.applicant_name,
            attendees=application.attendees,
            level=next_level.level,
        )
        await _commit(session)
        return await _present(session, application)

    # 最后一级：先提交占用请求时间（并发的另一次审批或撤销在此因 version 冲突），再请求 M1。
    # 之后本地提交失败（例如同时被驳回或超时撤销）时不在这里补偿：申请已不是 approved，
    # 由 jobs.release_leftover_blocks 释放可能已建立的占用；并发的另一次最终审批成功时占用属于它，不能释放。
    application.occupy_requested_at = at
    await _commit(session)
    occupied = await clients.occupy_room(application)
    transition(session, application, "approve", "approved", at, actor=user, comment=body.comment)
    application.m1_block_id = occupied.block_id
    notify(session, application, "room.application_approved", user_ids=[application.applicant_id])
    await _commit(session)
    return await _present(session, application)


async def reject(
    session: AsyncSession, user: CurrentUser, application_id: int, body: s.ApprovalAction
) -> s.Application:
    at = now()
    application = await _load(session, user, application_id)
    await _check_turn(session, user, application, at)
    transition(session, application, "reject", "rejected", at, actor=user, comment=body.comment)
    notify(
        session,
        application,
        "room.application_rejected",
        user_ids=[application.applicant_id],
        level=application.current_level,
        comment=body.comment,
    )
    await _commit(session)
    return await _present(session, application)


# ---------- 配置 ----------


async def get_flows(session: AsyncSession) -> list[s.ApprovalFlow]:
    flows = await session.scalars(
        select(ApprovalFlow).order_by(ApprovalFlow.priority.desc(), ApprovalFlow.id)
    )
    return [s.ApprovalFlow.model_validate(flow, from_attributes=True) for flow in flows]


async def put_flows(session: AsyncSession, flows: list[s.ApprovalFlow]) -> list[s.ApprovalFlow]:
    await session.execute(delete(ApprovalFlow))
    session.add_all(ApprovalFlow(**flow.model_dump(mode="json")) for flow in flows)
    with constraint_errors({"uq_approval_flows_name": (409, "DUPLICATE_FLOW_NAME", "审批流名称不能重复")}):
        await session.commit()
    return await get_flows(session)


async def get_settings(session: AsyncSession) -> s.RoomSettings:
    return await aload_params(session, Setting, s.RoomSettings)


async def put_settings(session: AsyncSession, body: s.RoomSettings) -> s.RoomSettings:
    await asave_params(session, Setting, body)
    await session.commit()
    return body


# ---------- 状态迁移与通知（定时任务共用） ----------


def transition(
    session,
    application: Application,
    action: s.RecordAction,
    to_status: str,
    at: datetime,
    *,
    actor: CurrentUser | None = None,
    comment: str | None = None,
) -> None:
    """唯一的状态迁移（含非最后一级通过、状态仍为 pending）：检查当前状态，按当前级别写审批记录。

    同步与异步会话都可用，调用方负责提交；actor 为空表示系统动作。"""
    from_status = application.status
    if from_status != FROM_STATUS[action]:
        raise AppError(409, "APPLICATION_STATE_CONFLICT", "申请状态已变化，不能执行此操作")
    session.add(
        ApprovalRecord(
            application_id=application.id,
            level=application.current_level,
            action=action,
            comment=comment,
            at=at,
            **(
                {}
                if actor is None
                else {
                    "approver_id": actor.id,
                    "approver_username": actor.username,
                    "approver_name": actor.name,
                    "approver_dept_id": actor.dept_id,
                }
            ),
        )
    )
    application.status = to_status
    if to_status != from_status:
        _status_changed(session, application, from_status)


def notify(
    session,
    application: Application,
    template: str,
    *,
    user_ids: Iterable[int] = (),
    approvers: s.FlowLevel | None = None,
    **params,
) -> None:
    """把一条申请通知加入当前事务（同步或异步会话），模板登记在 common 的 app/templates.py。

    收件人是 user_ids，或某一级的审批人（approvers：按该级权限码寻址，院系级只发给申请人院系）。"""
    add_event(
        session,
        Outbox,
        PRODUCER,
        NotificationSend(
            user_ids=list(user_ids),
            perm=approvers.approver_perm if approvers else None,
            dept_id=application.applicant_dept_id if approvers and approvers.scope == "dept" else None,
            template=template,
            params={
                "application_id": application.id,
                "room": application.room_name,
                "purpose": application.purpose,
                "start_at": to_biz(application.start_at).isoformat(),
                "end_at": to_biz(application.end_at).isoformat(),
                **params,
            },
            ref=Ref(module="m2", type="application", id=application.id),
        ),
    )


def level_of(application: Application) -> s.FlowLevel:
    """当前级别。快照中的级别从 1 开始连续（保存审批流时校验）。"""
    return s.FlowLevel.model_validate(application.flow_snapshot[application.current_level - 1])


def overdue(at: datetime) -> ColumnElement[bool]:
    """pending 申请在 at 时已不能再审批：当前级别到了截止时间，或申请时段已开始。"""
    return or_(Application.deadline_at <= at, Application.start_at <= at)


# ---------- 审批资格（SQL 条件） ----------


@dataclass(frozen=True)
class Rule:
    holds: ColumnElement[bool]  # 在含 Application 的查询中求值
    status: int
    code: str
    message: str


def turn_rules(user: CurrentUser, at: datetime) -> list[Rule]:
    """user 在 at 时能处理（通过或驳回）申请当前级别的全部条件，按报错优先级排列。"""
    current = Application.flow_snapshot[Application.current_level - 1]
    return [
        Rule(Application.status == "pending", 409, "APPLICATION_STATE_CONFLICT", "申请已不在审批中"),
        Rule(~overdue(at), 409, "APPLICATION_EXPIRED", "已过审批截止时间或申请时段已开始，申请将被自动撤销"),
        Rule(Application.applicant_id != user.id, 403, "NOT_YOUR_TURN", "不能审批自己的申请"),
        Rule(
            _can_approve(current, user),
            403,
            "NOT_YOUR_TURN",
            "你不是当前级别的审批人（院系级只能由申请人所在院系的审批人处理）",
        ),
        Rule(~_recorded(user, "approve"), 403, "NOT_YOUR_TURN", "同一申请的不同级别须由不同的人审批"),
    ]


def _can_approve(level, user: CurrentUser) -> ColumnElement[bool]:
    """user 符合审批流快照中某一级（JSONB）的要求：有该级权限码；院系级还要求与申请人同院系。"""
    same_dept = false() if user.dept_id is None else Application.applicant_dept_id == user.dept_id
    return and_(
        level["approver_perm"].astext.in_(user.perms),
        or_(level["scope"].astext == "school", same_dept),
    )


def _recorded(user: CurrentUser, action: s.RecordAction | None = None) -> ColumnElement[bool]:
    """user 在该申请上有审批记录（可限定动作）。"""
    condition = exists().where(
        ApprovalRecord.application_id == Application.id, ApprovalRecord.approver_id == user.id
    )
    return condition if action is None else condition.where(ApprovalRecord.action == action)


def _visible_to(user: CurrentUser) -> ColumnElement[bool]:
    """申请人本人、在申请上留下过记录的人、能审批其中任一级的人可以查看。"""
    level = func.jsonb_array_elements(Application.flow_snapshot).table_valued(column("value", JSONB))
    return or_(
        Application.applicant_id == user.id,
        _recorded(user),
        exists(select(1).select_from(level).where(_can_approve(level.c.value, user))),
    )


async def _check_turn(
    session: AsyncSession, user: CurrentUser, application: Application, at: datetime
) -> None:
    rules = turn_rules(user, at)
    row = (
        await session.execute(select(*(rule.holds for rule in rules)).where(Application.id == application.id))
    ).one()
    for rule, holds in zip(rules, row, strict=True):
        if not holds:
            raise AppError(rule.status, rule.code, rule.message)


# ---------- 内部 ----------


async def _ineligible_reasons(user: CurrentUser, rules: s.RoomSettings, at: datetime) -> list[str]:
    count = await clients.violation_count(user.id, at - timedelta(days=rules.violation_window_days))
    if count < rules.max_violations:
        return []
    return [f"近 {rules.violation_window_days} 天违约 {count} 次，违约达到 {rules.max_violations} 次不能申请"]


def _check_room(room: M1Room, user: CurrentUser, body: s.ApplicationCreate) -> None:
    if room.status != "enabled" or not room.is_whole_bookable:
        raise AppError(400, "ROOM_NOT_BOOKABLE", "该教室不支持整教室预约")
    if room.dept_id is not None and room.dept_id != user.dept_id:
        raise AppError(403, "DEPT_RESTRICTED", "该教室只对本院系开放")
    if body.attendees > room.capacity:
        raise AppError(400, "ATTENDEES_EXCEED_CAPACITY", f"参加人数超过教室容量 {room.capacity} 人")
    # 开放时间按业务时区的开始日期取当天的记录；结束不晚于当天关门时间，因此也不能跨天
    day = to_biz(body.start_at).date()
    if not any(
        hours.weekday == day.weekday()
        and at_hour(day, hours.open_hour) <= body.start_at
        and body.end_at <= at_hour(day, hours.close_hour)
        for hours in room.open_hours
    ):
        raise AppError(400, "OUTSIDE_OPEN_HOURS", "申请时段须在教室当天的开放时间内（不能跨天）")


async def _load(session: AsyncSession, user: CurrentUser, application_id: int) -> Application:
    application = await session.scalar(
        select(Application).where(Application.id == application_id, _visible_to(user))
    )
    if application is None:
        raise not_found("申请", application_id)
    return application


async def _commit(session: AsyncSession) -> None:
    try:
        await session.commit()
    except StaleDataError as exc:
        await session.rollback()
        raise AppError(409, "APPLICATION_STATE_CONFLICT", "申请已被其他操作修改，请刷新后重试") from exc


async def _affected_reservations(application: Application) -> int | None:
    """M1 不可用时为空，待办列表照常返回。"""
    try:
        return await clients.count_affected_reservations(
            application.room_id, application.start_at, application.end_at
        )
    except AppError:
        return None


def _status_changed(session, application: Application, from_status: str) -> None:
    add_event(
        session,
        Outbox,
        PRODUCER,
        ApplicationStatusChanged(
            application_id=application.id, from_status=from_status, to_status=application.status
        ),
    )


async def _present(session: AsyncSession, application: Application) -> s.Application:
    return (await _present_all(session, [application]))[0]


async def _present_all(session: AsyncSession, applications: list[Application]) -> list[s.Application]:
    records = defaultdict(list)
    for record in await session.scalars(
        select(ApprovalRecord)
        .where(ApprovalRecord.application_id.in_([a.id for a in applications]))
        .order_by(ApprovalRecord.at, ApprovalRecord.id)
    ):
        records[record.application_id].append(
            s.ApprovalRecordOut(
                level=record.level,
                approver=None
                if record.approver_id is None
                else s.UserBrief(
                    id=record.approver_id,
                    username=record.approver_username,
                    name=record.approver_name,
                    dept_id=record.approver_dept_id,
                ),
                action=record.action,
                comment=record.comment,
                at=record.at,
            )
        )
    return [
        s.Application(
            id=a.id,
            applicant=s.UserBrief(
                id=a.applicant_id,
                username=a.applicant_username,
                name=a.applicant_name,
                dept_id=a.applicant_dept_id,
            ),
            room_id=a.room_id,
            start_at=a.start_at,
            end_at=a.end_at,
            purpose=a.purpose,
            attendees=a.attendees,
            status=a.status,
            current_level=a.current_level,
            total_levels=len(a.flow_snapshot),
            deadline_at=a.deadline_at,
            records=records[a.id],
        )
        for a in applications
    ]
