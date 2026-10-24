"""读取 M1 可调系统参数。数据库 settings 表里没有的键使用 SeatSettings 的默认值。"""

from campus_common.params import load_params
from sqlalchemy.orm import Session

from app.models import Setting
from app.schemas import SeatSettings


def load_rules(session: Session) -> SeatSettings:
    return load_params(session, Setting, SeatSettings)
