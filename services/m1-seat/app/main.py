from campus_common.app_factory import create_app

from app.api import admin, internal, reservations, rooms
from app.config import settings

app = create_app(
    settings,
    title="M1 自习座位预约",
    description="座位搜索、预约、签到、违约记录、历史复用；空间与座位主数据；座位状态写入来源追溯。",
    routers=[rooms.router, reservations.router, admin.router, internal.router],
)
