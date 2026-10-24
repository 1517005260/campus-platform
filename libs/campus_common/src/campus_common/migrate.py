"""容器启动时的迁移入口：python -m campus_common.migrate（在服务目录下执行）。

正常发布：数据库版本落后于镜像 → alembic upgrade head。
回滚发布：数据库版本比镜像新（镜像里没有这个修订号）→ 跳过迁移并告警。
迁移遵循"先扩展后收缩"，旧代码可以在新 schema 上运行，所以回滚只换镜像、不降级数据库；
需要降级时由人在确认数据影响后用新镜像执行 alembic downgrade。
"""

import enum
import logging
import sys
from collections.abc import Iterable

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

log = logging.getLogger("campus_common.migrate")


class Plan(enum.StrEnum):
    UPGRADE = "upgrade"
    SKIP_DB_AHEAD = "skip_db_ahead"


def plan(current_revisions: Iterable[str], known_revisions: Iterable[str]) -> Plan:
    """current_revisions：数据库版本表中的修订号；known_revisions：本镜像迁移脚本中的全部修订号。"""
    unknown = set(current_revisions) - set(known_revisions)
    return Plan.SKIP_DB_AHEAD if unknown else Plan.UPGRADE


def current_revisions(url: str, schema: str) -> tuple[str, ...]:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn, opts={"version_table_schema": schema})
            return tuple(ctx.get_current_heads())
    finally:
        engine.dispose()


def main(config_path: str = "alembic.ini") -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s [migrate] %(message)s")
    from app.config import settings  # 服务目录约定：app/config.py 提供 settings

    config = Config(config_path)
    script = ScriptDirectory.from_config(config)
    known = [rev.revision for rev in script.walk_revisions()]
    current = current_revisions(settings.database_url, settings.db_schema)

    if plan(current, known) is Plan.SKIP_DB_AHEAD:
        log.warning(
            "数据库 %s 的版本 %s 比本镜像的迁移 %s 新（回滚发布），跳过迁移",
            settings.db_schema,
            ",".join(current),
            ",".join(script.get_heads()),
        )
        return 0
    command.upgrade(config, "head")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
