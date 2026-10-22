from campus_common.app_factory import create_app

from app.api import applications, approvals
from app.config import settings

app = create_app(
    settings,
    title="M2 整教室预约与审批",
    description="权限门槛、申请提交、多级审批（通过/驳回）、超时自动撤销；审批通过后经 M1 占用教室。",
    routers=[applications.router, approvals.router],
)
