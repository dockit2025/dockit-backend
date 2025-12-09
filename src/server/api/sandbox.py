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
from src.services.ai_specs import load_task_generation_spec
from src.services import task_suggestions as ts
from src.services import ai_suggestions  # NYTT – ATL-hjälp
from src.services.atl_lookup import get_atl_time_minutes


class GPTTaskSuggestRequest(BaseModel):
    """
    Request till /sandbox/gpt-suggest-tasks.

    limit:
      - hur många senaste missing_task-segment som ska tas med
        från missing_task_segments.jsonl (default 50).

    segments: (NYTT)
      - Om frontend skickar in en lista med rena texter (strängar),
        använder vi dessa direkt istället för att läsa från loggen.
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

    Vi stödjer både:
      - job_summary
      - text
    så att frontend kan skicka vilket som.
    """
    job_summary: Optional[str] = None
    text: Optional[str] = None
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None
    apply_rot: bool = False  # Sandbox: som standard ingen ROT här


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
    """
    Tolkning av fri text i Sandlådan.

    Flöde:
      - Plocka ut job_summary (eller text)
      - Bygg ett QuoteDraftIn med tomma lines
      - Anropa make_draft → samma logik som i /quotes/draft
      - Rensa missing_segments från uppenbart brus (hej/tack)
      - Returnera resultatet direkt till UI
    """
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

                # Filtrera bort korta hälsningar, t.ex. "hej", "hej kunden"
                if words and words[0] in {"hej", "hejsan", "tjena"} and len(words) <= 5:
                    continue

                # Filtrera bort korta tackfraser, t.ex. "tack på förhand"
                if "tack" in words and len(words) <= 6:
                    continue

                filtered_missing.append(text)

            interpretation["missing_segments"] = filtered_missing
            result["interpretation"] = interpretation
    except Exception:
        # Vi vill inte att Sandlådan kraschar bara för att rensningen strular
        pass

    # Lägg till en liten markör så vi vet att svaret kommer från Sandlådan
    result["sandbox"] = True
    return result


# =========================================================
#  GPT-FÖRSLAG (missing_task_segments → GPT + ATL)
# =========================================================

