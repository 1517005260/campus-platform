"""种子数据（幂等，约定见 campus_common.seeding）：默认报修分类与升级规则，所有环境都写入，已存在则不覆盖。"""

from campus_common.params import seed_params
from campus_common.seeding import run_seed

from app.config import settings
from app.models import Setting
from app.schemas import RepairSettings


def seed_base(session) -> None:
    seed_params(session, Setting, RepairSettings())


if __name__ == "__main__":
    run_seed(settings, seed_base)
