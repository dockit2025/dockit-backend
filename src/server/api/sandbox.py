from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.server.api.quotes import verify_api_key
from src.server.db.session import get_session
from src.server.schemas.quote import QuoteDraftIn
from src.services.quote_service import make_draft
from src.services.ai_client import AIClient
from src.services.ai_specs import (
    load_task_generation_spec,
    load_text_cleaner_spec,
)
from src.services import task_suggestions as ts
from src.services import ai_suggestions  # ATL-hjälp
from src.services.atl_lookup import get_atl_time_minutes


class GPTTaskSuggestRequest(BaseModel):
    """
    Request till /sandbox/gpt-suggest-tasks.
    """
    limit: Optional[int] = 50
    segments: Optional[List[str]] = None


class AcceptTaskRequest(BaseModel):
    """
    En enskild task som användaren valt 'Acceptera' på i Sandlådan.
    """
    task: Dict[str, Any]
    source: Optional[str] = "sandbox_ui"


class SandboxInterpretRequest(BaseModel):
    """
    Request till /sandbox/interpret från Sandbox-fliken i frontend.
    """
    job_summary: Optional[str] = None
    text: Optional[str] = None
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None
    apply_rot: bool = False  # Sandbox: som standard ingen ROT här


class TextCleanerRequest(BaseModel):
    """
    Request till /sandbox/clean-text.
    """
    job_text: str


router = APIRouter(
    prefix="/sandbox",
    tags=["sandbox"],
    dependencies=[Depends(verify_api_key)],
)


# =========================================================
#  TOLKA JOBB (Sandbox)
# =========================================================

