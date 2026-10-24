"""调用 M1 的跨模块接口：查询教室、占用/释放教室、查询受影响预约、查询违约次数。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from campus_common.service_client import ServiceClient
from campus_common.settings import ServiceSettings

BlockSource = Literal["M2_OCCUPY", "M3_MAINTENANCE"]


class M1Room(BaseModel):
    id: int
    building: str
    name: str
    type: str
    dept_id: int | None
    capacity: int
    is_whole_bookable: bool
    status: str


class M1Reservation(BaseModel):
    id: int
    user_id: int
    seat_id: int
    start_at: datetime
    end_at: datetime
    status: str


class M1BlockResult(BaseModel):
    block_id: int
    cancelled_reservations: list[M1Reservation]


STUB_ROOM = M1Room(
    id=1,
    building="第三教学楼",
    name="H3106",
    type="classroom",
    dept_id=None,
    capacity=60,
    is_whole_bookable=True,
    status="enabled",
)


class M1Client:
    def __init__(self, settings: ServiceSettings):
        self._settings = settings
        self.stub_enabled = settings.stub_clients  # 为真时返回桩数据、不发网络请求
        self._http = ServiceClient(settings.m1_url, settings)

    async def get_room(self, room_id: int) -> M1Room:
        if self.stub_enabled:
            return STUB_ROOM.model_copy(update={"id": room_id})
        return M1Room.model_validate(await self._http.request("GET", f"/internal/v1/rooms/{room_id}"))

    async def create_block(
        self,
        *,
        source: BlockSource,
        ref_id: int,
        room_id: int,
        start_at: datetime,
        end_at: datetime | None,
        reason: str,
        idempotency_key: str,
    ) -> M1BlockResult:
        """在 [start_at, end_at) 内占用或下架整间教室；end_at 为空表示结束时间未知。重试安全。"""
        if self.stub_enabled:
            return M1BlockResult(block_id=ref_id, cancelled_reservations=[])
        data = await self._http.request(
            "POST",
            "/internal/v1/blocks",
            json={
                "room_id": room_id,
                "start_at": start_at.isoformat(),
                "end_at": end_at.isoformat() if end_at else None,
                "source": source,
                "ref_id": ref_id,
                "reason": reason,
            },
            idempotency_key=idempotency_key,
        )
        return M1BlockResult.model_validate(data)

    async def release_block(self, source: BlockSource, ref_id: int) -> bool:
        """释放占用。幂等：本来就没有该占用时返回 False。"""
        if self.stub_enabled:
            return True
        data = await self._http.request("DELETE", f"/internal/v1/blocks/{source}/{ref_id}")
        return data["released"]

    async def room_reservations(
        self, room_id: int, start_at: datetime, end_at: datetime
    ) -> list[M1Reservation]:
        """时段内的有效个人预约（用于告知审批人占用会影响多少人）。"""
        if self.stub_enabled:
            return []
        data = await self._http.request(
            "GET",
            f"/internal/v1/rooms/{room_id}/reservations",
            params={"start_at": start_at.isoformat(), "end_at": end_at.isoformat()},
        )
        return [M1Reservation.model_validate(r) for r in data]

    async def violation_count(self, user_id: int, since: datetime) -> int:
        if self.stub_enabled:
            return 0
        data = await self._http.request(
            "GET", f"/internal/v1/users/{user_id}/violations", params={"since": since.isoformat()}
        )
        return data["count"]
