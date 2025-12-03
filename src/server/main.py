from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from src.server.db.session import init_db, get_session
from src.server.api import health, system, quotes, articles
from src.server.api.quote_document import router as quote_document_router
from src.server.api.quotes import _list_quotes_impl

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
        "https://4d33ec7a-7844-4eb7-9795-d6b0452f4ffe.lovableproject.com",
        "https://id-preview--4d33ec7a-7844-4eb7-9795-d6b0452f4ffe.lovable.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(system.router)
app.include_router(quotes.router)     # kräver API-key
app.include_router(articles.router)
app.include_router(quote_document_router)   # OFFENTLIG – kräver ingen API key

@app.get("/quotes", tags=["quotes"])
@app.get("/quotes/", include_in_schema=False)
def list_quotes_proxy(skip: int = 0, limit: int = 50, session: Session = Depends(get_session)):
    return _list_quotes_impl(skip=skip, limit=limit, session=session)

@app.get("/quotes/__list", tags=["quotes"])
def list_quotes_proxy2(skip: int = 0, limit: int = 50, session: Session = Depends(get_session)):
    return _list_quotes_impl(skip=skip, limit=limit, session=session)
