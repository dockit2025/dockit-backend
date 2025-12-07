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


class GPTTaskSuggestRequest(BaseModel):
    """
    Request till /sandbox/gpt-suggest-tasks.

    limit: hur många senaste missing_task-segment som ska tas med
           från missing_task_segments.jsonl (default 50).
    """
    limit: Optional[int] = 50


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
      - Returnera resultatet direkt till UI

    På så sätt får Sandbox exakt samma:
      - tasks + tolkad arbetstid (ATL/manual)
      - work/material-rader
      - materialpriser via pricing.get_price
      - interpretation-fältet med detaljer
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

    # Lägg till en liten markör så vi vet att svaret kommer från Sandlådan
    result["sandbox"] = True
    return result


# =========================================================
#  GPT-FÖRSLAG (missing_task_segments → GPT)
# =========================================================

@router.post("/gpt-suggest-tasks")
def gpt_suggest_tasks(payload: GPTTaskSuggestRequest) -> Dict[str, Any]:
    """
    Kör samma GPT-flöde som task_suggestions_review.py --gpt,
    men som HTTP-endpoint för Sandlådan.

    Viktigt:
      - Denna endpoint LOGGAR INTE något permanent.
      - Den returnerar bara förslag till UI.
      - När användaren klickar "Acceptera" ska /sandbox/accept-task användas.
    """
    limit = payload.limit or 50

    # 1) Bygg GPT-input från loggade missing_task-segment
    gpt_input: Dict[str, Any] = ts.build_gpt_input_from_missing_segments(limit=limit)
    segments: List[Dict[str, Any]] = gpt_input.get("segments") or []
    if not segments:
        return {
            "gpt_input": gpt_input,
            "suggested_tasks": [],
            "note": "Inga missing_task-segment hittades i loggen.",
        }

    # 2) Hämta spec + anropa GPT
    spec = load_task_generation_spec()
    client = AIClient()
    gpt_output: Dict[str, Any] = client.generate_tasks(spec=spec, gpt_input=gpt_input)

    raw_suggested = gpt_output.get("suggested_tasks") or []
    if not isinstance(raw_suggested, list):
        raw_suggested = []

    # 3) Filtrera bort tasks som redan finns i mappings
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

    # 4) Returnera data till Sandlådan (ingen loggning här)
    return {
        "gpt_input": gpt_input,
        "suggested_tasks": filtered,
    }


@router.post("/accept-task")
def accept_task(payload: AcceptTaskRequest) -> Dict[str, Any]:
    """
    Anropas när användaren klickar 'Acceptera' på en GPT-föreslagen task i Sandlådan.

    Sparar INTE direkt till YAML, utan loggar till task_suggestions.jsonl
    som en del av "förslagslistan" för senare review/patch.
    """
    task = payload.task or {}
    if not isinstance(task, dict) or not (task.get("task_ref") or "").strip():
        return {"status": "ignored", "reason": "Ogiltig eller tom task"}

    event_payload: Dict[str, Any] = {
        "source": payload.source or "sandbox_ui",
        "suggested_tasks": [task],
    }

    ts.log_task_suggestions(event_payload)

    return {"status": "ok", "source": event_payload["source"]}