@router.post("/gpt-suggest-tasks")
def gpt_suggest_tasks(payload: GPTTaskSuggestRequest) -> Dict[str, Any]:
    """
    Kör samma GPT-flöde som task_suggestions_review.py --gpt,
    men som HTTP-endpoint för Sandlådan.

    ATL-first-tanke:
      - Om payload.segments finns → använd JUST dessa segments
        (t.ex. de missing_segments som kom från det här jobbet),
        bygg GPT-input med ATL-kandidater via ai_suggestions.
      - Annars → läs som tidigare från missing_task_segments-loggen
        och berika med ATL-kandidater där också.

    Viktigt:
      - Denna endpoint LOGGAR INTE något permanent.
      - Den returnerar bara förslag till UI.
      - När användaren klickar "Acceptera" ska /sandbox/accept-task användas.
    """
    limit = payload.limit or 50

    # -----------------------------------------------------
    # 1) Bestäm vilka segments vi skickar till GPT
    # -----------------------------------------------------
    segments: List[Dict[str, Any]] = []
    note: Optional[str] = None

    if payload.segments:
        # Frontend har skickat in segment-texter direkt.
        # Bygg upp segment-objekt i samma format som logg-baserade.
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

        # Bygg GPT-input baserat på dessa segments + ATL-kandidater
        gpt_input: Dict[str, Any] = ai_suggestions.build_gpt_input_with_atl_for_segments(
            segments
        )
    else:
        # Behåll befintligt beteende: bygg GPT-input från loggade missing_task-segment
        base_input: Dict[str, Any] = ts.build_gpt_input_from_missing_segments(limit=limit)
        segments = base_input.get("segments") or []

        if not segments:
            return {
                "gpt_input": base_input,
                "suggested_tasks": [],
                "note": "Inga missing_task-segment hittades i loggen.",
            }

        # Berika med ATL-kandidater för dessa segments
        atl_enriched = ai_suggestions.build_gpt_input_with_atl_for_segments(segments)
        gpt_input = {**base_input, "atl_candidates": atl_enriched.get("atl_candidates", [])}

    if not segments:
        return {
            "gpt_input": gpt_input,
            "suggested_tasks": [],
            "note": "Inga segments skickades in och inga missing_task-segment hittades i loggen.",
        }

    # -----------------------------------------------------
    # 2) Hämta spec + anropa GPT
    # -----------------------------------------------------
    spec = load_task_generation_spec()
    client = AIClient()
    gpt_output: Dict[str, Any] = client.generate_tasks(spec=spec, gpt_input=gpt_input)

    raw_suggested = gpt_output.get("suggested_tasks") or []
    if not isinstance(raw_suggested, list):
        raw_suggested = []

    # -----------------------------------------------------
    # 3) Filtrera bort tasks som redan finns i mappings
    # -----------------------------------------------------
    filtered: List[Dict[str, Any]] = []

    # Cache för redan laddade mapping-filer per path
    existing_tasks_cache: Dict[str, List[Dict[str, Any]]] = {}

    for s in raw_suggested:
        if not isinstance(s, dict):
            continue

        task_ref = (s.get("task_ref") or "").strip()
        category = (s.get("category") or "ovrigt").strip() or "ovrigt"

        if not task_ref:
            continue

        # Hoppa över dubbletter inom samma GPT-svar
        if any((t.get("task_ref") or "").strip() == task_ref for t in filtered):
            continue

        # Hitta rätt mapping-fil för kategorin
        path = ts._category_to_mapping_path(category)
        key = str(path)

        if key not in existing_tasks_cache:
            data = ts._load_mapping_file(path)
            existing_tasks_cache[key] = data.get("tasks") or []

        # Hoppa över om task_id redan finns i befintlig YAML
        if ts._task_exists(existing_tasks_cache[key], task_ref):
            continue

        filtered.append(s)

    # -----------------------------------------------------
    # 3b) Sätt ATL-tider på förslagen om atl_moment/atl_variant finns
    # -----------------------------------------------------
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
            # Vi ignorerar fel här så att ett enskilt fel inte stoppar hela svaret
            continue

    if not filtered and payload.segments:
        note = (
            "GPT försökte matcha segmenten mot ATL men hittade inga nya "
            "arbetsmoment som inte redan finns i mappings."
        )

    # -----------------------------------------------------
    # 4) Returnera data till Sandlådan (ingen loggning här)
    # -----------------------------------------------------
    return {
        "gpt_input": gpt_input,
        "suggested_tasks": filtered,
        "note": note,
    }


@router.post("/accept-task")
def accept_task(payload: AcceptTaskRequest) -> Dict[str, Any]:
    """
    Anropas när användaren klickar 'Acceptera' på en GPT-föreslagen task i Sandlådan.

    Nu:
      - Loggar händelsen till task_suggestions.jsonl
      - Skriver direkt in arbetsmomentet i mappings/*
        via apply_suggested_tasks, med ATL-tider om de finns.
    """
    task = payload.task or {}
    if not isinstance(task, dict) or not (task.get("task_ref") or "").strip():
        return {"status": "ignored", "reason": "Ogiltig eller tom task"}

    # Bygg GPT-lik struktur som apply_suggested_tasks förstår
    gpt_output: Dict[str, Any] = {
        "suggested_tasks": [task],
    }

    # 1) Logga till task_suggestions.jsonl (för historik/spårbarhet)
    event_payload: Dict[str, Any] = {
        "source": payload.source or "sandbox_ui",
        "suggested_tasks": [task],
    }
    ts.log_task_suggestions(event_payload)

    # 2) Skriv direkt till YAML-mappings
    ts.apply_suggested_tasks(gpt_output)

    return {"status": "ok", "source": event_payload["source"]}
