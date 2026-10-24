from campus_common.settings import ServiceSettings


class Settings(ServiceSettings):
    service_name: str = "m3-repair"
    database_url: str = "postgresql+psycopg://m3_repair:m3_repair@localhost:5432/campus"
    db_schema: str = "m3"


settings = Settings()
