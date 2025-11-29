from sqlmodel import SQLModel, create_engine, Session
from src.server.settings.config import settings

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.database_url, echo=settings.debug, connect_args=connect_args)

def init_db() -> None:
    # Se till att modellerna laddas (EN gång, via src.server.*)
    from src.server.models import __all_models  # noqa: F401
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session

