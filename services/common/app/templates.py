"""通知模板：template + params → (标题, 正文)。站内通知与邮件使用同一份渲染结果。

模板编码由发送方定义（seat.* 来自 M1，room.* / repair.* 由 M2、M3 提出后在这里登记）。
未知模板或参数缺失时不抛异常：标题用模板编码、正文列出参数，并记录警告，消息不会因此进入死信队列。
"""

import json
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from campus_common.timeutil import to_biz

log = logging.getLogger(__name__)


def fmt_time(value: Any) -> str:
    """ISO 时间 → 业务时区的"11月6日 14:00"；无法解析时原样返回。"""
    try:
        moment = to_biz(datetime.fromisoformat(str(value)))
    except ValueError:
        return str(value)
    return f"{moment.month}月{moment.day}日 {moment:%H:%M}"


def _slot(p: dict[str, Any]) -> str:
    start = fmt_time(p["start_at"])
    if "end_at" not in p:
        return start
    end = fmt_time(p["end_at"])
    # 整教室申请可能跨天，结束日期不同时写全
    return f"{start}–{end[-5:] if end[:-6] == start[:-6] else end}"


Renderer = Callable[[dict[str, Any]], tuple[str, str]]

# M1 管理员操作取消预约的三种实际原因（params.cause），各自说明发生了什么
_ADMIN_CANCEL: dict[str, Callable[[str], tuple[str, str]]] = {
    "seat_disabled": lambda slot: (
        "预约因座位停用被取消",
        f"你预约的 {slot} 自习座位已被管理员停用，预约已取消，不记违约。",
    ),
    "room_disabled": lambda slot: (
        "预约因自习室停用被取消",
        f"你预约的 {slot} 自习座位所在的自习室已被管理员停用，预约已取消，不记违约。",
    ),
    "room_deregistered": lambda slot: (
        "预约因自习室注销被取消",
        f"你预约的 {slot} 自习座位所在教室已不再作为自习室开放，预约已取消，不记违约。",
    ),
}

# M3 超时升级通知里工单所处的状态（只有这三个状态配置升级规则）
_REPAIR_STATUS = {"dispatched": "已派单、待开始维修", "in_progress": "维修中", "pending_acceptance": "待验收"}


def _order(p: dict[str, Any]) -> str:
    return f"报修工单 #{p['order_id']}（{p['category']}）"


