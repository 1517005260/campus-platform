"""操作审计查询。写入：其他服务经 audit.record 消息，common 自身的管理操作直接写（app/audit.py）。"""

from campus_common.auth import require_perm
from campus_common.db import SessionDep
from campus_common.errors import ERROR_RESPONSES
from campus_common.pagination import Page, PageParams, page_params
from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime

from app import audit
from app import schemas as s

router = APIRouter(prefix="/api/v1", tags=["通知与审计"], responses=ERROR_RESPONSES)


@router.get("/audit", summary="查询操作审计", response_model=Page[s.AuditLogOut])
async def query_audit(
    session: SessionDep,
    actor_id: str | None = Query(None, description="用户 ID、服务名或定时任务名"),
    module: str | None = Query(None, description="common / m1 / m2 / m3"),
    action: str | None = Query(None, description="动作编码，例如 block.create"),
    target_type: str | None = None,
    target_id: str | None = None,
    date_from: AwareDatetime | None = Query(None, description="起始时刻（含），需带时区"),
    date_to: AwareDatetime | None = Query(None, description="结束时刻（不含），需带时区"),
    p: PageParams = Depends(page_params),
    user=Depends(require_perm("audit:read")),
):
    """各条件精确匹配，最新的在前。时间不带时区：422 `VALIDATION_ERROR`。"""
    return await audit.query(
        session,
        p,
        actor_id=actor_id,
        module=module,
        action=action,
        target_type=target_type,
        target_id=target_id,
        date_from=date_from,
        date_to=date_to,
    )
