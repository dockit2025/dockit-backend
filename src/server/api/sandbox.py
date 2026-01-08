from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlmodel import select

from src.server.api.quotes import verify_api_key
from src.server.db.session import get_session
from src.server.schemas.quote import QuoteDraftIn
from src.server.models.missing_task_segment import MissingTaskSegment
from src.services.quote_service import make_draft
from src.services.ai_client import AIClient
from src.services.ai_specs import load_task_generation_spec, load_text_cleaner_spec
from src.services import task_suggestions as ts
from src.services import ai_suggestions  # ATL-hjälp
from src.services.atl_lookup import get_atl_time_minutes
from src.services.atl_apply import (
    resolve_mapping_path,
    load_mapping_yaml,
    find_task_in_mapping,
    confirm_apply_atl_ref,
)


# =========================================================
# Safety: mapping writes (mappings/*.yaml)
# =========================================================
def _mapping_writes_enabled() -> bool:
    """
    Default: DISABLED.
    Enable explicit via env:
      DOCKIT_ALLOW_MAPPING_WRITES=true (or 1/yes/on)
    """
    v = (os.getenv("DOCKIT_ALLOW_MAPPING_WRITES") or "").strip().lower()
    return v in {"1", "true", "yes", "on"}


def _ensure_mapping_writes_allowed() -> None:
    if not _mapping_writes_enabled():
        raise HTTPException(
            status_code=403,
            detail="Mapping writes are disabled. Set DOCKIT_ALLOW_MAPPING_WRITES=true to enable.",
        )


# =========================================================
# DB helpers: MissingTaskSegment (admin queue, threshold-gating)
# =========================================================
def _normalize_segment_key(text: str) -> str:
    s = (text or "").strip().lower()
    s = " ".join(s.split())  # collapse whitespace
    return s


def _record_missing_segments_in_db(session: Session, segments: List[str]) -> None:
    """
    Upsertar MissingTaskSegment-rader (count + last_seen_utc + example).
    Fail-safe: caller ska fånga exception (vi vill inte stoppa /sandbox/interpret).
    """
    if not segments:
        return

    now = datetime.now(timezone.utc)

    # Dedup per request: räkna occurrences i denna request (så vi inte gör N queries för samma text)
    per_key: Dict[str, Dict[str, Any]] = {}
    for s in segments:
        example = str(s or "").strip()
        if not example:
            continue
        key = _normalize_segment_key(example)
        if not key:
            continue
        entry = per_key.get(key)
        if not entry:
            per_key[key] = {"example": example, "inc": 1}
        else:
            entry["inc"] = int(entry.get("inc", 0)) + 1
            # uppdatera exempel till senaste i listan (mest relevant för admin)
            entry["example"] = example

    if not per_key:
        return

    for key, meta in per_key.items():
        inc = int(meta.get("inc", 1))
        example = str(meta.get("example") or "")

        # 1) Läs befintlig
        row = None
        try:
            # SQLModel Session har .exec; men Session här är kompatibel i runtime.
            if hasattr(session, "exec"):
                row = session.exec(
                    select(MissingTaskSegment).where(MissingTaskSegment.segment_key == key)
                ).first()
            else:
                row = session.execute(
                    select(MissingTaskSegment).where(MissingTaskSegment.segment_key == key)
                ).scalars().first()
        except Exception:
            row = None

        if row:
            row.count = int(row.count or 0) + inc
            row.example = example or row.example or ""
            row.last_seen_utc = now
            session.add(row)
        else:
            session.add(
                MissingTaskSegment(
                    segment_key=key,
                    example=example or key,
                    count=inc,
                    first_seen_utc=now,
                    last_seen_utc=now,
                )
            )

    session.commit()


def _db_task_queue(session: Session, *, min_count: int, limit: int) -> Dict[str, Any]:
    """
    Läser admin-kö från DB.
    """
    # total_unique
    total_unique = 0
    try:
        if hasattr(session, "exec"):
            total_unique = int(session.exec(select(func.count()).select_from(MissingTaskSegment)).one())
        else:
            total_unique = int(session.execute(select(func.count()).select_from(MissingTaskSegment)).scalar() or 0)
    except Exception:
        total_unique = 0

    # rows
    stmt = (
        select(MissingTaskSegment)
        .where(MissingTaskSegment.count >= min_count)
        .order_by(MissingTaskSegment.count.desc(), MissingTaskSegment.last_seen_utc.desc())
        .limit(limit)
    )

    if hasattr(session, "exec"):
        rows = session.exec(stmt).all()
    else:
        rows = session.execute(stmt).scalars().all()

    items: List[Dict[str, Any]] = []
    for r in rows:
        last_seen = getattr(r, "last_seen_utc", None)
        if isinstance(last_seen, datetime):
            last_seen_ts = last_seen.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        else:
            last_seen_ts = None

        items.append(
            {
                "segment_key": r.segment_key,
                "example": r.example,
                "count": int(r.count or 0),
                "last_seen_ts": last_seen_ts,
            }
        )

    return {
        "min_count": min_count,
        "limit": limit,
        "total_unique": total_unique,
        "returned": len(items),
        "items": items,
    }