@router.post("/interpret")
def sandbox_interpret(
    payload: SandboxInterpretRequest,
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    summary = payload.job_summary or payload.text
    if not summary or not summary.strip():
        raise HTTPException(status_code=400, detail="job_summary eller text krävs")

    draft_payload = QuoteDraftIn(
        customer_name=payload.customer_name or "Sandbox-kund",
        customer_email=payload.customer_email,
        job_summary=summary.strip(),
        lines=[],
        apply_rot=payload.apply_rot,
    )

    result = make_draft(payload=draft_payload, session=session)

    # Rensa missing_segments från uppenbart brus (hälsningar, tackfraser)
    try:
        interpretation = result.get("interpretation") or {}
        raw_missing = interpretation.get("missing_segments") or []

        if isinstance(raw_missing, list):
            filtered_missing: List[str] = []

            for s in raw_missing:
                text = str(s or "").strip()
                if not text:
                    continue

                lower = text.lower()
                words = lower.split()

                # Korta hälsningar
                if words and words[0] in {"hej", "hejsan", "tjena"} and len(words) <= 5:
                    continue

                # Korta tackfraser
                if "tack" in words and len(words) <= 6:
                    continue

                filtered_missing.append(text)

            interpretation["missing_segments"] = filtered_missing
            result["interpretation"] = interpretation
    except Exception:
        pass

    result["sandbox"] = True
    return result


# =========================================================
#  TEXTRENSARE – /sandbox/clean-text
# =========================================================

@router.post("/clean-text")
def sandbox_clean_text(payload: TextCleanerRequest) -> Dict[str, Any]:
    """
    Använder textrensar-specen för att ta in fri job_text och
    returnera rena arbetsmoment-segment.

    Output:
      { "clean_segments": ["...","..."] }
    """
    job_text = (payload.job_text or "").strip()
    if not job_text:
        raise HTTPException(status_code=400, detail="job_text krävs")

    try:
        spec = load_text_cleaner_spec()
        client = AIClient()
        result = client.generate_text_segments(spec=spec, job_text=job_text)

        clean_segments = result.get("clean_segments") or []
        if not isinstance(clean_segments, list):
            clean_segments = []

        out: List[str] = []
        for item in clean_segments:
            text: str = ""
            if isinstance(item, dict):
                # Nytt: hantera både segment_text och text
                if "segment_text" in item:
                    text = str(item.get("segment_text") or "").strip()
                elif "text" in item:
                    text = str(item.get("text") or "").strip()
                else:
                    text = str(item).strip()
            else:
                text = str(item or "").strip()

            if text:
                out.append(text)

        return {"clean_segments": out}
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Text-cleaner-spec saknas: {e}",
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
#  GPT-FÖRSLAG (missing_task_segments → GPT + ATL)
# =========================================================

@router.post("/gpt-suggest-tasks")
def gpt_suggest_tasks(payload: GPTTaskSuggestRequest) -> Dict[str, Any]:
    limit = payload.limit or 50

    segments: List[Dict[str, Any]] = []
    note: Optional[str] = None

    if payload.segments:
        for idx, text in enumerate(payload.segments):
            if not text or not str(text).strip():
                continue
            segments.append(
                {
                    "segment_id": f"ui_{idx + 1:04d}",
                    "segment_text": str(text).strip(),
                    "source_type": "sandbox_ui",
                    "room_hint": None,
                    "language": "sv",
                    "existing_task_ref": None,
                }
            )

        gpt_input: Dict[str, Any] = ai_suggestions.build_gpt_input_with_atl_for_segments(
            segments
        )
    else:
        base_input: Dict[str, Any] = ts.build_gpt_input_from_missing_segments(limit=limit)
        segments = base_input.get("segments") or []

        if not segments:
            return {
                "gpt_input": base_input,
                "suggested_tasks": [],
                "note": "Inga missing_task-segment hittades i loggen.",
            }

        atl_enriched = ai_suggestions.build_gpt_input_with_atl_for_segments(segments)
        gpt_input = {
            **base_input,
            "atl_candidates": atl_enriched.get("atl_candidates", []),
        }

    if not segments:
        return {
            "gpt_input": gpt_input,
            "suggested_tasks": [],
            "note": "Inga segments skickades in och inga missing_task-segment hittades i loggen.",
        }

    spec = load_task_generation_spec()
    client = AIClient()
    gpt_output: Dict[str, Any] = client.generate_tasks(spec=spec, gpt_input=gpt_input)

    raw_suggested = gpt_output.get("suggested_tasks") or []
    if not isinstance(raw_suggested, list):
        raw_suggested = []

    filtered: List[Dict[str, Any]] = []
    existing_tasks_cache: Dict[str, List[Dict[str, Any]]] = {}

    for s in raw_suggested:
        if not isinstance(s, dict):
            continue

        task_ref = (s.get("task_ref") or "").strip()
        category = (s.get("category") or "ovrigt").strip() or "ovrigt"

        if not task_ref:
            continue

        if any((t.get("task_ref") or "").strip() == task_ref for t in filtered):
            continue

        path = ts._category_to_mapping_path(category)
        key = str(path)

        if key not in existing_tasks_cache:
            data = ts._load_mapping_file(path)
            existing_tasks_cache[key] = data.get("tasks") or []

        if ts._task_exists(existing_tasks_cache[key], task_ref):
            continue

        filtered.append(s)

    for s in filtered:
        try:
            atl_moment = (s.get("atl_moment") or "").strip()
            atl_variant = s.get("atl_variant")
            if atl_moment and atl_variant is not None:
                variant_int = int(atl_variant)
            else:
                continue

            minutes = get_atl_time_minutes(atl_moment, variant_int)
            if minutes and minutes > 0:
                s["time_source"] = "atl"
                s["time_minutes_per_unit"] = minutes
        except Exception:
            continue

    if not filtered and payload.segments:
        note = (
            "GPT försökte matcha segmenten mot ATL men hittade inga nya "
            "arbetsmoment som inte redan finns i mappings."
        )
    else:
        note = None

    return {
        "gpt_input": gpt_input,
        "suggested_tasks": filtered,
        "note": note,
    }


# =========================================================
#  ACCEPTERA TASK (med möjlighet att rätta ATL + kategori)
# =========================================================

@router.post("/accept-task")
def accept_task(payload: AcceptTaskRequest) -> Dict[str, Any]:
    task = payload.task or {}
    if not isinstance(task, dict) or not (task.get("task_ref") or "").strip():
        return {"status": "ignored", "reason": "Ogiltig eller tom task"}

    try:
        atl_moment_raw = task.get("atl_moment")
        atl_variant_raw = task.get("atl_variant")

        atl_moment = (atl_moment_raw or "").strip() if isinstance(atl_moment_raw, str) else ""
        if atl_moment and atl_variant_raw is not None:
            try:
                variant_int = int(atl_variant_raw)
                minutes = get_atl_time_minutes(atl_moment, variant_int)
                if minutes and minutes > 0:
                    task["time_source"] = "atl"
                    task["time_minutes_per_unit"] = minutes
            except Exception:
                pass
    except Exception:
        pass

    gpt_output: Dict[str, Any] = {"suggested_tasks": [task]}

    event_payload: Dict[str, Any] = {
        "source": payload.source or "sandbox_ui",
        "suggested_tasks": [task],
    }
    ts.log_task_suggestions(event_payload)

    ts.apply_suggested_tasks(gpt_output)

    return {"status": "ok", "source": event_payload["source"]}


# =========================================================
#  DEBUG-ENDPOINT FÖR ATL
# =========================================================

@router.get("/debug/atl")
def debug_atl() -> Dict[str, Any]:
    path = ai_suggestions.ATL_PATH
    file_exists = path.exists()

    rows_info: List[Dict[str, Any]] = []
    row_count: int = 0
    error: Optional[str] = None

    try:
        rows = ai_suggestions.load_atl_rows()
        row_count = len(rows)
        for r in rows[:5]:
            rows_info.append(
                {
                    "arbetsmoment": r.arbetsmoment,
                    "grupp": r.grupp,
                    "rad": r.rad,
                    "moment_text": r.moment_text,
                    "underlag_text": r.underlag_text,
                    "enhet": r.enhet,
                }
            )
    except Exception as e:  # noqa: BLE001
        error = str(e)

    return {
        "atl_path": str(path),
        "file_exists": file_exists,
        "row_count": row_count,
        "sample_rows": rows_info,
        "error": error,
    }


# =========================================================
#  DEBUG-ENDPOINT FÖR MAPPINGS
# =========================================================

@router.get("/debug/mapping")
def debug_mapping(category: str = "ovrigt") -> Dict[str, Any]:
    try:
        path = ts._category_to_mapping_path(category)
        data = ts._load_mapping_file(path)
        tasks = data.get("tasks") or []

        return {
            "category": category,
            "path": str(path),
            "tasks_count": len(tasks),
            "tasks": tasks,
        }
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))
