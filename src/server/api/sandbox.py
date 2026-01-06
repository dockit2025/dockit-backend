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
from src.services.atl_apply import resolve_mapping_path, load_mapping_yaml, find_task_in_mapping, confirm_apply_atl_ref


class GPTTaskSuggestRequest(BaseModel):
    """
    Request till /sandbox/gpt-suggest-tasks.

    limit:
      - hur många senaste missing_task-segment som ska tas med
        från missing_task_segments.jsonl (default 50).

    segments:
      - Om frontend skickar in en lista med rena texter (strängar),
        använder vi dessa direkt istället för att läsa från loggen.
    """
    limit: Optional[int] = 50
    segments: Optional[List[str]] = None


class GPTMatchTasksRequest(BaseModel):
    """
    Request till /sandbox/gpt-match-tasks (FAS 2).

    Antingen:
      - job_text: fri text som preprocessas via FAS 0 workplan (gpt-workplan)
      - segments: lista med rena segment-texter från UI
    """
    job_text: Optional[str] = None
    segments: Optional[List[str]] = None
    categories_hint: Optional[List[str]] = None


class GPTMatchAtlRequest(BaseModel):
    """
    Request till /sandbox/gpt-match-atl (ATL-Sandbox).

    items: lista av matchade tasks från FAS 2, där varje item innehåller:
      - segment_id
      - segment_text
      - task_id
      - label (valfri)
      - quantity
    """
    items: List[Dict[str, Any]]


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


class TextCleanerRequest(BaseModel):
    """
    Request till /sandbox/clean-text och /sandbox/gpt-extract-segments.

    Tar in en fri job_text och returnerar clean_segments enligt
    textrensar-specen.
    """
    job_text: str


class GPTWorkplanRequest(BaseModel):
    """
    Request till /sandbox/gpt-workplan (FAS 0).

    job_text:
      - Fri text från användaren (tal, felskrivningar, mängder).
    """
    job_text: str
    language: Optional[str] = "sv"
    context: Optional[Dict[str, Any]] = None


router = APIRouter(
    prefix="/sandbox",
    tags=["sandbox"],
    dependencies=[Depends(verify_api_key)],
)


# =========================================================
#  TOLKA JOBB (Sandbox → återanvänder /quotes/draft-logiken)
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
                # Hantera både segment_text och text i textrensar-output
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
#  GPT-SEGMENTERING – /sandbox/gpt-extract-segments (FAS 1)
# =========================================================

@router.post("/gpt-extract-segments")
def gpt_extract_segments(payload: TextCleanerRequest) -> Dict[str, Any]:
    """
    Tar in en fri job_text och använder samma textrensare som /sandbox/clean-text,
    men returnerar explicita segment med id + text.
    """
    job_text = (payload.job_text or "").strip()
    if not job_text:
        raise HTTPException(status_code=400, detail="job_text krävs")

    try:
        spec = load_text_cleaner_spec()
        client = AIClient()
        result = client.generate_text_segments(spec=spec, job_text=job_text)

        raw_segments = result.get("clean_segments") or []
        if not isinstance(raw_segments, list):
            raw_segments = []

        segments_out: List[Dict[str, Any]] = []

        for idx, item in enumerate(raw_segments, start=1):
            seg_id = f"seg_{idx:03d}"
            seg_text = ""

            if isinstance(item, dict):
                if "segment_text" in item:
                    seg_text = str(item.get("segment_text") or "").strip()
                elif "text" in item:
                    seg_text = str(item.get("text") or "").strip()
                else:
                    seg_text = str(item).strip()
            else:
                seg_text = str(item or "").strip()

            if not seg_text:
                continue

            segments_out.append(
                {
                    "segment_id": seg_id,
                    "segment_text": seg_text,
                }
            )

        return {"segments": segments_out}

    except FileNotFoundError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Text-cleaner-spec saknas: {e}",
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
#  GPT-WORKPLAN – /sandbox/gpt-workplan (FAS 0)
# =========================================================

