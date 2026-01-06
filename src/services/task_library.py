# RUNTIME NOTE: /sandbox/gpt-match-tasks
# Denna loader används av sandbox-GPT-matchning (FAS 2 kandidatlista):
#   src/server/api/sandbox.py -> /sandbox/gpt-match-tasks
#
# OBS: /sandbox/interpret använder istället free_text_interpreter.py som egen loader.
# Ändra inte här utan att kontrollera runtime-noten i free_text_interpreter.py.
# Se: documentation/runtime_map.md
#from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_all_tasks_from_mappings() -> List[Dict[str, Any]]:
    mappings_dir = ROOT / "mappings"
    if not mappings_dir.exists():
        raise FileNotFoundError(f"Hittar inte mappen 'mappings/' på: {mappings_dir}")

    all_tasks: List[Dict[str, Any]] = []

    for path in sorted(mappings_dir.glob("*.yaml")):
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        tasks_raw = None
        if isinstance(data, dict) and "tasks" in data:
            tasks_raw = data["tasks"] or []
        elif isinstance(data, list):
            tasks_raw = data
        else:
            continue

        if isinstance(tasks_raw, list):
            for task in tasks_raw:
                if not isinstance(task, dict):
                    continue
                tcopy = dict(task)
                tcopy["_mapping_file"] = path.name
                all_tasks.append(tcopy)
        elif isinstance(tasks_raw, dict):
            for task_id, task_def in tasks_raw.items():
                if not isinstance(task_def, dict):
                    continue
                tcopy = dict(task_def)
                tcopy.setdefault("task_id", task_id)
                tcopy["_mapping_file"] = path.name
                all_tasks.append(tcopy)

    return all_tasks

