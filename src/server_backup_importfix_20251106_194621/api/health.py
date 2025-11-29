# 12) src/server/api/health.py
from fastapi import APIRouter
from src.server.schemas.common import Message

router = APIRouter()

@router.get("/health", response_model=Message, tags=["system"])
def health():
    return {"message": "ok"}


