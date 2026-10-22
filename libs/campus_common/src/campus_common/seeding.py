"""种子数据入口。各服务的 app/seed.py 只写数据本身：

    def seed_base(session): ...          # 所有环境：权限码、系统参数默认值等
    def seed_demo(session): ...          # 仅 SEED_DEMO=true：演示账号、演示教室等

    if __name__ == "__main__":
        run_seed(settings, seed_base, seed_demo)

两者都必须幂等（INSERT ... ON CONFLICT DO NOTHING），每次部署都会执行；CI 连续执行两次并比对各表行数。
演示数据使用固定 ID，写完后用 reset_sequences() 把自增序列推到最大 ID 之后，避免与业务数据冲突。
"""

from collections.abc import Callable, Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

from campus_common.db import make_sync_sessionmaker
from campus_common.settings import ServiceSettings

SeedFn = Callable[[Session], None]


def run_seed(settings: ServiceSettings, base: SeedFn, demo: SeedFn | None = None) -> None:
    sessions = make_sync_sessionmaker(settings.database_url)
    with sessions() as session, session.begin():
        base(session)
        if demo is not None and settings.seed_demo:
            demo(session)


def reset_sequences(session: Session, schema: str, tables: Iterable[str], column: str = "id") -> None:
    for table in tables:
        # 下一个值为 MAX+1；空表时为 1
        session.execute(
            text(
                f"SELECT setval(pg_get_serial_sequence('{schema}.{table}', '{column}'), "
                f'(SELECT COALESCE(MAX("{column}"), 0) + 1 FROM "{schema}"."{table}"), false)'
            )
        )
