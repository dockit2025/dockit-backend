from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from src.server.api.quotes import verify_api_key  # återanvänd API-nyckelkontroll
from openai import OpenAI
import os

router = APIRouter(prefix="/speech", tags=["speech"])

@router.post("/transcribe", dependencies=[Depends(verify_api_key)])
async def transcribe_audio(
    file: UploadFile = File(...),
    language: str = Query(default="sv"),
):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY saknas i backend-miljön")

    try:
        client = OpenAI(api_key=api_key)
        audio_bytes = await file.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Tom ljudfil")

        resp = client.audio.transcriptions.create(
            model="whisper-1",
            file=(file.filename or "audio.webm", audio_bytes),
            language=language,
        )

        text = getattr(resp, "text", None) or ""
        return {"text": text}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Transkribering misslyckades: {e}")
