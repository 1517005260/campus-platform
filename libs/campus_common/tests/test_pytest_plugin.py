import pytest
from campus_common.pytest_plugin import database_url_problem


@pytest.mark.parametrize(
    "url",
    [
        None,
        "postgresql+psycopg://campus:campus@localhost:5432/campus",
        "postgresql+psycopg://m1_seat:m1_seat@localhost:5432/campus",
        "postgresql+psycopg://campus:campus@localhost:5432/test_campus",
        "postgresql+psycopg://campus:campus@localhost:5432/campus_test_backup",
    ],
)
def test_non_test_database_rejected(url):
    assert database_url_problem(url)


def test_test_database_allowed():
    assert database_url_problem("postgresql+psycopg://campus:campus@localhost:5432/campus_test") is None
