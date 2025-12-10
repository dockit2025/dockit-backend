import re
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.services.atl_lookup import get_atl_time_minutes


# ---------------------------------------------------------
# Hjälpdata
# ---------------------------------------------------------

SWEDISH_NUMBER_WORDS = {
    "en": 1,
    "ett": 1,
    "ena": 1,
    "ettan": 1,
    "två": 2,
    "tva": 2,
    "tre": 3,
    "fyra": 4,
    "fem": 5,
    "sex": 6,
    "sju": 7,
    "åtta": 8,
    "atta": 8,
    "nio": 9,
    "tio": 10,
}


ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "knowledge" / "logs"
BROKEN_MAP_LOG = LOG_DIR / "broken_material_refs.jsonl"
MISSING_TASK_SEGMENTS_LOG = LOG_DIR / "missing_task_segments.jsonl"


def _ensure_log_dir() -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


def _log_unmatched_segment(segment: str) -> None:
    clean = (segment or "").strip()
    if not clean:
        return

    _ensure_log_dir()
    event = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "type": "missing_task_segment",
        "segment": clean,
    }

    try:
        with MISSING_TASK_SEGMENTS_LOG.open("a", encoding="utf-8") as f:
            json.dump(event, f, ensure_ascii=False)
            f.write("\n")
    except Exception:
        pass


# ---------------------------------------------------------
# Ladda tasks från mappings/
# ---------------------------------------------------------


def _load_all_tasks_from_mappings() -> List[Dict[str, Any]]:
    """
    Läser alla YAML-filer i mappen 'mappings/' och returnerar en lista med task-dictar.
    Stöder både:
    - {"tasks": [ {...}, {...} ]}
    - {"tasks": { "id": {...}, ... }}
    - eller ren lista med dictar.
    """
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


def _collect_mapping_filenames() -> List[str]:
    mappings_dir = ROOT / "mappings"
    if not mappings_dir.exists():
        return []
    return sorted([p.name for p in mappings_dir.glob("*.yaml")])


# ---------------------------------------------------------
# Enkel patternmatchning
# ---------------------------------------------------------


def _simple_pattern_match(text: str, pattern: str) -> bool:
    """
    Enkel matchning:
    - case-insensitive
    - först: direkt substring
    - annars: alla ord i pattern i rätt ordning, med begränsad spridning.
    """
    text_l = text.lower()
    patt_l = pattern.strip().lower()
    if not patt_l:
        return False

    if patt_l in text_l:
        return True

    words = re.findall(r"[a-zåäö0-9]+", patt_l)
    if not words:
        return False

    idx = 0
    first_pos = None
    last_pos = None

    for w in words:
        m = re.search(r"\b" + re.escape(w) + r"\b", text_l[idx:])
        if not m:
            return False
        pos = idx + m.start()
        if first_pos is None:
            first_pos = pos
        last_pos = pos
        idx = pos + len(w)

    MAX_SPAN_CHARS = 25
    if first_pos is not None and last_pos is not None:
        if (last_pos - first_pos) > MAX_SPAN_CHARS:
            return False

    return True


# ---------------------------------------------------------
# Quantity-detektering
# ---------------------------------------------------------


def _detect_quantity_from_context(
    free_text: str,
    pattern: str,
    default_quantity: float = 1.0,
) -> float:
    """
    Försöker hitta antal i närheten av pattern.
    - ex. "3 vägguttag" → 3
    - hanterar både siffror och talord.
    """
    text_l = free_text.lower()
    patt_l = pattern.strip().lower()
    patt_words = re.findall(r"[a-zåäö0-9]+", patt_l)
    last_word = patt_words[-1] if patt_words else ""
    idx_last_word = text_l.find(last_word) if last_word else -1

    # Först: meter-matchningar som "12 meter" eller "12 m"
    meter_matches = list(re.finditer(r"(\d+(?:[.,]\d+)?)\s*(meter|m)\b", text_l))
    if meter_matches:
        chosen = None
        if idx_last_word != -1:
            before = [m for m in meter_matches if m.start() <= idx_last_word]
            if before:
                chosen = before[-1]
        if chosen is None:
            chosen = meter_matches[-1]
        try:
            num_str = chosen.group(1).replace(",", ".")
            val = float(num_str)
            if val > 0:
                return val
        except Exception:
            pass

    if idx_last_word == -1:
        return default_quantity

    window_start = max(0, idx_last_word - 30)
    context = text_l[window_start:idx_last_word].strip()

    m_digits = re.search(r"(\d+)\D*$", context)
    if m_digits:
        try:
            return float(int(m_digits.group(1)))
        except ValueError:
            pass

    words = re.findall(r"[a-zåäöA-ZÅÄÖ]+", context)
    if words:
        last_ctx_word = words[-1].lower()
        if last_ctx_word in SWEDISH_NUMBER_WORDS:
            return float(SWEDISH_NUMBER_WORDS[last_ctx_word])

    return default_quantity


