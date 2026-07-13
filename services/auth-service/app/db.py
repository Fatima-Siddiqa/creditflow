from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

# Every table this service creates lives inside the `auth` schema, not the
# default `public` schema — this is what "isolated schema per service" means
# in practice: one Postgres instance, one database, N schemas, one per
# service, and nobody reads across schema boundaries.
engine = create_engine(
    settings.database_url,
    connect_args={"options": f"-csearch_path={settings.db_schema}"},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
Base.metadata.schema = settings.db_schema


def get_db():
    """FastAPI dependency — yields a session, always closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()