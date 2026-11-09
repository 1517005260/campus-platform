"""通知模板渲染：room.* 按业务时区写明发生了什么；跨天时段写出结束日期。"""

import pytest
from app.templates import render

# UTC 06:00–08:00 = 北京时间 11月5日 14:00–16:00
APP = {
    "application_id": 12,
    "room": "第三教学楼 H3106",
    "purpose": "社团招新宣讲",
    "start_at": "2026-11-05T06:00:00+00:00",
    "end_at": "2026-11-05T08:00:00+00:00",
}
DESC = "整教室申请 #12（第三教学楼 H3106，11月5日 14:00–16:00，用途：社团招新宣讲）"


@pytest.mark.parametrize(
    ("template", "params", "title", "content"),
    [
        (
            "room.application_submitted",
            {"applicant": "张三", "attendees": 40, "level": 1},
            "新的整教室申请待审批",
            f"张三 提交了{DESC}，参加 40 人，请进行第 1 级审批。",
        ),
        (
            "room.approval_requested",
            {"applicant": "张三", "attendees": 40, "level": 2},
            "整教室申请待你审批",
            f"张三 的{DESC}，参加 40 人，已通过第 1 级审批，请进行第 2 级审批。",
        ),
        (
            "room.level_approved",
            {"level": 1, "next_level": 2},
            "整教室申请通过一级审批",
            f"你的{DESC}已通过第 1 级审批，正在等待第 2 级审批。",
        ),
        (
            "room.application_approved",
            {},
            "整教室申请已批准",
            f"你的{DESC}已通过全部审批，教室已在该时段为你占用。",
        ),
        (
            "room.application_rejected",
            {"level": 2, "comment": "该时段已安排考试"},
            "整教室申请被驳回",
            f"你的{DESC}在第 2 级审批被驳回。审批意见：该时段已安排考试",
        ),
        (
            "room.application_rejected",
            {"level": 1, "comment": None},
            "整教室申请被驳回",
            f"你的{DESC}在第 1 级审批被驳回。审批人未填写意见。",
        ),
        (
            "room.application_rejected",
            {"level": 1},
            "整教室申请被驳回",
            f"你的{DESC}在第 1 级审批被驳回。审批人未填写意见。",
        ),
        (
            "room.application_withdrawn",
            {"applicant": "张三", "level": 2},
            "整教室申请已撤回",
            f"张三 撤回了{DESC}，第 2 级审批无需再处理。",
        ),
        (
            "room.application_cancelled",
            {"applicant": "张三"},
            "已批准的整教室申请被取消",
            f"张三 取消了你审批通过的{DESC}，教室占用已释放。",
        ),
        (
            "room.application_expired",
            {"level": 2, "cause": "deadline"},
            "整教室申请已超时失效",
            f"你的{DESC}在第 2 级审批超过处理时限，已自动失效。如仍需使用教室，请重新提交申请。",
        ),
        (
            "room.application_expired",
            {"level": 1, "cause": "started"},
            "整教室申请已超时失效",
            f"你的{DESC}在申请时段开始前仍停留在第 1 级审批，已自动失效。如仍需使用教室，请重新提交申请。",
        ),
    ],
)
def test_room_templates_state_what_happened(template, params, title, content):
    assert render(template, APP | params) == (title, content)


@pytest.mark.parametrize(
    ("start_at", "end_at", "slot"),
    [
        # 同一天只写结束时刻；跨天（含按业务时区才跨天的 UTC 时间）写出结束日期
        ("2026-11-05T14:00:00+08:00", "2026-11-05T23:00:00+08:00", "11月5日 14:00–23:00"),
        ("2026-11-05T22:00:00+08:00", "2026-11-06T08:00:00+08:00", "11月5日 22:00–11月6日 08:00"),
        ("2026-11-05T12:00:00+00:00", "2026-11-05T17:00:00+00:00", "11月5日 20:00–11月6日 01:00"),
        # 日相同、月不同
        ("2026-10-05T10:00:00+08:00", "2026-11-05T10:00:00+08:00", "10月5日 10:00–11月5日 10:00"),
    ],
)
def test_slot_shows_end_date_when_it_is_another_day(start_at, end_at, slot):
    _, content = render("room.application_approved", APP | {"start_at": start_at, "end_at": end_at})
    assert f"，{slot}，" in content
