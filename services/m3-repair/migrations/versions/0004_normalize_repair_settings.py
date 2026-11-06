"""normalize stored repair settings

报修配置此前保存时不校验，库里可能存着现在的 RepairSettings 拒绝的值；读取配置的接口和升级任务会因此失败。
这里把已存的值改成最接近原意的合法值，之后保存接口按同一规则校验，库里不会再出现非法值：

- categories：去掉首尾空白、去重，丢弃空白和超过 30 字的分类（这些分类本来就无法上报：列为 String(30)）；
  全部被丢弃时恢复默认分类；
- admin_accept_after_hours：小于 1 的改为 1（原意是"尽快可代验收"）；
- escalation_rules：notify_perm 不是 M3 的权限码（repair:dispatch / manage / work）时改为默认的 repair:manage。

只改数据；回滚不还原（规范化后的值旧代码同样可用）。迁移不引用 app 代码，规则写在这里，与当时的模型一致。

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-06 12:00:00
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_CATEGORIES = ["空调", "照明", "桌椅", "插座", "网络", "其他"]
NOTIFY_PERMS = {"repair:dispatch", "repair:manage", "repair:work"}


def _categories(value: list[str]) -> list[str]:
    kept = dict.fromkeys(c.strip() for c in value if 0 < len(c.strip()) <= 30)
    return list(kept) or DEFAULT_CATEGORIES


def _rules(value: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        rule | {"notify_perm": "repair:manage"}
        if "notify_perm" in rule and rule["notify_perm"] not in NOTIFY_PERMS
        else rule
        for rule in value
    ]


NORMALIZE = {
    "categories": _categories,
    "admin_accept_after_hours": lambda hours: max(hours, 1),
    "escalation_rules": _rules,
}


def upgrade() -> None:
    bind = op.get_bind()
    update = sa.text("UPDATE m3.settings SET value = :value WHERE key = :key").bindparams(
        sa.bindparam("value", type_=JSONB)
    )
    for key, value in bind.execute(sa.text("SELECT key, value FROM m3.settings")).all():
        if key in NORMALIZE and (normalized := NORMALIZE[key](value)) != value:
            bind.execute(update, {"key": key, "value": normalized})


def downgrade() -> None:
    pass
