from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()


class Settings(BaseModel):
    app_name: str = "Dockit AI - Hantverksassistenten (v0)"
    environment: str = os.getenv("ENVIRONMENT", "dev")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./dockit.db")
    debug: bool = os.getenv("DEBUG", "1") == "1"

    # API key for protected endpoints (e.g. /quotes/* and /sandbox/*)
    dockit_api_key: str = os.getenv("DOCKIT_API_KEY", "")


settings = Settings()