# =========================================================
# Request models
# =========================================================
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
    """
    job_summary: Optional[str] = None
    text: Optional[str] = None
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None
    apply_rot: bool = False  # Sandbox: som standard ingen ROT här


class TextCleanerRequest(BaseModel):
    job_text: str


class GPTWorkplanRequest(BaseModel):
    job_text: str
    language: Optional[str] = "sv"
    context: Optional[Dict[str, Any]] = None


class GPTAtlRankRequest(BaseModel):
    task: Dict[str, Any]
    segment_text: str
    max_rows: Optional[int] = 25


class AtlApplyPreviewRequest(BaseModel):
    task_id: str
    mapping_file: str
    moment_id: str
    variant: int


class AtlApplyConfirmRequest(BaseModel):
    task_id: str
    mapping_file: str
    moment_id: str
    variant: int


# =========================================================
# Router
# =========================================================
router = APIRouter(
    prefix="/sandbox",
    tags=["sandbox"],
    dependencies=[Depends(verify_api_key)],
)


# =========================================================
# /sandbox/interpret (UI använder denna i prod idag)
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
    filtered_missing: List[str] = []
    try:
        interpretation = result.get("interpretation") or {}
        raw_missing = interpretation.get("missing_segments") or []

        if isinstance(raw_missing, list):
            for s in raw_missing:
                text = str(s or "").strip()
                if not text:
                    continue

                lower = text.lower()
                words = lower.split()

                if words and words[0] in {"hej", "hejsan", "tjena"} and len(words) <= 5:
                    continue
                if "tack" in words and len(words) <= 6:
                    continue

                filtered_missing.append(text)

            interpretation["missing_segments"] = filtered_missing
            result["interpretation"] = interpretation
    except Exception:
        # vi vill inte att /sandbox/interpret kraschar för "rensningen"
        pass

    # DB-backed admin queue: upserta missing segments (fail-safe)
    if filtered_missing:
        try:
            _record_missing_segments_in_db(session=session, segments=filtered_missing)
        except Exception:
            # fail-safe: påverka inte runtime
            pass

    result["sandbox"] = True
    return result


# =========================================================
# /sandbox/clean-text
# =========================================================
@router.post("/clean-text")
def sandbox_clean_text(payload: TextCleanerRequest) -> Dict[str, Any]:
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
            if isinstance(item, dict):
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
        raise HTTPException(status_code=500, detail=f"Text-cleaner-spec saknas: {e}")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
# /sandbox/gpt-extract-segments (FAS 1)
# =========================================================
@router.post("/gpt-extract-segments")
def gpt_extract_segments(payload: TextCleanerRequest) -> Dict[str, Any]:
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

            segments_out.append({"segment_id": seg_id, "segment_text": seg_text})

        return {"segments": segments_out}
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Text-cleaner-spec saknas: {e}")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
# /sandbox/gpt-workplan (FAS 0)
# =========================================================
@router.post("/gpt-workplan")
def gpt_workplan(payload: GPTWorkplanRequest) -> Dict[str, Any]:
    job_text = (payload.job_text or "").strip()
    if not job_text:
        raise HTTPException(status_code=400, detail="job_text krävs")

    from src.services.ai_workplan import generate_workplan

    try:
        return generate_workplan(
            job_text=job_text,
            language=payload.language or "sv",
            context=payload.context,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
# /sandbox/gpt-match-tasks (FAS 2)
# =========================================================
@router.post("/gpt-match-tasks")
def gpt_match_tasks(payload: GPTMatchTasksRequest) -> Dict[str, Any]:
    segments: List[Dict[str, Any]] = []

    if payload.segments:
        for i, s in enumerate(payload.segments, start=1):
            text = str(s or "").strip()
            if not text:
                continue
            segments.append({"segment_id": f"ui_{i:03d}", "segment_text": text})

    elif payload.job_text and str(payload.job_text).strip():
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
    result = match_segments_to_tasks(segments=segments, candidates_by_segment=candidates_by_segment)

    # Enrich matches med task-metadata (spårbarhet)
    try:
        task_by_id: Dict[str, Dict[str, Any]] = {
            str(t.get("task_id") or "").strip(): t
            for t in all_tasks
            if isinstance(t, dict) and (t.get("task_id") or "")
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
        pass

    # Safety normalization
    matches = result.get("matches")
    if not isinstance(matches, list):
        matches = []

    for m in matches:
        if not isinstance(m, dict):
            continue
        sid = (m.get("segment_id") or "").strip()
        mid = (m.get("matched_task_id") or "").strip()
        if not sid:
            continue
        cand_ids = {str(t.get("task_id") or "").strip() for t in (candidates_by_segment.get(sid) or [])}
        if mid and cand_ids and (mid not in cand_ids):
            m["matched_task_id"] = None
            m["needs_new_task"] = True
            m["confidence"] = min(float(m.get("confidence") or 0.0), 0.49)
            m["reason"] = (m.get("reason") or "") + " (Safety: matched_task_id fanns inte i kandidatlistan.)"

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
# /sandbox/gpt-match-atl (ATL-Sandbox)
# =========================================================
@router.post("/gpt-match-atl")
def gpt_match_atl(payload: GPTMatchAtlRequest) -> Dict[str, Any]:
    items = payload.items or []
    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=400, detail="items krävs och måste vara en lista")

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
# /sandbox/gpt-suggest-tasks (missing segments -> GPT + ATL)
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
        gpt_input: Dict[str, Any] = ai_suggestions.build_gpt_input_with_atl_for_segments(segments)
    else:
        base_input: Dict[str, Any] = ts.build_gpt_input_from_missing_segments(limit=limit)
        segments = base_input.get("segments") or []

        if not segments:
            return {"gpt_input": base_input, "suggested_tasks": [], "note": "Inga missing_task-segment hittades i loggen."}

        atl_enriched = ai_suggestions.build_gpt_input_with_atl_for_segments(segments)
        gpt_input = {**base_input, "atl_candidates": atl_enriched.get("atl_candidates", [])}

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

    # Sätt ATL-tider om atl_moment/atl_variant finns
    for s in filtered:
        try:
            atl_moment = (s.get("atl_moment") or "").strip()
            atl_variant = s.get("atl_variant")
            if not (atl_moment and atl_variant is not None):
                continue

            variant_int = int(atl_variant)
            minutes = get_atl_time_minutes(atl_moment, variant_int)
            if minutes and minutes > 0:
                s["time_source"] = "atl"
                s["time_minutes_per_unit"] = minutes
        except Exception:
            continue

    if not filtered and payload.segments:
        note = "GPT försökte matcha segmenten mot ATL men hittade inga nya arbetsmoment som inte redan finns i mappings."

    return {"gpt_input": gpt_input, "suggested_tasks": filtered, "note": note}


# =========================================================
# /sandbox/accept-task (writes mappings) — GUARDED
# =========================================================
@router.post("/accept-task")
def accept_task(payload: AcceptTaskRequest) -> Dict[str, Any]:
    _ensure_mapping_writes_allowed()

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
# Debug endpoints
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


@router.get("/debug/mapping")
def debug_mapping(category: str = "ovrigt") -> Dict[str, Any]:
    try:
        path = ts._category_to_mapping_path(category)
        data = ts._load_mapping_file(path)
        tasks = data.get("tasks") or []
        return {"category": category, "path": str(path), "tasks_count": len(tasks), "tasks": tasks}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
# /sandbox/atl-search (admin, no GPT)
# =========================================================
@router.get("/atl-search")
def atl_search(q: str, max_rows: int = 20) -> Dict[str, Any]:
    query = (q or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="q (query) krävs")

    try:
        max_rows_int = int(max_rows)
    except Exception:
        max_rows_int = 20
    max_rows_int = max(1, min(50, max_rows_int))

    from src.services.ai_suggestions import find_atl_candidates_for_segment

    rows = find_atl_candidates_for_segment(segment_text=query, max_rows=max_rows_int, min_score=0.01)

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

    return {"query": query, "max_rows": max_rows_int, "count": len(out_rows), "rows": out_rows}


# =========================================================
# /sandbox/gpt-atl-rank (Admin)
# =========================================================
@router.post("/gpt-atl-rank")
def gpt_atl_rank(payload: GPTAtlRankRequest) -> Dict[str, Any]:
    if not payload.task or not payload.segment_text:
        raise HTTPException(status_code=400, detail="task och segment_text krävs")

    from src.services.ai_atl_rank import suggest_atl_ref_for_task

    try:
        return suggest_atl_ref_for_task(
            task=payload.task,
            segment_text=payload.segment_text,
            max_rows=payload.max_rows or 25,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
# /sandbox/atl-apply-preview (Admin, no write)
# =========================================================
@router.post("/atl-apply-preview")
def atl_apply_preview(payload: AtlApplyPreviewRequest) -> Dict[str, Any]:
    try:
        task_id = (payload.task_id or "").strip()
        mapping_file = (payload.mapping_file or "").strip()
        moment_id = (payload.moment_id or "").strip()
        variant = int(payload.variant)

        if not task_id or not mapping_file or not moment_id:
            raise HTTPException(status_code=400, detail="task_id, mapping_file, moment_id och variant krävs")

        path = resolve_mapping_path(mapping_file)
        root = load_mapping_yaml(path)

        task, meta = find_task_in_mapping(mapping_root=root, task_id=task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"task_id '{task_id}' hittades inte i {mapping_file}")

        rows = ai_suggestions.load_atl_rows()
        moment_text = None
        for r in rows:
            if getattr(r, "id_str", None) == moment_id:
                moment_text = getattr(r, "moment_text", None)
                break

        if not moment_text:
            raise HTTPException(status_code=404, detail=f"moment_id '{moment_id}' hittades inte i ATL-data")

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
# /sandbox/atl-apply-confirm (Admin, writes mappings) — GUARDED
# =========================================================
@router.post("/atl-apply-confirm")
def atl_apply_confirm(payload: AtlApplyConfirmRequest) -> Dict[str, Any]:
    _ensure_mapping_writes_allowed()

    try:
        task_id = (payload.task_id or "").strip()
        mapping_file = (payload.mapping_file or "").strip()
        moment_id = (payload.moment_id or "").strip()
        variant = int(payload.variant)

        if not task_id or not mapping_file or not moment_id:
            raise HTTPException(status_code=400, detail="task_id, mapping_file, moment_id och variant krävs")

        rows = ai_suggestions.load_atl_rows()
        moment_text = None
        for r in rows:
            if getattr(r, "id_str", None) == moment_id:
                moment_text = getattr(r, "moment_text", None)
                break

        if not moment_text:
            raise HTTPException(status_code=404, detail=f"moment_id '{moment_id}' hittades inte i ATL-data")

        res = confirm_apply_atl_ref(
            task_id=task_id,
            mapping_file=mapping_file,
            moment_text=moment_text,
            variant=variant,
        )

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
# /sandbox/admin/task-queue (read-only)
# =========================================================
@router.get("/admin/task-queue")
def admin_task_queue(
    min_count: int = 1,
    limit: int = 50,
    exclude_prefixes: Optional[str] = None,
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """
    Read-only admin-kö.

    Primärt: DB-backed (MissingTaskSegment).
    Fallback: ts.summarize_missing_task_segments (jsonl) om DB inte fungerar.

    exclude_prefixes:
      - kommaseparerad lista av prefix att dölja, t.ex. "zz_,test_"
    """
    try:
        min_count_int = int(min_count)
    except Exception:
        min_count_int = 1
    min_count_int = max(1, min_count_int)

    try:
        limit_int = int(limit)
    except Exception:
        limit_int = 50
    limit_int = max(1, min(200, limit_int))

    prefixes: List[str] = []
    raw = (exclude_prefixes or "").strip()
    if raw:
        prefixes = [p.strip().lower() for p in raw.split(",") if p.strip()]

    def _apply_filter(out: Dict[str, Any]) -> Dict[str, Any]:
        if not prefixes:
            return out
        items = out.get("items") or []
        if not isinstance(items, list):
            items = []
        before = len(items)
        filtered = []
        for it in items:
            key = str((it or {}).get("segment_key") or "").strip().lower()
            if not key:
                continue
            if any(key.startswith(p) for p in prefixes):
                continue
            filtered.append(it)
        out["items"] = filtered
        out["returned"] = len(filtered)
        out["filtered_out"] = before - len(filtered)
        out["exclude_prefixes"] = prefixes
        return out

    try:
        out = _db_task_queue(session=session, min_count=min_count_int, limit=limit_int)
    except Exception:
        out = ts.summarize_missing_task_segments(min_count=min_count_int, limit=limit_int)

    return _apply_filter(out)
