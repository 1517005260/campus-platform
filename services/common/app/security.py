import asyncio

import bcrypt

# 用户不存在时也做一次同样耗时的校验，使响应时间不暴露用户名是否存在
_DUMMY_HASH = bcrypt.hashpw(b"campus-platform", bcrypt.gensalt()).decode()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


async def verify_password_async(password: str, hashed: str | None) -> bool:
    """在线程池中校验（bcrypt 是 CPU 密集操作，不阻塞事件循环）；hashed 为空时与不存在的用户同样耗时。"""
    ok = await asyncio.to_thread(verify_password, password, hashed or _DUMMY_HASH)
    return ok and hashed is not None
