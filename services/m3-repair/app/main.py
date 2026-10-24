from campus_common.app_factory import create_app

from app.api import orders, work
from app.config import settings

app = create_app(
    settings,
    title="M3 物业报修工单",
    description="故障上报、派单、维修中、超时升级、完工验收与评价；维修中可经 M1 下架整间教室。",
    routers=[orders.router, work.router],
)