@router.post("/gpt-workplan")
def gpt_workplan(payload: GPTWorkplanRequest) -> Dict[str, Any]:
    """
    FAS 0 (Sandbox-only):
      - Fri text -> arbetsplan + rena segment
      - Returnerar även antaganden och frågor
    """
    job_text = (payload.job_text or "").strip()
    if not job_text:
        raise HTTPException(status_code=400, detail="job_text krävs")

    from src.services.ai_workplan import generate_workplan

    try:
        result = generate_workplan(
            job_text=job_text,
            language=payload.language or "sv",
            context=payload.context,
        )
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
#  GPT-MATCH TASKS – /sandbox/gpt-match-tasks (FAS 2)
# =========================================================

@router.post("/gpt-match-tasks")
def gpt_match_tasks(payload: GPTMatchTasksRequest) -> Dict[str, Any]:
    """
    FAS 2: Matcha segments -> befintliga tasks (YAML) via GPT.

    Input:
      - segments: (UI) lista med segment-texter (används direkt)
      - job_text: (fri text) preprocessas via FAS 0 workplan och workplan.segments används
    """
    segments: List[Dict[str, Any]] = []

    if payload.segments:
        # UI skickar redan rena segments
        for i, s in enumerate(payload.segments, start=1):
            text = str(s or "").strip()
            if not text:
                continue
            segments.append({"segment_id": f"ui_{i:03d}", "segment_text": text})

    elif payload.job_text and str(payload.job_text).strip():
        # FAS 0: Workplan → använd dess segments
        from src.services.ai_workplan import generate_workplan

        wp = generate_workplan(job_text=str(payload.job_text).strip(), language="sv", context=None)
        wp_segments = wp.get("segments") or []
        if not isinstance(wp_segments, list):
            wp_segments = []

        for idx, item in enumerate(wp_segments, start=1):
            if isinstance(item, dict):
                sid = str(item.get("segment_id") or "").strip() or f"wp_{idx:03d}"
                stx = str(item.get("segment_text") or "").strip()
            else:
                sid = f"wp_{idx:03d}"
                stx = str(item or "").strip()

            if not stx:
                continue
            segments.append({"segment_id": sid, "segment_text": stx})

    else:
        raise HTTPException(status_code=400, detail="Antingen job_text eller segments krävs.")

    if not segments:
        return {"matches": [], "unmatched_segments": [], "note": "Inga segments att matcha."}

    from src.services.task_library import load_all_tasks_from_mappings
    all_tasks = load_all_tasks_from_mappings()

    from src.services.task_candidates import build_candidates_by_segment
    candidates_by_segment = build_candidates_by_segment(segments, all_tasks)

    from src.services.ai_task_matching import match_segments_to_tasks
    result = match_segments_to_tasks(
        segments=segments,
        candidates_by_segment=candidates_by_segment,
    )

    # -----------------------------------------------------
    #  Enrich matches med task-metadata (för spårbarhet i Sandbox)
    # -----------------------------------------------------
    try:
        task_by_id: Dict[str, Dict[str, Any]] = {
            str(t.get("task_id") or "").strip(): t for t in all_tasks if isinstance(t, dict) and (t.get("task_id") or "")
        }
        matches_tmp = result.get("matches")
        if isinstance(matches_tmp, list):
            for m in matches_tmp:
                if not isinstance(m, dict):
                    continue
                tid = str(m.get("matched_task_id") or "").strip()
                if not tid:
                    continue
                t = task_by_id.get(tid)
                if not t:
                    continue
                m["task_meta"] = {
                    "label": t.get("label"),
                    "category": t.get("category"),
                    "time_source": t.get("time_source"),
                    "atl_refs": t.get("atl_refs") or [],
                    "manual_time_minutes_per_unit": t.get("manual_time_minutes_per_unit"),
                    "mapping_file": t.get("_mapping_file"),
                }
    except Exception:
        # Sandbox ska inte krascha om metadata-enrichment strular
        pass

    # --- Safety normalization ---
    matches = result.get("matches")
    if not isinstance(matches, list):
        matches = []

    # 1) Se till att matched_task_id (om satt) finns bland kandidaterna för segmentet
    for m in matches:
        if not isinstance(m, dict):
            continue
        sid = (m.get("segment_id") or "").strip()
        mid = (m.get("matched_task_id") or "").strip()
        if not sid:
            continue
        cand_ids = {str(t.get("task_id") or "").strip() for t in (candidates_by_segment.get(sid) or [])}
        if mid and cand_ids and (mid not in cand_ids):
            # ogiltigt val -> tvinga unmatched
            m["matched_task_id"] = None
            m["needs_new_task"] = True
            m["confidence"] = min(float(m.get("confidence") or 0.0), 0.49)
            m["reason"] = (m.get("reason") or "") + " (Safety: matched_task_id fanns inte i kandidatlistan.)"

    # 2) Bygg unmatched_segments deterministiskt från matches
    unmatched: List[Dict[str, Any]] = []
    for m in matches:
        if not isinstance(m, dict):
            continue
        if m.get("needs_new_task") is True or not (m.get("matched_task_id") or ""):
            sid = m.get("segment_id")
            stx = m.get("segment_text")
            if sid and stx:
                unmatched.append({"segment_id": sid, "segment_text": stx})

    result["matches"] = matches
    result["unmatched_segments"] = unmatched
    return result


