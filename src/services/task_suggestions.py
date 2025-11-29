from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------
# Paths
# ---------------------------------------------------------

# Projektrot, t.ex. D:\dockit-ai
ROOT = Path(__file__).resolve().parents[2]

LOG_DIR = ROOT / "knowledge" / "logs"
MISSING_TASK_SEGMENTS_PATH = LOG_DIR / "missing_task_segments.jsonl"
TASK_SUGGESTIONS_LOG = LOG_DIR / "task_suggestions.jsonl"

MAPPINGS_DIR = ROOT / "mappings"

CATEGORY_TO_FILE = {
    "belysning": "belysning.yaml",
    "brytare_och_uttag": "brytare_och_uttag.yaml",
    "natverk_och_media": "natverk_och_media.yaml",
    "ror_och_vp": "ror_och_vp.yaml",
    "felsokning_och_service": "felsokning_och_service.yaml",
    "kok": "kok.yaml",
    "badrum": "badrum.yaml",
    "ovrigt": "ovrigt.yaml",
}


# ---------------------------------------------------------
# Läs missing_task-segment
# ---------------------------------------------------------

def _load_missing_task_events(limit: Optional[int] = 50) -> List[Dict[str, Any]]:
    if not MISSING_TASK_SEGMENTS_PATH.exists():
        return []

    events: List[Dict[str, Any]] = []

    with MISSING_TASK_SEGMENTS_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            if event.get("type") != "missing_task_segment":
                continue

            segment = (event.get("segment") or "").strip()
            if not segment:
                continue

            events.append(event)

    if limit is not None and limit > 0 and len(events) > limit:
        events = events[-limit:]

    return events


def _build_segment_id(event: Dict[str, Any], index: int) -> str:
    ts_raw = str(event.get("ts") or "")
    ts_clean = (
        ts_raw.replace("-", "")
        .replace(":", "")
        .replace(".", "")
        .strip()
    )
    if not ts_clean:
        ts_clean = "notimestamp"

    return f"missingseg_{ts_clean}_{index:04d}"


# ---------------------------------------------------------
# GPT-input
# ---------------------------------------------------------

def build_gpt_input_from_missing_segments(limit: int = 50) -> Dict[str, Any]:
    events = _load_missing_task_events(limit=limit)
    segments_out: List[Dict[str, Any]] = []

    for idx, event in enumerate(events, start=1):
        segment_text = (event.get("segment") or "").strip()
        if not segment_text:
            continue

        segments_out.append(
            {
                "segment_id": _build_segment_id(event, idx),
                "segment_text": segment_text,
                "source_type": str(event.get("type") or "missing_task_segment"),
                "room_hint": None,
                "language": "sv",
                "existing_task_ref": None,
            }
        )

    return {"segments": segments_out}


# ---------------------------------------------------------
# Logga GPT-output
# ---------------------------------------------------------

def _append_json_line(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
        f.write("\n")


def log_task_suggestions(gpt_output: Dict[str, Any]) -> None:
    event = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "type": "task_suggestions",
        "payload": gpt_output,
    }
    _append_json_line(TASK_SUGGESTIONS_LOG, event)


# ---------------------------------------------------------
# Helpers för YAML-mappingar
# ---------------------------------------------------------

def _category_to_mapping_path(category: Optional[str]) -> Path:
    cat = (category or "ovrigt").strip().lower() or "ovrigt"
    filename = CATEGORY_TO_FILE.get(cat, CATEGORY_TO_FILE["ovrigt"])
    return MAPPINGS_DIR / filename


def _load_mapping_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"tasks": []}

    import yaml
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if isinstance(data, dict):
        tasks = data.get("tasks")
        if isinstance(tasks, list):
            return {"tasks": tasks}
        if isinstance(tasks, dict):
            out = []
            for task_id, task_def in tasks.items():
                if not isinstance(task_def, dict):
                    continue
                t = dict(task_def)
                t.setdefault("task_id", task_id)
                out.append(t)
            return {"tasks": out}
        return {"tasks": []}

    if isinstance(data, list):
        return {"tasks": data}

    return {"tasks": []}


