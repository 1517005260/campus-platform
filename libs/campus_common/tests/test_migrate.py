from campus_common.migrate import Plan, plan

KNOWN = ["0002", "0001"]


def test_upgrade_when_database_is_empty():
    assert plan([], KNOWN) is Plan.UPGRADE


def test_upgrade_when_database_is_behind_or_current():
    assert plan(["0001"], KNOWN) is Plan.UPGRADE
    assert plan(["0002"], KNOWN) is Plan.UPGRADE


def test_skip_when_database_is_ahead_of_image():
    # 回滚到旧镜像：数据库已在 0003，旧镜像只认识 0001、0002
    assert plan(["0003"], KNOWN) is Plan.SKIP_DB_AHEAD
