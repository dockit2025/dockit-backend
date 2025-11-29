from typing import Generator
from sqlmodel import Session, create_engine

# Kör backend från projektroten så att SQLite-pathen stämmer
engine = create_engine("sqlite:///dockit.db", echo=False)

def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
