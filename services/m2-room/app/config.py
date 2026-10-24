from campus_common.settings import ServiceSettings


class Settings(ServiceSettings):
    service_name: str = "m2-room"
    database_url: str = "postgresql+psycopg://m2_room:m2_room@localhost:5432/campus"
    db_schema: str = "m2"


settings = Settings()