# =========================================================
#  GPT-MATCH ATL – /sandbox/gpt-match-atl (ATL-Sandbox)
# =========================================================

@router.post("/gpt-match-atl")
def gpt_match_atl(payload: GPTMatchAtlRequest) -> Dict[str, Any]:
    """
    ATL-Sandbox:
      - Tar in matchade items (segment_text + task_id + quantity)
      - Hämtar ATL-kandidater
      - Låter GPT välja moment+variant eller göra estimate
      - Returnerar results med confidence + explanation
    """
    items = payload.items or []
    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=400, detail="items krävs och måste vara en lista")

    # Bygg quantity-map så vi kan räkna totals på outputen
    qty_by_segment: Dict[str, float] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        sid = str(it.get("segment_id") or "").strip()
        if not sid:
            continue
        try:
            q = float(it.get("quantity", 1) or 1)
        except Exception:
            q = 1.0
        if q <= 0:
            q = 1.0
        qty_by_segment[sid] = q

    from src.services.ai_atl_selection import select_atl_for_items
    result = select_atl_for_items(items=items, max_rows_per_item=12)

    # Lägg till time_minutes_total per result
    results = result.get("results")
    if isinstance(results, list):
        for r in results:
            if not isinstance(r, dict):
                continue
            sid = str(r.get("segment_id") or "").strip()
            qty = qty_by_segment.get(sid, 1.0)
            try:
                per_unit = float(r.get("time_minutes_per_unit") or 0.0)
            except Exception:
                per_unit = 0.0
            r["quantity"] = qty
            r["time_minutes_total"] = round(per_unit * qty, 2)

    return result

# =========================================================
#  GPT-FÖRSLAG (missing_task_segments → GPT + ATL)
# =========================================================

@router.post("/gpt-suggest-tasks")
def gpt_suggest_tasks(payload: GPTTaskSuggestRequest) -> Dict[str, Any]:
    """
    Kör samma GPT-flöde som task_suggestions_review.py --gpt,
    men som HTTP-endpoint för Sandlådan.
    """
    limit = payload.limit or 50

    # -----------------------------------------------------
    # 1) Bestäm vilka segments vi skickar till GPT
    # -----------------------------------------------------
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
            continue

    if not filtered and payload.segments:
        note = (
            "GPT försökte matcha segmenten mot ATL men hittade inga nya "
            "arbetsmoment som inte redan finns i mappings."
        )

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
#  DEBUG-ENDPOINT FÖR ATL PÅ RENDER
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
#  DEBUG-ENDPOINT FÖR MAPPINGS (PÅ RENDER/LOKALT)
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


