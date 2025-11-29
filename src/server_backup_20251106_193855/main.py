from fastapi import FastAPI
from contextlib import asynccontextmanager

# Viktigt: importera via "src." eftersom vi startar som "src.server.main:app"
from src.server.api import quotes, system
from src.server.db.session import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Initierar databasen...")
    init_db()
    yield
    print("Avslutar appen...")

app = FastAPI(
    title="Dockit AI - Hantverksassistenten",
    version="0.1.0",
    lifespan=lifespan,
)

# Monterar routrar – system först (innehåller /health och /__debug/routes)
app.include_router(system.router)
app.include_router(quotes.router)

