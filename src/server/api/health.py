# 12) src/server/api/health.py
from fastapi import APIRouter
import os
from datetime import datetime, timezone

DOCKIT_GIT_SHA = os.getenv("RENDER_GIT_COMMIT") or os.getenv("GIT_COMMIT") or "unknown"
DOCKIT_BUILD_UTC = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
from src.server.schemas.common import Message

router = APIRouter()

@router.get("/health", response_model=Message, tags=["system"])
def health():
    return {"message":"ok","git_sha":DOCKIT_GIT_SHA,"build_utc":DOCKIT_BUILD_UTC}



