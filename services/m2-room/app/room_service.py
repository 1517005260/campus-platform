"""M2 申请、审批和查询的业务逻辑。"""

from datetime import timedelta

from campus_common.auth import CurrentUser
from campus_common.db import constraint_errors
from campus_common.errors import AppError, not_found
from campus_common.events import ApplicationStatusChanged, NotificationSend, Ref
from campus_common.outbox import add_event
from campus_common.pagination import Page, PageParams, page_of
from campus_common.params import aload_params, asave_params
from campus_common.timeutil import now
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app import clients
from app import schemas as s
from app.models import Application, ApprovalFlow, ApprovalRecord, Outbox, Setting

ACTIVE_STATUSES = ("pending", "approved")


def _level(application: Application) -> s.FlowLevel:
    for raw in application.flow_snapshot:
        level = s.FlowLevel.model_validate(raw)
        if level.level == application.current_level:
            return level
    raise AppError(409, "APPLICATION_STATE_CONFLICT", "申请的审批流快照无效")


def _record(
    session: AsyncSession,
    application: Application,
    action: str,
    *,
    approver_id: int | None,
    comment: str | None = None,
) -> None:
    session.add(
        ApprovalRecord(
            application_id=application.id,
            level=application.current_level,
            approver_id=approver_id,
            action=action,
            comment=comment,
            at=now(),
        )
    )


def notify(
    session,
    application: Application,
    template: str,
    *,
    user_ids: list[int] | None = None,
    perm: str | None = None,
    **params,
) -> None:
    add_event(
        session,
        Outbox,
        "m2-room",
        NotificationSend(
            user_ids=user_ids or [],
            perm=perm,
            template=template,
            params={
                "application_id": application.id,
                "room_id": application.room_id,
                "purpose": application.purpose,
                "start_at": application.start_at.isoformat(),
                "end_at": application.end_at.isoformat(),
                **params,
            },
            ref=Ref(module="m2", type="application", id=application.id),
        ),
    )


def status_event(session, application: Application, from_status: str, to_status: str) -> None:
    add_event(
        session,
        Outbox,
        "m2-room",
        ApplicationStatusChanged(
            application_id=application.id,
            from_status=from_status,
            to_status=to_status,
        ),
    )


async def _brief(user_id: int) -> s.UserBrief:
    user = await clients.get_user(user_id)
    return s.UserBrief.model_validate(user, from_attributes=True)


async def application_out(session: AsyncSession, application: Application) -> s.Application:
    records = (
        await session.scalars(
            select(ApprovalRecord)
            .where(ApprovalRecord.application_id == application.id)
            .order_by(ApprovalRecord.at, ApprovalRecord.id)
        )
    ).all()
    people: dict[int, s.UserBrief] = {application.applicant_id: await _brief(application.applicant_id)}
    for record in records:
        if record.approver_id is not None and record.approver_id not in people:
            people[record.approver_id] = await _brief(record.approver_id)
    return s.Application(
        id=application.id,
        applicant=people[application.applicant_id],
        room_id=application.room_id,
        start_at=application.start_at,
        end_at=application.end_at,
        purpose=application.purpose,
        attendees=application.attendees,
        status=application.status,
        current_level=application.current_level,
        total_levels=len(application.flow_snapshot),
        deadline_at=application.deadline_at,
        records=[
            s.ApprovalRecordOut(
                level=record.level,
                approver=people.get(record.approver_id) if record.approver_id is not None else None,
                action=record.action,
                comment=record.comment,
                at=record.at,
            )
            for record in records
        ],
    )


async def _eligible(session: AsyncSession, user: CurrentUser) -> tuple[bool, list[str]]:
    rules = await aload_params(session, Setting, s.RoomSettings)
    since = now() - timedelta(days=rules.violation_window_days)
    count = await clients.violation_count(user.id, since)
    reasons = []
    if count >= rules.max_violations:
        reasons.append(f"近 {rules.violation_window_days} 天违约 {count} 次")
    return not reasons, reasons


async def eligibility(session: AsyncSession, user: CurrentUser) -> s.Eligibility:
    eligible, reasons = await _eligible(session, user)
    return s.Eligibility(eligible=eligible, reasons=reasons)