def _save_mapping_file(path: Path, data: Dict[str, Any]) -> None:
    import yaml
    path.parent.mkdir(parents=True, exist_ok=True)
    out = {"tasks": data.get("tasks") or []}
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(out, f, allow_unicode=True, sort_keys=False, indent=2)


def _task_exists(tasks: List[Dict[str, Any]], task_id: str) -> bool:
    tid = (task_id or "").strip()
    if not tid:
        return False
    for t in tasks:
        if (t.get("task_id") or "").strip() == tid:
            return True
    return False


def _convert_suggested_task_to_mapping_task(s: Dict[str, Any]) -> Dict[str, Any]:
    task_ref = (s.get("task_ref") or "").strip()
    title_sv = (s.get("title_sv") or "").strip()
    description_sv = (s.get("description_sv") or "").strip()
    category = (s.get("category") or "ovrigt").strip() or "ovrigt"

    # Tid: timmar -> minuter
    hours = 0.0
    try:
        hours = float(s.get("estimated_hours_per_unit") or 0.0)
    except Exception:
        hours = 0.0

    minutes = int(round(hours * 60)) if hours > 0 else 0

    segment_text = (s.get("source_segment_text") or "").strip()

    # NYTT: använd GPT:s egna patterns om de finns
    raw_patterns = s.get("patterns") or []
    patterns_list: List[str] = []

    if isinstance(raw_patterns, list):
        for p in raw_patterns:
            if isinstance(p, str):
                p_clean = p.strip()
                if p_clean:
                    patterns_list.append(p_clean)

    if not patterns_list:
        if segment_text:
            patterns_list = [segment_text]
        elif title_sv:
            patterns_list = [title_sv]

    # Material
    materials: List[Dict[str, Any]] = []
    for m in s.get("default_materials") or []:
        if not isinstance(m, dict):
            continue
        ref_hint = (m.get("material_ref_hint") or "").strip()
        if not ref_hint:
            continue
        qty = m.get("qty_per_unit") or 1.0
        try:
            qty = float(qty)
        except Exception:
            qty = 1.0

        mat = {"ref": ref_hint, "quantity_per_unit": qty}
        unit = m.get("unit")
        if unit:
            mat["unit"] = unit
        note = m.get("note")
        if note:
            mat["description"] = note

        materials.append(mat)

    return {
        "task_id": task_ref or title_sv.replace(" ", "_").upper(),
        "label": title_sv or task_ref or "Nytt arbetsmoment",
        "category": category,
        "manual_time_minutes_per_unit": minutes,
        "time_source": "gpt",
        "description": description_sv or None,
        "quantity_type": s.get("quantity_type") or "per_unit",
        "default_unit": s.get("default_unit") or "st",
        "room_type_hint": s.get("room_type_hint"),
        "gpt_confidence": s.get("confidence"),
        "patterns": patterns_list,
        "materials": materials,
        "_auto_generated": True,
    }


def apply_suggested_tasks(gpt_output: Dict[str, Any]) -> None:
    suggested = gpt_output.get("suggested_tasks") or []
    if not isinstance(suggested, list):
        return

    tasks_per_file: Dict[Path, List[Dict[str, Any]]] = {}

    for s in suggested:
        if not isinstance(s, dict):
            continue

        category = (s.get("category") or "ovrigt").strip() or "ovrigt"
        path = _category_to_mapping_path(category)
        t = _convert_suggested_task_to_mapping_task(s)

        tasks_per_file.setdefault(path, []).append(t)

    for path, new_tasks in tasks_per_file.items():
        data = _load_mapping_file(path)
        tasks = data.get("tasks") or []

        for t in new_tasks:
            if not _task_exists(tasks, t.get("task_id")):
                tasks.append(t)

        data["tasks"] = tasks
        _save_mapping_file(path, data)


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def _load_gpt_output(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python task_suggestions.py path_to_gpt_output.json")
        sys.exit(1)

    gpt_output = _load_gpt_output(Path(sys.argv[1]))

    log_task_suggestions(gpt_output)
    apply_suggested_tasks(gpt_output)

    print("OK: suggestions logged + written to mapping files.")
