from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

if settings.database_url.startswith("sqlite"):
    raise RuntimeError(
        "SQLite is not supported. Set DATABASE_URL to a PostgreSQL connection string, "
        "e.g. postgresql+psycopg2://watchlist:watchlist@localhost:5432/watchlist"
    )

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate_instruments_cooldown_columns() -> None:
    """Upgrade legacy last_event_at/last_event_type columns to last_event_times JSON."""
    insp = inspect(engine)
    if "instruments" not in insp.get_table_names():
        return

    columns = {c["name"] for c in insp.get_columns("instruments")}

    with engine.begin() as conn:
        if "last_event_times" not in columns:
            conn.execute(
                text(
                    "ALTER TABLE instruments "
                    "ADD COLUMN last_event_times JSONB NOT NULL DEFAULT '{}'::jsonb"
                )
            )

        if "last_event_at" in columns and "last_event_type" in columns:
            conn.execute(
                text(
                    """
                    UPDATE instruments
                    SET last_event_times = jsonb_build_object(
                        last_event_type,
                        to_char(last_event_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US')
                    )
                    WHERE last_event_at IS NOT NULL
                      AND last_event_type IS NOT NULL
                      AND last_event_times = '{}'::jsonb
                    """
                )
            )
            conn.execute(text("ALTER TABLE instruments DROP COLUMN last_event_at"))
            conn.execute(text("ALTER TABLE instruments DROP COLUMN last_event_type"))


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_instruments_cooldown_columns()