TEMPLATES: dict[str, Renderer] = {
    "seat.remind_before": lambda p: (
        "自习预约即将开始",
        f"你预约的 {_slot(p)} 自习座位即将开始，请按时到场签到。",
    ),
    "seat.remind_late": lambda p: (
        "请尽快签到",
        f"你预约的 {_slot(p)} 自习座位尚未签到，"
        f"开始后 {p['deadline_minutes']} 分钟仍未签到将自动取消并记违约。",
    ),
    "seat.no_show_cancelled": lambda p: (
        "预约已因未签到取消",
        f"你预约的 {_slot(p)} 自习座位超时未签到，已自动取消并记一次违约。",
    ),
    "seat.reservation_cancelled_by_block": lambda p: (
        "预约因教室占用被取消",
        f"你预约的 {_slot(p)} 自习座位所在教室被占用"
        f"（{'维修' if p.get('block_source') == 'M3_MAINTENANCE' else '整教室借用'}"
        f"{'：' + p['reason'] if p.get('reason') else ''}），预约已取消，不记违约。",
    ),
    "seat.reservation_cancelled_by_admin": lambda p: _ADMIN_CANCEL[p["cause"]](_slot(p)),
    "room.application_submitted": lambda p: (
        "新的整教室申请待审批",
        f"整教室申请 #{p['application_id']}（{p['room']}，{p['purpose']}，{_slot(p)}）已提交，"
        f"请完成第 {p['level']} 级审批。",
    ),
    "room.approval_requested": lambda p: (
        "整教室申请进入下一审批级",
        f"整教室申请 #{p['application_id']}（{p['room']}，{p['purpose']}，{_slot(p)}）等待第 {p['level']} 级审批。",
    ),
    "room.application_approved": lambda p: (
        "整教室申请已通过",
        f"你的整教室申请 #{p['application_id']}（{p['room']}，{p['purpose']}，{_slot(p)}）已通过。",
    ),
    "room.application_rejected": lambda p: (
        "整教室申请被驳回",
        f"你的整教室申请 #{p['application_id']}（{p['room']}，{p['purpose']}，{_slot(p)}）未通过审批。",
    ),
    "room.application_withdrawn": lambda p: (
        "整教室申请已撤回",
        f"你的整教室申请 #{p['application_id']}（{p['room']}，{p['purpose']}，{_slot(p)}）已撤回。",
    ),
    "room.application_cancelled": lambda p: (
        "整教室预约已取消",
        f"你的整教室申请 #{p['application_id']}（{p['room']}，{p['purpose']}，{_slot(p)}）已取消，教室占用已释放。",
    ),
    "room.application_expired": lambda p: (
        "整教室申请审批超时",
        f"你的整教室申请 #{p['application_id']}（{p['room']}，{p['purpose']}，{_slot(p)}）"
        f"在第 {p['level']} 级审批超时，已自动撤销。",
    ),
    "repair.reported": lambda p: (
        "新的报修待派单",
        f"{p['room']} 报修了{p['category']}故障（报修工单 #{p['order_id']}），请尽快派单。",
    ),
    "repair.cancelled": lambda p: (
        "报修工单已取消",
        f"{_order(p)}已被报修人取消，无需派单。取消原因：{p['reason']}",
    ),
    "repair.dispatched": lambda p: (
        "你有新的维修任务",
        f"{_order(p)}已派给你，请在 {fmt_time(p['deadline_at'])} 前完成。"
        f"{'开始维修时系统会下架整间教室，验收通过后恢复。' if p['blocks_room'] else ''}",
    ),
    "repair.started": lambda p: (
        "报修工单开始维修",
        f"你提交的{_order(p)}已开始维修{'，维修期间该教室暂停预约' if p['blocks_room'] else ''}。",
    ),
    "repair.completed": lambda p: (
        "报修工单待验收",
        f"你提交的{_order(p)}已完工：{p['note']}。请确认后验收评价；"
        f"完工 {p['accept_after_hours']} 小时后仍未验收的，管理员可代为验收。",
    ),
    "repair.rejected": lambda p: (
        "维修验收未通过",
        f"{_order(p)}验收未通过：{p['reason']}。请继续维修{'，教室保持下架' if p['blocks_room'] else ''}。",
    ),
    "repair.accepted": lambda p: (
        "维修工单已验收",
        f"{_order(p)}已{'由管理员代为' if p['by_admin'] else '由报修人'}验收通过，评分 {p['rating']} 星。",
    ),
    "repair.escalated": lambda p: (
        "报修工单超时升级",
        f"{_order(p)}自 {fmt_time(p['since'])} 起处于“{_REPAIR_STATUS[p['status']]}”状态，"
        f"每超过 {p['timeout_hours']} 小时升级一次，现已升级到第 {p['level']} 级，请督办。",
    ),
    "common.roles_changed": lambda p: (
        "你的角色已变更",
        f"管理员已将你的角色调整为：{p['roles'] or '无'}。重新登录后生效。",
    ),
    "common.welcome": lambda p: (
        "欢迎使用校园资源服务平台",
        f"{p['name']}，你好！你可以在左侧菜单使用有权限的功能，系统提醒会显示在右上角的通知中。",
    ),
}


def render(template: str, params: dict[str, Any]) -> tuple[str, str]:
    renderer = TEMPLATES.get(template)
    if renderer is not None:
        try:
            return renderer(params)
        except (KeyError, TypeError) as exc:
            log.warning("通知模板 %s 缺少参数 %s，按未知模板落库", template, exc)
    else:
        log.warning("未知通知模板 %s，按模板编码落库", template)
    return template, json.dumps(params, ensure_ascii=False, sort_keys=True)
