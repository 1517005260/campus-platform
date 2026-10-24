"""模块之间不能直接访问数据库：以 M1 的数据库角色读取其他模块的 schema 会被拒绝（NFR-01）。"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

pytestmark = pytest.mark.db


@pytest.mark.parametrize("schema", ["common", "m2", "m3"])
def test_other_module_schema_is_denied(db, schema):
    with pytest.raises(ProgrammingError, match="permission denied for schema"):
        db.execute(text(f'SELECT 1 FROM "{schema}".alembic_version'))
    db.rollback()
