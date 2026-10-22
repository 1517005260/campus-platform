"""输出本服务 schema 中每张表的行数，用于验证种子数据幂等（连续执行两次结果不变）。

在服务目录下运行：uv run --no-sync python ../../scripts/seed_snapshot.py
"""

import os
import sys

from sqlalchemy import create_engine, text

sys.path.insert(0, os.getcwd())

from app.config import settings  # noqa: E402


def main() -> None:
    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        tables = conn.scalars(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = :s AND table_type = 'BASE TABLE' ORDER BY table_name"
            ),
            {"s": settings.db_schema},
        ).all()
        for table in tables:
            count = conn.scalar(text(f'SELECT count(*) FROM "{settings.db_schema}"."{table}"'))
            print(f"{table}\t{count}")


if __name__ == "__main__":
    main()
