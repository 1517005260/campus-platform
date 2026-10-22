"""阶段 0 的桩数据。实现接口时替换掉对这里的调用，全部替换后删除本文件。"""

from campus_common.auth import CurrentUser

from app import schemas as s


def order(
    user: CurrentUser, id_: int = 1, status: s.OrderStatus = "submitted", blocks_room: bool = False
) -> s.WorkOrder:
    return s.WorkOrder(
        id=id_,
        reporter=s.UserBrief(id=user.id, username=user.username, name=user.name, dept_id=user.dept_id),
        room_id=1,
        seat_id=None,
        category="空调",
        description="空调不制冷",
        photos=[],
        status=status,
        blocks_room=blocks_room,
        assignee=None,
        deadline_at=None,
        escalation_level=0,
        rating=None,
        timeline=[],
    )