# =========================================================
#  ATL SEARCH – /sandbox/atl-search (admin, no GPT)
# =========================================================

@router.get("/atl-search")
def atl_search(q: str, max_rows: int = 20) -> Dict[str, Any]:
    """
    Admin-hjälp: Sök i ATL-listan (Del7_ATL_Total.csv) och returnera top-kandidater.
    Ingen GPT här – bara heuristisk textmatchning som stöd för admin.
    """
    query = (q or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="q (query) krävs")

    # rimliga bounds så man inte råkar få gigantiska svar
    try:
        max_rows_int = int(max_rows)
    except Exception:
        max_rows_int = 20
    max_rows_int = max(1, min(50, max_rows_int))

    from src.services.ai_suggestions import find_atl_candidates_for_segment

    rows = find_atl_candidates_for_segment(
        segment_text=query,
        max_rows=max_rows_int,
        min_score=0.01,
    )

    out_rows: List[Dict[str, Any]] = []
    for r in rows:
        out_rows.append(
            {
                "arbetsmoment": r.arbetsmoment,
                "moment_id": r.id_str,
                "grupp": r.grupp,
                "rad": r.rad,
                "moment_text": r.moment_text,
                "underlag_text": r.underlag_text,
                "enhet": r.enhet,
                "times": r.times,
            }
        )

    return {
        "query": query,
        "max_rows": max_rows_int,
        "count": len(out_rows),
        "rows": out_rows,
    }



# =========================================================
#  GPT-ATL-RANK – /sandbox/gpt-atl-rank (Admin)
# =========================================================

class GPTAtlRankRequest(BaseModel):
    """
    Admin-request för att föreslå ATL-referens för en task.
    """
    task: Dict[str, Any]
    segment_text: str
    max_rows: Optional[int] = 25


class AtlApplyPreviewRequest(BaseModel):
    """
    Admin-request för att preview:a att en vald ATL-referens kan appliceras på en befintlig task.

    Viktigt:
    - Ingen fil skrivs i preview.
    - mapping_file ska komma från server-side task_meta, men vi validerar defensivt ändå.
    """
    task_id: str
    mapping_file: str
    moment_id: str
    variant: int


@router.post("/gpt-atl-rank")
def gpt_atl_rank(payload: GPTAtlRankRequest) -> Dict[str, Any]:
    """
    Admin-only:
    Föreslå ATL moment + variant för en task baserat på segment-text.
    """
    if not payload.task or not payload.segment_text:
        raise HTTPException(status_code=400, detail="task och segment_text krävs")

    from src.services.ai_atl_rank import suggest_atl_ref_for_task

    try:
        result = suggest_atl_ref_for_task(
            task=payload.task,
            segment_text=payload.segment_text,
            max_rows=payload.max_rows or 25,
        )
        return result
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
#  ATL APPLY (PREVIEW) – /sandbox/atl-apply-preview (Admin)
# =========================================================

