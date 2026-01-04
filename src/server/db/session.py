from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy import inspect, text

from src.server.settings.config import settings

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.database_url, echo=settings.debug, connect_args=connect_args)


def _ensure_quote_status_column() -> None:
    """
    Skapar kolumnen quote.status om den saknas.
    (create_all lägger inte till nya kolumner på existerande tabeller.)
    """
    insp = inspect(engine)
    try:
        cols = [c["name"] for c in insp.get_columns("quote")]
    except Exception:
        return

    if "status" in cols:
        return

    ddl = "ALTER TABLE quote ADD COLUMN status VARCHAR NOT NULL DEFAULT 'draft'"
    with engine.begin() as conn:
        conn.execute(text(ddl))


def init_db() -> None:
    # Se till att modellerna laddas (EN gång, via src.server.*)
    from src.server.models import __all_models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    _ensure_quote_status_column()


def get_session():
    with Session(engine) as session:
        yield session
