"""可调系统参数：每个服务一张键值表（ParamMixin），值的结构与默认值由服务的 Pydantic 参数模型定义。

    class SeatSettings(BaseModel):              # app/schemas.py
        max_hours: int = 4

    seed_params(session, Setting, SeatSettings())          # 种子：写入缺少的默认值，不覆盖已调整的值
    rules = load_params(session, Setting, SeatSettings)    # 定时任务（同步会话）
    rules = await aload_params(session, Setting, SeatSettings)   # 接口（异步会话）
    await asave_params(session, Setting, body)             # 管理接口保存，调用方负责提交

表中没有的键使用模型默认值，因此新增参数只需在模型里加字段并给默认值，下次部署由种子写入。
种子只补缺少的键、不覆盖已有值：修改代码里已有参数的默认值不会改变已部署环境的取值，
需要统一调整时通过管理接口修改，或写一次数据迁移。
"""

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session


def seed_params(session: Session, model, defaults: BaseModel) -> None:
    """写入默认值；已存在的键保持不变（管理员在线上的调整不会被部署覆盖）。"""
    values = [{"key": k, "value": v} for k, v in defaults.model_dump(mode="json").items()]
    if values:
        session.execute(insert(model).values(values).on_conflict_do_nothing())


def load_params[P: BaseModel](session: Session, model, schema: type[P]) -> P:
    stored = {row.key: row.value for row in session.scalars(select(model))}
    return schema.model_validate(stored)


async def aload_params[P: BaseModel](session: AsyncSession, model, schema: type[P]) -> P:
    stored = {row.key: row.value for row in (await session.scalars(select(model))).all()}
    return schema.model_validate(stored)


async def asave_params(session: AsyncSession, model, params: BaseModel) -> None:
    for key, value in params.model_dump(mode="json").items():
        await session.execute(
            insert(model)
            .values(key=key, value=value)
            .on_conflict_do_update(index_elements=[model.key], set_={"value": value})
        )