@router.post("/atl-apply-preview")
def atl_apply_preview(payload: AtlApplyPreviewRequest) -> Dict[str, Any]:
    """
    Admin-only preview:
    - Validerar mapping_file
    - Verifierar att task_id finns i filen
    - Slår upp moment_text via ATL (moment_id -> moment_text)
    - Returnerar en "plan" för write (utan att skriva)
    """
    try:
        task_id = (payload.task_id or "").strip()
        mapping_file = (payload.mapping_file or "").strip()
        moment_id = (payload.moment_id or "").strip()
        variant = int(payload.variant)

        if not task_id or not mapping_file or not moment_id:
            raise HTTPException(status_code=400, detail="task_id, mapping_file, moment_id och variant krävs")

        # 1) Resolve + load mapping
        path = resolve_mapping_path(mapping_file)
        root = load_mapping_yaml(path)

        # 2) Hitta task i filen (måste finnas)
        task, meta = find_task_in_mapping(mapping_root=root, task_id=task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"task_id '{task_id}' hittades inte i {mapping_file}")

        # 3) moment_id -> moment_text (Moment/Typ/Sort)
        # ai_suggestions använder arbetsmoment-numret som id_str
        rows = ai_suggestions.load_atl_rows()
        moment_text = None
        for r in rows:
            if getattr(r, "id_str", None) == moment_id:
                moment_text = getattr(r, "moment_text", None)
                break

        if not moment_text:
            raise HTTPException(status_code=404, detail=f"moment_id '{moment_id}' hittades inte i ATL-data")

        # 4) Kontroll: går det att slå upp tid med moment_text + variant?
        minutes_per_unit = get_atl_time_minutes(moment_text, variant)

        return {
            "status": "ok",
            "task_id": task_id,
            "mapping_file": mapping_file,
            "mapping_path": str(path),
            "tasks_container_type": meta.get("tasks_container_type"),
            "atl_ref": {"moment": moment_text, "variant": variant, "moment_id": moment_id},
            "time_minutes_per_unit": minutes_per_unit,
            "note": "Preview only. Ingen fil är skriven.",
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
#  ATL APPLY (CONFIRM) – /sandbox/atl-apply-confirm (Admin)
# =========================================================

class AtlApplyConfirmRequest(BaseModel):
    """
    Admin-request för att confirm:a (skriva) en vald ATL-referens till mapping-YAML.

    Viktigt:
    - Detta gör faktisk write + backup.
    - mapping_file ska komma från server-side task_meta, men vi validerar defensivt ändå.
    """
    task_id: str
    mapping_file: str
    moment_id: str
    variant: int


@router.post("/atl-apply-confirm")
def atl_apply_confirm(payload: AtlApplyConfirmRequest) -> Dict[str, Any]:
    """
    Admin-only confirm:
    - Validerar mapping_file
    - Verifierar att task_id finns i filen
    - Slår upp moment_text via ATL (moment_id -> moment_text)
    - Skapar backup
    - Skriver ATL-ref till YAML + re-read validate
    """
    try:
        task_id = (payload.task_id or "").strip()
        mapping_file = (payload.mapping_file or "").strip()
        moment_id = (payload.moment_id or "").strip()
        variant = int(payload.variant)

        if not task_id or not mapping_file or not moment_id:
            raise HTTPException(status_code=400, detail="task_id, mapping_file, moment_id och variant krävs")

        # moment_id -> moment_text (Moment/Typ/Sort)
        rows = ai_suggestions.load_atl_rows()
        moment_text = None
        for r in rows:
            if getattr(r, "id_str", None) == moment_id:
                moment_text = getattr(r, "moment_text", None)
                break

        if not moment_text:
            raise HTTPException(status_code=404, detail=f"moment_id '{moment_id}' hittades inte i ATL-data")

        # Gör write + backup + verify
        res = confirm_apply_atl_ref(
            task_id=task_id,
            mapping_file=mapping_file,
            moment_text=moment_text,
            variant=variant,
        )

        # Extra: returnera även ATL-tid för transparens
        minutes_per_unit = get_atl_time_minutes(moment_text, variant)

        return {
            **res,
            "atl_ref": {"moment": moment_text, "variant": variant, "moment_id": moment_id},
            "time_minutes_per_unit": minutes_per_unit,
            "note": "CONFIRM: filen är skriven och verifierad.",
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
#  ADMIN QUEUE – /sandbox/admin/task-queue (read-only)
# =========================================================

@router.get("/admin/task-queue")
def admin_task_queue(min_count: int = 1, limit: int = 50) -> Dict[str, Any]:
    """
    Read-only: summerar återkommande missing_task_segments som en admin-kö.
    Används för att besluta vad som ska bli tasks (kontrollerad självlärning).
    """
    return ts.summarize_missing_task_segments(min_count=min_count, limit=limit)

