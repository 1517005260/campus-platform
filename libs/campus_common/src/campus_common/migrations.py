"""Alembic 公共逻辑。各服务的 migrations/env.py 只需调用 run_migrations()。

- 每个服务的版本表放在自己的 schema 里（m1.alembic_version），互不干扰
- 只对比本服务 schema 下的对象，alembic check / autogenerate 不会看到别的服务的表
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import MetaData, create_engine, text


def run_migrations(metadata: MetaData, schema: str, url: str) -> None:
    def include_name(name, type_, parent_names):
        if type_ == "schema":
            return name == schema
        return True

    if context.config.config_file_name:
        fileConfig(context.config.config_file_name)

    engine = create_engine(url)
    with engine.begin() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :s"), {"s": schema}
        )
        if not exists:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))

    with engine.connect() as conn:
        context.configure(
            connection=conn,
            target_metadata=metadata,
            version_table_schema=schema,
            include_schemas=True,
            include_name=include_name,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