# ---------------------------------------------------------
# Segmentering
# ---------------------------------------------------------


def _smart_split_on_och(segment: str) -> List[str]:
    """
    Delar på 'och' om det binder ihop två separata arbetsuppgifter.
    Ex: "byta uttag och installera dimmer" → två segment.
    """
    lower = segment.lower()
    if " och " not in lower:
        return [segment]

    verbs = [
        "byta",
        "installera",
        "sätta upp",
        "montera",
        "dra",
        "koppla in",
        "koppla ur",
        "ta bort",
        "riva",
        "felsöka",
        "justera",
        "programmera",
        "flytta",
        "lägga",
        "mäta",
        "putsa",
    ]

    def has_verb(phrase_lower: str) -> bool:
        phrase_lower = phrase_lower.strip()
        if not phrase_lower:
            return False
        for v in verbs:
            if phrase_lower.startswith(v + " "):
                return True
            if " " + v + " " in phrase_lower:
                return True
            if phrase_lower == v:
                return True
        return False

    parts = segment.split(" och ")
    if len(parts) == 1:
        return [segment]

    result: List[str] = []
    current = parts[0].strip()

    for next_part in parts[1:]:
        next_clean = next_part.strip()
        if not next_clean:
            continue

        cur_has = has_verb(current.lower())
        next_has = has_verb(next_clean.lower())

        if cur_has and next_has:
            result.append(current)
            current = next_clean
        else:
            current = current + " och " + next_clean

    result.append(current)
    return result


def _split_into_segments(free_text: str) -> List[str]:
    segments: List[str] = []

    if not free_text:
        return segments

    text = re.sub(r"\s+", " ", free_text).strip()
    if not text:
        return segments

    raw_parts = re.split(r"[.!?]+|,(?!\d)", text)
    for part in raw_parts:
        part = part.strip()
        if not part:
            continue
        for seg in _smart_split_on_och(part):
            seg = seg.strip()
            if seg:
                segments.append(seg)

    return segments


# ---------------------------------------------------------
# Dedupe & "samma sträcka" quantity-propagation
# ---------------------------------------------------------


