from typing import Literal

from campus_common.settings import ServiceSettings


class Settings(ServiceSettings):
    service_name: str = "common"
    database_url: str = "postgresql+psycopg://common_svc:common_svc@localhost:5432/campus"
    db_schema: str = "common"
    # 引导管理员 admin 的初始密码（所有环境由种子写入，已存在时不改动）
    admin_password: str = "campus123"
    # 邮件发送。smtp_host 为空表示不发邮件（通知只落库为站内信），生产环境接入真实 SMTP 前保持为空。
    # 开发环境默认指向本机 Mailpit；测试环境由 compose 指向 mailpit 容器
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_security: Literal["none", "starttls", "ssl"] = "none"
    mail_from: str = "noreply@campus.local"

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host)


settings = Settings()
