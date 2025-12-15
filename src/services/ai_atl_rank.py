from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.services.ai_client import AIClient
from src.services.ai_specs import load_atl_rank_spec
from src.services.ai_suggestions import find_atl_candidates_for_segment


def suggest_atl_ref_for_task(
    *,
    task: Dict[str, Any],
    segment_text: str,
    max_rows: int = 25,
    min_score: float = 0.01,
) -> Dict[str, Any]:
    """
    Admin-only: Föreslå ATL-referens (moment_id + variant) för en task,
    baserat på text + top-kandidater från ATL-listan.
    """
    spec = load_atl_rank_spec()
    client = AIClient()

    # Bygg ATL-kandidater
    candidates = find_atl_candidates_for_segment(
        segment_text=segment_text,
        max_rows=max_rows,
        min_score=min_score,
    )

    atl_candidates: List[Dict[str, Any]] = []
    for r in candidates:
        atl_candidates.append(
            {
                "moment_id": r.id_str,
                "arbetsmoment": r.arbetsmoment,
                "moment_text": r.moment_text,
                "underlag_text": r.underlag_text,
                "enhet": r.enhet,
                "times": r.times,
            }
        )

    gpt_input: Dict[str, Any] = {
        "task": {
            "task_id": task.get("task_id"),
            "label": task.get("label"),
            "category": task.get("category"),
        },
        "segment_text": segment_text,
        "atl_candidates": atl_candidates,
    }

    return client.generate_atl_rank(spec=spec, gpt_input=gpt_input)
