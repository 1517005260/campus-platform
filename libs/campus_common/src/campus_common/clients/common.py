"""调用 common 的跨模块接口：按 ID 查用户（含邮箱）、按权限码（和院系）查用户。"""

from pydantic import BaseModel

from campus_common.service_client import ServiceClient
from campus_common.settings import ServiceSettings


class UserBrief(BaseModel):
    id: int
    username: str
    name: str
    dept_id: int | None


class UserContact(UserBrief):
    email: str | None


class CommonClient:
    def __init__(self, settings: ServiceSettings):
        self._settings = settings
        self.stub_enabled = settings.stub_clients  # 为真时返回桩数据、不发网络请求
        self._http = ServiceClient(settings.common_url, settings)

    async def get_user(self, user_id: int) -> UserContact:
        if self.stub_enabled:
            return UserContact(id=user_id, username=f"user{user_id}", name="演示用户", dept_id=1, email=None)
        return UserContact.model_validate(await self._http.request("GET", f"/internal/v1/users/{user_id}"))

    async def users_with_perm(self, perm: str, dept_id: int | None = None) -> list[UserBrief]:
        """例如本院系审批人：perm=room:approve、dept_id=申请人院系；维修工：perm=repair:work。"""
        if self.stub_enabled:
            return [UserBrief(id=9001, username="stub", name=f"拥有 {perm} 的用户", dept_id=dept_id)]
        params = {"perm": perm} | ({"dept_id": dept_id} if dept_id is not None else {})
        data = await self._http.request("GET", "/internal/v1/users", params=params)
        return [UserBrief.model_validate(u) for u in data]
