from __future__ import annotations

from typing import Any, Dict, Optional

from src.services.ai_client import AIClient
from src.services.ai_specs import load_workplan_spec


def generate_workplan(
    *,
    job_text: str,
    language: str = "sv",
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    FAS 0 (Sandbox-only): Fri text -> work_plan + segments + antaganden.
    """
    spec = load_workplan_spec()
    client = AIClient()

    gpt_input: Dict[str, Any] = {
        "job_text": job_text,
        "language": language,
        "context": context or {},
    }

    return client.generate_workplan(spec=spec, gpt_input=gpt_input)
