from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.services.ai_client import AIClient
from src.services.ai_specs import load_atl_selection_spec
from src.services import ai_suggestions
from src.services.task_library import load_all_tasks_from_mappings


_TASKS_CACHE: Optional[Dict[str, Dict[str, Any]]] = None


def _get_task_by_id(task_id: str) -> Optional[Dict[str, Any]]:
    global _TASKS_CACHE
    if _TASKS_CACHE is None:
        tasks = load_all_tasks_from_mappings()
        _TASKS_CACHE = {}
        for t in tasks:
            tid = str(t.get("task_id") or "").strip()
            if tid:
                _TASKS_CACHE[tid] = t
    return _TASKS_CACHE.get(task_id)


def _row_to_candidate_payload(row: ai_suggestions.ATLRow) -> Dict[str, Any]:
    return {
        "arbetsmoment": row.arbetsmoment,
        "rad": row.rad,
        "moment_text": row.moment_text,
        "underlag_text": row.underlag_text,
        "enhet": row.enhet,
        "times": row.times,
    }


def _row_text(row: ai_suggestions.ATLRow) -> str:
    return f"{row.moment_text} {row.underlag_text} {row.enhet}".lower()


def _is_tillagg(row: ai_suggestions.ATLRow) -> bool:
    t = _row_text(row)
    return "tillägg" in t or "tillagg" in t


def _boost_score(seg_text: str, task_id: str, row: ai_suggestions.ATLRow) -> float:
    s = 0.0
    seg = (seg_text or "").lower()
    tid = (task_id or "").lower()
    txt = _row_text(row)

    wants_vp = ("vp" in seg) or ("vp-" in seg) or ("vp_r" in tid) or ("vp" in tid)
    wants_infallt = ("infäll" in seg) or ("infal" in seg) or ("infällt" in seg) or ("infälld" in seg)
    wants_vagg = ("vägg" in seg) or ("vagg" in seg) or ("vagg" in tid) or ("vägg" in tid)

    if wants_vp and ("vp" in txt):
        s += 0.30
    if wants_infallt and ("infäll" in txt or "infal" in txt):
        s += 0.20
    if wants_vagg and ("vägg" in txt or "vagg" in txt):
        s += 0.10

    if _is_tillagg(row) and (wants_vp or wants_infallt or wants_vagg):
        s -= 0.25

    return s


def _pick_candidates(search_text: str, seg_text: str, task_id: str, max_rows: int) -> List[ai_suggestions.ATLRow]:
    base = ai_suggestions.find_atl_candidates_for_segment(
        segment_text=search_text,
        max_rows=max_rows * 3,
        min_score=0.0,
    )

    scored = []
    for r in base:
        sim = ai_suggestions._similarity_score(search_text, r)  # type: ignore[attr-defined]
        score = sim + _boost_score(seg_text, task_id, r)
        scored.append((score, r))

    scored.sort(key=lambda x: x[0], reverse=True)
    ranked = [r for _, r in scored]

    non_tillagg = [r for r in ranked if not _is_tillagg(r)]
    if len(non_tillagg) >= 3:
        ranked = non_tillagg

    return ranked[:max_rows]


def _manual_minutes_for_task(task_id: str) -> Optional[float]:
    t = _get_task_by_id(task_id)
    if not isinstance(t, dict):
        return None
    mt = t.get("manual_time_minutes_per_unit")
    try:
        mt_val = float(mt) if mt is not None else None
    except Exception:
        mt_val = None
    if mt_val is not None and mt_val > 0:
        return mt_val
    return None


def _apply_manual_fallback(results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fallback-regel:
    1) Om GPT säger needs_estimate=true och manual tid finns -> manual_fallback (yellow)
    2) Om GPT väljer ATL men confidence_level är gul/röd och manual tid finns -> OVERRIDE till manual_fallback (yellow)
       (Detta förhindrar "fel ATL" när vi hellre vill ha rimlig schablon.)
    """
    out = dict(results or {})
    res_list = out.get("results")
    if not isinstance(res_list, list):
        return out

    new_list: List[Dict[str, Any]] = []
    for r in res_list:
        if not isinstance(r, dict):
            continue

        task_id = str(r.get("task_id") or "").strip()
        if not task_id:
            new_list.append(r)
            continue

        manual_minutes = _manual_minutes_for_task(task_id)

        needs_est = r.get("needs_estimate") is True
        confidence_level = str(r.get("confidence_level") or "").strip().lower()
        time_source = str(r.get("time_source") or "").strip().lower()

        should_override_weak_atl = (
            manual_minutes is not None
            and time_source == "atl"
            and confidence_level in {"yellow", "red"}
        )

        if (needs_est and manual_minutes is not None) or should_override_weak_atl:
            rr = dict(r)
            rr["time_source"] = "manual_fallback"
            rr["time_minutes_per_unit"] = float(manual_minutes)
            rr["needs_estimate"] = False
            rr["confidence"] = max(float(rr.get("confidence") or 0.0), 0.6)
            rr["confidence_level"] = "yellow"

            # Ta bort chosen om vi override:ar ett svagt ATL-val (så UI inte visar fel ATL)
            if should_override_weak_atl and "chosen" in rr:
                rr.pop("chosen", None)

            suffix = " (Fallback: använde manual_time_minutes_per_unit från mappings.)"
            if should_override_weak_atl:
                suffix = " (Override: svag ATL-träff ersatt med manual_time_minutes_per_unit från mappings.)"

            rr["explanation"] = ((rr.get("explanation") or "").strip() + suffix).strip()
            new_list.append(rr)
        else:
            new_list.append(r)

    out["results"] = new_list
    return out


def select_atl_for_items(
    *,
    items: List[Dict[str, Any]],
    max_rows_per_item: int = 12,
) -> Dict[str, Any]:
    spec = load_atl_selection_spec()
    client = AIClient()

    enriched_items: List[Dict[str, Any]] = []
    for it in items:
        seg_id = str(it.get("segment_id") or "").strip()
        seg_text = str(it.get("segment_text") or "").strip()
        task_id = str(it.get("task_id") or "").strip()
        label = str(it.get("label") or "").strip()

        if not seg_id or not seg_text:
            continue

        search_text = " ".join([seg_text, label, task_id]).strip()

        candidates = _pick_candidates(
            search_text=search_text,
            seg_text=seg_text,
            task_id=task_id,
            max_rows=max_rows_per_item,
        )

        enriched_items.append(
            {
                "segment_id": seg_id,
                "segment_text": seg_text,
                "task_id": it.get("task_id"),
                "label": it.get("label"),
                "quantity": it.get("quantity", 1),
                "atl_candidates": [_row_to_candidate_payload(r) for r in candidates],
            }
        )

    gpt_input = {"items": enriched_items}
    raw = client.generate_atl_selection(spec=spec, gpt_input=gpt_input)
    return _apply_manual_fallback(raw)
