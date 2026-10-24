"""种子数据（幂等，约定见 campus_common.seeding）：默认审批流与申请参数，所有环境都写入，已存在则不覆盖。"""

from campus_common.params import seed_params
from campus_common.seeding import run_seed
from sqlalchemy.dialects.postgresql import insert

from app.config import settings
from app.models import ApprovalFlow, Setting
from app.schemas import ApprovalFlow as FlowIn
from app.schemas import FlowLevel, RoomSettings

DEFAULT_FLOWS = [
    FlowIn(
        name="默认两级审批",
        levels=[
            FlowLevel(level=1, scope="dept", timeout_hours=48),
            FlowLevel(level=2, scope="school", timeout_hours=48),
        ],
    )
]


def seed_base(session) -> None:
    seed_params(session, Setting, RoomSettings())
    for flow in DEFAULT_FLOWS:
        session.execute(
            insert(ApprovalFlow)
            .values(**flow.model_dump(exclude={"levels"}), levels=[lv.model_dump() for lv in flow.levels])
            .on_conflict_do_nothing(index_elements=["name"])
        )


if __name__ == "__main__":
    run_seed(settings, seed_base)
