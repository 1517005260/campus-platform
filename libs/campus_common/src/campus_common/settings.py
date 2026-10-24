"""服务配置。所有配置来自环境变量，代码里不写死地址和密钥。"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str
    db_schema: str

    # 各服务在 app/config.py 中给出本地开发默认值（使用自己的数据库角色）
    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    # 开发默认使用受限的业务账号（由 make run 中的 mqctl setup 创建），与部署环境一致
    rabbitmq_url: str = "amqp://campus_app:campus_app@localhost:5672//"

    jwt_secret: str = "dev-only-secret-change-me-at-least-32-bytes"
    jwt_ttl_minutes: int = 480

    # 本服务调用别人时使用的密钥
    service_key: str = "dev-service-key"
    # 本服务接受的调用方及其密钥，JSON 格式：{"m2-room": "key2", "m3-repair": "key3"}
    # 默认值只用于本地开发；部署环境由 compose 按服务注入（密钥清单见 .env.example）
    service_keys: dict[str, str] = Field(
        default_factory=lambda: {
            name: "dev-service-key" for name in ("common", "m1-seat", "m2-room", "m3-repair")
        }
    )

    # 为 true 时，campus_common.clients 中调用其他服务的函数返回桩数据，不发网络请求
    stub_clients: bool = True
    # 被调用服务的地址（只有调用方会用到；部署环境由 compose 注入容器地址）
    m1_url: str = "http://localhost:8001"
    common_url: str = "http://localhost:8004"

    # 种子数据：基础数据所有环境都写；演示数据只在 seed_demo 为真时写（开发、测试环境）
    seed_demo: bool = False
    demo_password: str = "campus123"

    app_version: str = "dev"
    git_sha: str = "unknown"
    deploy_env: str = "dev"

    @property
    def module(self) -> str:
        """模块代号（common / m1 / m2 / m3），用作 Celery 任务名与幂等键的前缀。"""
        return self.service_name.split("-")[0]
