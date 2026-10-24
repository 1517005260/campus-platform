"""测试辅助：生成带指定权限的 token 和服务间请求头、清空服务 schema。

通用 fixture（client、migrated、db、db_seed）由 pytest 插件提供，见 pytest_plugin.py。
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from campus_common.auth import CurrentUser, create_token
from campus_common.settings import ServiceSettings


def user_headers(
    settings: ServiceSettings,
    *,
    perms: list[str],
    user_id: int = 1001,
    dept_id: int | None = 1,
    roles: list[str] | None = None,
) -> dict[str, str]:
    user = CurrentUser(
        id=user_id,
        username=f"u{user_id}",
        name=f"测试用户{user_id}",
        dept_id=dept_id,
        roles=roles or ["test"],
        perms=perms,
    )
    return {"Authorization": f"Bearer {create_token(user, settings)}"}


def service_headers(name: str, key: str, idempotency_key: str | None = None) -> dict[str, str]:
    headers = {"X-Service-Name": name, "X-Service-Key": key}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def truncate_schema(session: Session, schema: str) -> None:
    """清空 schema 中除 Alembic 版本表外的全部表，并重置自增序列。"""
    tables = session.scalars(
        text("SELECT tablename FROM pg_tables WHERE schemaname = :s AND tablename <> 'alembic_version'"),
        {"s": schema},
    ).all()
    if tables:
        names = ", ".join(f'"{schema}"."{t}"' for t in tables)
        session.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))


def record_service_calls(monkeypatch, client, response=None) -> list[tuple[str, str, dict]]:
    """让 campus_common.clients 中的一个客户端（M1Client / CommonClient）改走记录器：关闭它的桩数据、
    不发网络请求，返回记录 (method, path, kwargs) 的列表；每次请求返回 response。只影响传入的客户端。"""
    calls: list[tuple[str, str, dict]] = []

    async def fake_request(method: str, path: str, **kwargs):
        calls.append((method, path, kwargs))
        return response

    monkeypatch.setattr(client, "stub_enabled", False)
    monkeypatch.setattr(client._http, "request", fake_request)
    return calls