def _dedupe_tasks(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def score(task: Dict[str, Any]) -> int:
        s = 0
        task_id = (task.get("task_id") or "").lower()
        cat = (task.get("category") or "").lower()
        mf = (task.get("mapping_file") or "").lower()

        if "felsokning" in task_id:
            s += 1
        if "felsokning" in cat:
            s += 2
        if "felsokning" in mf:
            s += 2
        return s

    unique: Dict[tuple, Dict[str, Any]] = {}
    for t in tasks:
        key = (t.get("task_id"), t.get("text_segment"))
        if key in unique:
            existing = unique[key]
            if score(t) > score(existing):
                unique[key] = t
        else:
            unique[key] = t
    return list(unique.values())


def _propagate_same_distance_quantity(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    phrases = ("samma sträcka", "samma längd", "samma väg")
    last_quantity_by_category: Dict[str, float] = {}
    new_tasks: List[Dict[str, Any]] = []

    for t in tasks:
        task = dict(t)
        seg = (task.get("text_segment") or "").lower()
        qty = task.get("quantity")
        cat = task.get("category")

        if isinstance(qty, (int, float)) and qty > 1 and cat:
            last_quantity_by_category[cat] = float(qty)

        if cat and qty in (1, 1.0) and any(p in seg for p in phrases):
            prev_qty = last_quantity_by_category.get(cat)
            if prev_qty and prev_qty > 1:
                task["quantity"] = prev_qty
                per_unit = task.get("time_minutes_per_unit")
                if isinstance(per_unit, (int, float)):
                    task["time_minutes_total"] = per_unit * prev_qty

        new_tasks.append(task)

    return new_tasks


# ---------------------------------------------------------
# Bygg task-resultat
# ---------------------------------------------------------


def _build_task_result(
    task_def: Dict[str, Any],
    matched_pattern: str,
    text_segment: str,
) -> Dict[str, Any]:
    try:
        manual_time_minutes_per_unit = float(task_def.get("manual_time_minutes_per_unit") or 0)
    except Exception:
        manual_time_minutes_per_unit = 0.0

    time_source = (task_def.get("time_source") or "manual").lower()

    atl_moment = task_def.get("atl_moment")
    atl_variant = task_def.get("atl_variant")

    atl_refs = task_def.get("atl_refs") or []
    if (not atl_moment) and isinstance(atl_refs, list) and atl_refs:
        first = atl_refs[0]
        if isinstance(first, dict):
            m_val = (first.get("moment") or "").strip()
            v_val = first.get("variant", None)
            atl_moment = m_val or None
            try:
                atl_variant = int(v_val) if v_val is not None else None
            except Exception:
                atl_variant = None

    # ATL: använd get_atl_time_minutes som redan returnerar MINUTER per enhet
    if atl_moment and atl_variant is not None and time_source in ("atl", "auto"):
        try:
            variant_int = int(atl_variant)
        except (TypeError, ValueError):
            variant_int = 0

        try:
            atl_minutes = get_atl_time_minutes(str(atl_moment), variant_int)
        except Exception:
            atl_minutes = None

        if atl_minutes is not None and atl_minutes > 0:
            # atl_minutes är redan minuter per enhet
            manual_time_minutes_per_unit = float(atl_minutes)
            time_source = "atl"

    quantity = _detect_quantity_from_context(
        text_segment,
        matched_pattern,
        default_quantity=1.0,
    )

    time_minutes_total = manual_time_minutes_per_unit * quantity

    result = {
        "task_id": task_def.get("task_id"),
        "label": task_def.get("label"),
        "category": task_def.get("category"),
        "mapping_file": task_def.get("_mapping_file"),
        "matched_pattern": matched_pattern,
        "text_segment": text_segment,
        "quantity": quantity,
        "time_source": time_source,
        "time_minutes_per_unit": manual_time_minutes_per_unit,
        "time_minutes_total": time_minutes_total,
        "materials": task_def.get("materials", []),
        "atl_moment": atl_moment,
        "atl_variant": atl_variant,
    }

    return result


# ---------------------------------------------------------
# Publik funktion: interpret_free_text
# ---------------------------------------------------------


def interpret_free_text(free_text: str) -> Dict[str, Any]:
    """
    Tolkar fri text och returnerar ett JSON-liknande dict.
    """
    all_tasks_defs = _load_all_tasks_from_mappings()
    free_text_stripped = (free_text or "").strip()

    matched_tasks: List[Dict[str, Any]] = []
    missing_segments: List[str] = []

    segments = _split_into_segments(free_text_stripped)

    for segment in segments:
        segment_matched = False

        for task_def in all_tasks_defs:
            patterns: Optional[List[str]] = task_def.get("patterns")
            if not patterns:
                continue

            chosen_pattern: Optional[str] = None

            for pattern in patterns:
                if not isinstance(pattern, str):
                    continue

                if _simple_pattern_match(segment, pattern):
                    chosen_pattern = pattern
                    break

            if chosen_pattern is not None:
                result_task = _build_task_result(
                    task_def=task_def,
                    matched_pattern=chosen_pattern,
                    text_segment=segment,
                )
                matched_tasks.append(result_task)
                segment_matched = True

        if not segment_matched:
            _log_unmatched_segment(segment)
            missing_segments.append(segment)

    matched_tasks = _dedupe_tasks(matched_tasks)
    matched_tasks = _propagate_same_distance_quantity(matched_tasks)

    total_time_minutes = sum(t.get("time_minutes_total", 0) for t in matched_tasks)
    total_time_hours = total_time_minutes / 60.0 if total_time_minutes else 0.0

    totals = {
        "tasks_count": len(matched_tasks),
        "total_time_minutes": total_time_minutes,
        "total_time_hours": total_time_hours,
    }

    meta = {
        "version": "1.0.0",
        "mapping_files": _collect_mapping_filenames(),
    }

    result: Dict[str, Any] = {
        "free_text": free_text_stripped,
        "tasks": matched_tasks,
        "totals": totals,
        "meta": meta,
        "missing_segments": missing_segments,
    }

    return result


if __name__ == "__main__":
    if len(sys.argv) > 1:
        free_text_input = " ".join(sys.argv[1:])
    else:
        free_text_input = (
            "Byta tre vägguttag i vardagsrummet, byta en strömbrytare och installera en dimmer, "
            "dra infällda rör till ett nytt uttag i sovrummet, installera en diskmaskin i köket, "
            "sätta upp en taklampa i hallen och installera en laddbox på uppfarten. "
        )

    data = interpret_free_text(free_text_input)
    print(json.dumps(data, ensure_ascii=False, indent=2))
