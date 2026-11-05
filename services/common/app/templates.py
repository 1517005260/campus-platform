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
    return f"{start}–{fmt_time(p['end_at'])[-5:]}" if "end_at" in p else start


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
