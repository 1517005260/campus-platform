from campus_common.settings import ServiceSettings


class Settings(ServiceSettings):
    service_name: str = "m1-seat"
    database_url: str = "postgresql+psycopg://m1_seat:m1_seat@localhost:5432/campus"
    db_schema: str = "m1"


settings = Settings()
