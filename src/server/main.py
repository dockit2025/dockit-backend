from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from src.server.db.session import init_db, get_session
from src.server.api import health
from src.server.api import system
from src.server.api import quotes
from src.server.api.quotes import _list_quotes_impl  # vår säkra list-funktion

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Initierar databasen...")
    init_db()
    yield
    print("Avslutar appen...")

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://lovable.dev",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router)
app.include_router(system.router)
app.include_router(quotes.router)

# Hård proxy: tvinga fram GET /quotes och /quotes/__list
@app.get("/quotes", tags=["quotes"], summary="Lista alla offerter (proxy)")
@app.get("/quotes/", include_in_schema=False)
def list_quotes_proxy(skip: int = 0, limit: int = 50, session: Session = Depends(get_session)):
    return _list_quotes_impl(skip=skip, limit=limit, session=session)

@app.get("/quotes/__list", tags=["quotes"], summary="Lista alla offerter (proxy failsafe)")
def list_quotes_proxy2(skip: int = 0, limit: int = 50, session: Session = Depends(get_session)):
    return _list_quotes_impl(skip=skip, limit=limit, session=session)