async def submit(session: AsyncSession, user: CurrentUser, body: s.ApplicationCreate) -> s.Application:
    eligible, reasons = await _eligible(session, user)
    if not eligible:
        raise AppError(403, "NOT_ELIGIBLE", "当前不满足整教室申请资格", reasons)

    room = await clients.get_room(body.room_id)
    if room.status != "enabled" or not room.is_whole_bookable:
        raise AppError(400, "ROOM_NOT_BOOKABLE", "该教室不支持整教室预约")

    rules = await aload_params(session, Setting, s.RoomSettings)
    current = now()
    if not (
        current + timedelta(days=rules.advance_days_min)
        <= body.start_at
        <= current + timedelta(days=rules.advance_days_max)
    ):
        raise AppError(
            400,
            "ADVANCE_DAYS_OUT_OF_RANGE",
            f"开始时间须在提前 {rules.advance_days_min} 至 {rules.advance_days_max} 天范围内",
        )

    dept_scoped = room.dept_id is not None
    flow = await session.scalar(
        select(ApprovalFlow)
        .where(
            or_(ApprovalFlow.room_type.is_(None), ApprovalFlow.room_type == room.type),
            or_(ApprovalFlow.dept_scoped.is_(None), ApprovalFlow.dept_scoped == dept_scoped),
        )
        .order_by(ApprovalFlow.priority.desc(), ApprovalFlow.id)
        .limit(1)
    )
    if flow is None:
        raise AppError(409, "APPROVAL_FLOW_NOT_FOUND", "没有适用于该教室的审批流")

    conflict = await session.scalar(
        select(Application.id).where(
            Application.room_id == body.room_id,
            Application.status.in_(ACTIVE_STATUSES),
            Application.start_at < body.end_at,
            Application.end_at > body.start_at,
        )
    )
    if conflict is not None:
        raise AppError(409, "APPLICATION_TIME_CONFLICT", "该教室在申请时段内已有有效申请")

    levels = [s.FlowLevel.model_validate(level) for level in flow.levels]
    first = levels[0]
    approvers = await clients.users_with_perm(
        first.approver_perm, user.dept_id if first.scope == "dept" else None
    )
    application = Application(
        applicant_id=user.id,
        applicant_dept_id=user.dept_id,
        room_id=body.room_id,
        start_at=body.start_at,
        end_at=body.end_at,
        purpose=body.purpose,
        attendees=body.attendees,
        status="pending",
        flow_snapshot=[level.model_dump(mode="json") for level in levels],
        current_level=1,
        deadline_at=current + timedelta(hours=first.timeout_hours),
    )
    session.add(application)
    with constraint_errors(
        {"no_application_overlap": (409, "APPLICATION_TIME_CONFLICT", "该教室在申请时段内已有有效申请")}
    ):
        await session.flush()
        notify(
            session,
            application,
            "room.application_submitted",
            user_ids=[approver.id for approver in approvers if approver.id != user.id],
            level=1,
        )
        status_event(session, application, "", "pending")
        await session.commit()
    return await application_out(session, application)


async def list_mine(
    session: AsyncSession,
    user: CurrentUser,
    status: s.ApplicationStatus | None,
    params: PageParams,
) -> Page[s.Application]:
    filters = [Application.applicant_id == user.id]
    if status is not None:
        filters.append(Application.status == status)
    total = await session.scalar(select(func.count()).select_from(Application).where(*filters)) or 0
    rows = (
        await session.scalars(
            select(Application)
            .where(*filters)
            .order_by(Application.created_at.desc(), Application.id.desc())
            .offset(params.offset)
            .limit(params.size)
        )
    ).all()
    return page_of([await application_out(session, row) for row in rows], total, params)


async def get_application(session: AsyncSession, application_id: int) -> Application:
    application = await session.get(Application, application_id)
    if application is None:
        raise not_found("申请", application_id)
    return application


async def detail(session: AsyncSession, user: CurrentUser, application_id: int) -> s.Application:
    application = await get_application(session, application_id)
    if application.applicant_id != user.id and not user.has("room:approve"):
        raise not_found("申请", application_id)
    return await application_out(session, application)


def _check_turn(application: Application, user: CurrentUser) -> s.FlowLevel:
    if application.status != "pending":
        raise AppError(409, "APPLICATION_STATE_CONFLICT", "申请状态已变化")
    level = _level(application)
    if application.applicant_id == user.id:
        raise AppError(403, "NOT_YOUR_TURN", "不能审批自己的申请")
    if level.approver_perm not in user.perms:
        raise AppError(403, "NOT_YOUR_TURN", "你不是当前级别的审批人")
    if level.scope == "dept" and user.dept_id != application.applicant_dept_id:
        raise AppError(403, "NOT_YOUR_TURN", "你不在当前审批范围内")
    return level


