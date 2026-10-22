"""阶段 0 的桩数据。实现接口时替换掉对这里的调用，全部替换后删除本文件。"""

from datetime import timedelta

from campus_common.auth import CurrentUser
from campus_common.timeutil import now

from app import schemas as s


def application(user: CurrentUser, id_: int = 1, status: s.ApplicationStatus = "pending"):
    start = now().replace(minute=0, second=0, microsecond=0) + timedelta(days=3)
    return s.Application(
        id=id_,
        applicant=s.UserBrief(id=user.id, username=user.username, name=user.name, dept_id=user.dept_id),
        room_id=1,
        start_at=start,
        end_at=start + timedelta(hours=2),
        purpose="班级读书会",
        attendees=30,
        status=status,
        current_level=1,
        total_levels=2,
        deadline_at=now() + timedelta(hours=48),
        records=[],
    )
