"""school approval permission：学校级审批改用独立的权限码 room:approve_school

M2 审批流的学校级改为要求 room:approve_school，院系级仍是 room:approve。种子不修改已存在的角色，
已有环境的预置角色在这里调整（新环境的数据库此时还没有角色，种子按 app/permissions.py 写入）：

- 权限码目录加入 room:approve_school（迁移先于种子执行，角色引用它之前目录里必须已有）；
- 预置学校审批人 school_approver：加上 room:approve_school、去掉 room:approve；
- 预置系统管理员 sys_admin：加上 room:approve_school（它拥有全部权限码）。

院系审批人与自定义角色不动。每一步都可重复执行。回滚恢复学校审批人的 room:approve，
并从目录删除 room:approve_school（分配了它的角色随之失去它，旧版本不认识这个权限码）。
迁移不引用 app 代码，权限码与描述写在这里。

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-09 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 预置角色的编码固定（种子写入，不可删除或改名），按编码定位；角色不存在（新环境）时什么也不做
GRANT = sa.text(
    "INSERT INTO common.role_permissions (role_code, perm_code) "
    "SELECT code, :perm FROM common.roles WHERE code = :role ON CONFLICT DO NOTHING"
)
REVOKE = sa.text("DELETE FROM common.role_permissions WHERE role_code = :role AND perm_code = :perm")


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO common.permissions (code, module, description) "
            "VALUES ('room:approve_school', 'm2', '学校级审批整教室申请') ON CONFLICT DO NOTHING"
        )
    )
    bind.execute(
        GRANT, [{"role": role, "perm": "room:approve_school"} for role in ("school_approver", "sys_admin")]
    )
    bind.execute(REVOKE, {"role": "school_approver", "perm": "room:approve"})


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(GRANT, {"role": "school_approver", "perm": "room:approve"})
    bind.execute(sa.text("DELETE FROM common.permissions WHERE code = 'room:approve_school'"))
