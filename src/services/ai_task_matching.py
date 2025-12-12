from __future__ import annotations

from typing import Any, Dict, List

from src.services.ai_client import AIClient
from src.services.ai_specs import load_task_matching_spec


def match_segments_to_tasks(
    *,
    segments: List[Dict[str, Any]],
    candidates_by_segment: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    spec = load_task_matching_spec()
    client = AIClient()

    gpt_input = {
        "segments": segments,
        "candidates_by_segment": candidates_by_segment,
    }

    return client.generate_task_matches(spec=spec, gpt_input=gpt_input)
