from app.config import settings
from app.models import Base
from campus_common.migrations import run_migrations

run_migrations(Base.metadata, settings.db_schema, settings.database_url)