async def approve(
    session: AsyncSession,
    user: CurrentUser,
    application_id: int,
    body: s.ApprovalAction,
) -> s.Application:
    application = await get_application(session, application_id)
    _check_turn(application, user)
    final = application.current_level == len(application.flow_snapshot)
    if not final:
        _record(session, application, "approve", approver_id=user.id, comment=body.comment)
        application.current_level += 1
        next_level = _level(application)
        application.deadline_at = now() + timedelta(hours=next_level.timeout_hours)
        approvers = await clients.users_with_perm(
            next_level.approver_perm,
            application.applicant_dept_id if next_level.scope == "dept" else None,
        )
        notify(
            session,
            application,
            "room.approval_requested",
            user_ids=[approver.id for approver in approvers if approver.id != application.applicant_id],
            level=application.current_level,
        )
        await _commit_state_change(session)
        return await application_out(session, application)

    occupied = await clients.occupy_room(
        application.id,
        application.room_id,
        application.start_at,
        application.end_at,
        "整教室预约",
    )
    application.status = "approved"
    application.m1_block_id = occupied.block_id
    _record(session, application, "approve", approver_id=user.id, comment=body.comment)
    notify(session, application, "room.application_approved", user_ids=[application.applicant_id])
    status_event(session, application, "pending", "approved")
    try:
        await session.commit()
    except Exception as exc:
        await session.rollback()
        fresh = await session.get(Application, application_id, populate_existing=True)
        if fresh is None or fresh.status != "approved":
            await clients.release_room(application_id)
        if isinstance(exc, StaleDataError):
            raise AppError(409, "APPLICATION_STATE_CONFLICT", "申请状态已被其他操作修改") from exc
        raise
    return await application_out(session, application)


async def reject(
    session: AsyncSession,
    user: CurrentUser,
    application_id: int,
    body: s.ApprovalAction,
) -> s.Application:
    application = await get_application(session, application_id)
    _check_turn(application, user)
    application.status = "rejected"
    _record(session, application, "reject", approver_id=user.id, comment=body.comment)
    notify(session, application, "room.application_rejected", user_ids=[application.applicant_id])
    status_event(session, application, "pending", "rejected")
    await _commit_state_change(session)
    return await application_out(session, application)


async def withdraw(session: AsyncSession, user: CurrentUser, application_id: int) -> s.Application:
    application = await get_application(session, application_id)
    if application.applicant_id != user.id:
        raise not_found("申请", application_id)
    if application.status == "pending":
        target = "withdrawn"
        action = "withdraw"
    elif application.status == "approved" and now() < application.start_at:
        await clients.release_room(application.id)
        target = "cancelled"
        action = "cancel"
    else:
        raise AppError(409, "APPLICATION_STATE_CONFLICT", "当前状态不能撤回或取消")
    old_status = application.status
    application.status = target
    _record(session, application, action, approver_id=user.id)
    notify(session, application, f"room.application_{target}", user_ids=[application.applicant_id])
    status_event(session, application, old_status, target)
    await _commit_state_change(session)
    return await application_out(session, application)


async def _commit_state_change(session: AsyncSession) -> None:
    try:
        await session.commit()
    except StaleDataError as exc:
        await session.rollback()
        raise AppError(409, "APPLICATION_STATE_CONFLICT", "申请状态已被其他操作修改") from exc


async def todo(
    session: AsyncSession, user: CurrentUser, params: PageParams
) -> Page[s.ApplicationForApprover]:
    pending = (
        await session.scalars(
            select(Application).where(Application.status == "pending").order_by(Application.id)
        )
    ).all()
    visible = []
    for application in pending:
        level = _level(application)
        if (
            application.applicant_id != user.id
            and level.approver_perm in user.perms
            and (level.scope != "dept" or user.dept_id == application.applicant_dept_id)
        ):
            visible.append(application)
    page_rows = visible[params.offset : params.offset + params.size]
    items = []
    for application in page_rows:
        base = await application_out(session, application)
        affected = await clients.count_affected_reservations(
            application.room_id, application.start_at, application.end_at
        )
        items.append(s.ApplicationForApprover(**base.model_dump(), affected_reservations=affected))
    return page_of(items, len(visible), params)


async def get_flows(session: AsyncSession) -> list[s.ApprovalFlow]:
    flows = (
        await session.scalars(select(ApprovalFlow).order_by(ApprovalFlow.priority.desc(), ApprovalFlow.id))
    ).all()
    return [
        s.ApprovalFlow(
            name=flow.name,
            room_type=flow.room_type,
            dept_scoped=flow.dept_scoped,
            priority=flow.priority,
            levels=[s.FlowLevel.model_validate(level) for level in flow.levels],
        )
        for flow in flows
    ]


async def put_flows(session: AsyncSession, flows: list[s.ApprovalFlow]) -> list[s.ApprovalFlow]:
    names = [flow.name for flow in flows]
    if len(names) != len(set(names)):
        raise AppError(409, "DUPLICATE_FLOW_NAME", "审批流名称不能重复")
    await session.execute(delete(ApprovalFlow))
    session.add_all(
        [
            ApprovalFlow(
                name=flow.name,
                room_type=flow.room_type,
                dept_scoped=flow.dept_scoped,
                priority=flow.priority,
                levels=[level.model_dump(mode="json") for level in flow.levels],
            )
            for flow in flows
        ]
    )
    await session.commit()
    return await get_flows(session)


async def get_settings(session: AsyncSession) -> s.RoomSettings:
    return await aload_params(session, Setting, s.RoomSettings)


async def put_settings(session: AsyncSession, body: s.RoomSettings) -> s.RoomSettings:
    await asave_params(session, Setting, body)
    await session.commit()
    return body
