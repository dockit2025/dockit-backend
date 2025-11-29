import re
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from src.services.atl_lookup import get_atl_time_minutes

# ---------------------------------------------------------
# Hjälpfunktioner
# ---------------------------------------------------------

SWEDISH_NUMBER_WORDS = {
    "en": 1,
    "ett": 1,
    "ena": 1,   # ibland skrivs lite konstigt i löptext
    "ettan": 1,
    "två": 2,
    "tva": 2,   # fallback utan å
    "tre": 3,
    "fyra": 4,
    "fem": 5,
    "sex": 6,
    "sju": 7,
    "åtta": 8,
    "atta": 8,  # fallback
    "nio": 9,
    "tio": 10,
}

# ---------------------------------------------------------
# Loggning av trasiga material-mappningar / omatchade segment
# ---------------------------------------------------------

ROOT = Path(__file__).resolve().parents[0]
LOG_DIR = ROOT / "knowledge" / "logs"
BROKEN_MAP_LOG = LOG_DIR / "broken_material_refs.jsonl"
MISSING_TASK_SEGMENTS_LOG = LOG_DIR / "missing_task_segments.jsonl"


def _ensure_log_dir() -> None:
    """
    Ser till att loggmappen finns.
    """
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        # Vi vill aldrig krascha på grund av loggning
        pass


def _log_unmatched_segment(segment: str) -> None:
    """
    Loggar textsegment som inte matchade någon task.
    Underlag för att senare låta GPT föreslå nya tasks/mappingar.
    """
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
        # Vi vill aldrig krascha på grund av loggning
        pass


# ---------------------------------------------------------
# Ladda tasks från YAML-mappings
# ---------------------------------------------------------

def _load_all_tasks_from_mappings() -> List[Dict[str, Any]]:
    """
    Läser in alla mapping-filer i mappen 'mappings/' och returnerar
    en lista med sammanslagna task-dictar.

    Stöder tre vanliga YAML-strukturer:

    1) Top-nivå: {"tasks": [ {task...}, {task...}, ... ]}
    2) Top-nivå: {"tasks": { "task_id_1": {...}, "task_id_2": {...}, ... }}
    3) Top-nivå: [ {task...}, {task...}, ... ]
    """
    base_dir = Path(__file__).resolve().parent
    mappings_dir = base_dir / "mappings"

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
            # Okänd struktur - hoppa över filen
            continue

        # Fall A: tasks_raw är en lista med redan kompletta task-dictar
        if isinstance(tasks_raw, list):
            for task in tasks_raw:
                if not isinstance(task, dict):
                    continue
                task_copy = dict(task)
                # Se till att vi vet vilken fil tasken kom ifrån
                task_copy["_mapping_file"] = path.name
                all_tasks.append(task_copy)

        # Fall B: tasks_raw är en dict: {task_id: { ... }, ...}
        elif isinstance(tasks_raw, dict):
            for task_id, task_def in tasks_raw.items():
                if not isinstance(task_def, dict):
                    continue
                task_copy = dict(task_def)
                # Om task_id saknas inne i dict: sätt den från nyckeln
                task_copy.setdefault("task_id", task_id)
                task_copy["_mapping_file"] = path.name
                all_tasks.append(task_copy)

    return all_tasks


# ---------------------------------------------------------
# Pattern-matchning (fri text ↔ mapping-pattern)
# ---------------------------------------------------------

def _simple_pattern_match(text: str, pattern: str) -> bool:
    """
    Enkel matchning:
    - case-insensitive
    - matchar antingen exakt substring
    - eller alla ord i pattern i rätt ordning (med valfria ord emellan),
      men med begränsat avstånd mellan första och sista ordet.
    """
    text_l = text.lower()
    patt_l = pattern.strip().lower()
    if not patt_l:
        return False

    # 1) Försök med enkel substring (exakt fras)
    if patt_l in text_l:
        return True

    # 2) Ord-för-ord i rätt ordning med max span
    words = re.findall(r"[a-zåäö0-9]+", patt_l)
    if not words:
        return False

    idx = 0
    first_pos = None
    last_pos = None

    for w in words:
        m = re.search(r"\b" + re.escape(w) + r"\b", text_l[idx:]); pos = idx + m.start() if m else -1
        if pos == -1:
            return False
        if first_pos is None:
            first_pos = pos
        last_pos = pos
        idx = pos + len(w)

    # Begränsa hur långt ifrån varandra första och sista ordet får ligga
    MAX_SPAN_CHARS = 25
    if first_pos is not None and last_pos is not None:
        if (last_pos - first_pos) > MAX_SPAN_CHARS:
            return False

    return True


# ---------------------------------------------------------
# Detektera quantity (antal) från text
# ---------------------------------------------------------

def _detect_quantity_from_context(
    free_text: str,
    pattern: str,
    default_quantity: float = 1.0,
) -> float:
    """
    Först: försök hitta "<tal> meter" eller "<tal> m" i närheten av pattern
    och använd det som quantity (för längdmoment).
    Annars: original logik (siffror eller talord före pattern).
    Vi gissar aldrig fram extra moment – vi läser bara det som faktiskt står.
    """
    text_l = free_text.lower()
    patt_l = pattern.strip().lower()

    # Ord i pattern (för att hitta sista ordet där vi tittar bakåt)
    patt_words = re.findall(r"[a-zåäö0-9]+", patt_l)
    last_word = patt_words[-1] if patt_words else ""
    idx_last_word = text_l.find(last_word) if last_word else -1

    # 1) Försök hitta "<tal> meter" eller "<tal> m" och välj den som ligger
    #    närmast pattern (före pattern om möjligt).
    meter_matches = list(re.finditer(r"(\d+(?:[.,]\d+)?)\s*(meter|m)\b", text_l))
    if meter_matches:
        chosen_match = None

        if idx_last_word != -1:
            # Välj den match som ligger närmast men inte efter sista ordet i pattern
            before = [m for m in meter_matches if m.start() <= idx_last_word]
            if before:
                chosen_match = before[-1]  # närmast före pattern
        if chosen_match is None:
            # Om vi inte hittade någon före pattern, ta sista generellt (som tidigare logik)
            chosen_match = meter_matches[-1]

        try:
            num_str = chosen_match.group(1).replace(",", ".")
            qty_val = float(num_str)
            if qty_val > 0:
                return qty_val
        except Exception:
            pass

    # 2) Original-logik: leta i kontext precis före sista ordet i pattern
    if idx_last_word == -1:
        return default_quantity

    window_start = max(0, idx_last_word - 30)
    context = text_l[window_start:idx_last_word].strip()

    # 2a) Leta efter siffer-tal (t.ex. "3", "12")
    m_digits = re.search(r"(\d+)\D*$", context)
    if m_digits:
        try:
            return float(int(m_digits.group(1)))
        except ValueError:
            pass

    # 2b) Leta efter sista "ordet" och tolka som talord
    words = re.findall(r"[a-zåäöA-ZÅÄÖ]+", context)
    if words:
        last_ctx_word = words[-1].lower()
        if last_ctx_word in SWEDISH_NUMBER_WORDS:
            return float(SWEDISH_NUMBER_WORDS[last_ctx_word])

    return default_quantity


# ---------------------------------------------------------
# Bygg task-resultat (en rad i JSON-output)
# ---------------------------------------------------------

def _build_task_result(
    task_def: Dict[str, Any],
    matched_pattern: str,
    text_segment: str,
) -> Dict[str, Any]:
    """
    Bygger upp en task-post i JSON-output baserat på task_def
    och vilken pattern som matchade, för ett specifikt textsegment.

    Stöd för ATL-tider om task_def innehåller:
        time_source: "atl" eller "auto"
        atl_moment/atl_variant ELLER atl_refs-lista
    """
    try:
        manual_time_minutes_per_unit = float(task_def.get("manual_time_minutes_per_unit") or 0)
    except Exception:
        manual_time_minutes_per_unit = 0.0

    time_source = (task_def.get("time_source") or "manual").lower()

    # ATL-konfiguration (valfri)
    atl_moment = task_def.get("atl_moment")
    atl_variant = task_def.get("atl_variant")

    # Om atl_moment inte är satt men atl_refs finns → plocka första posten
    atl_refs = task_def.get("atl_refs") or []
    if (not atl_moment) and isinstance(atl_refs, list) and atl_refs:
        first = atl_refs[0]
        if isinstance(first, dict):
            moment_val = (first.get("moment") or "").strip()
            atl_moment = moment_val or None
            variant_val = first.get("variant", None)
            try:
                atl_variant = int(variant_val) if variant_val is not None else None
            except Exception:
                atl_variant = None

    # Om tasken är markerad som ATL-baserad (eller "auto") och vi har moment + variant
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
            # OBS: behåller din befintliga logik med * 60.0
            manual_time_minutes_per_unit = float(atl_minutes) * 60.0
            time_source = "atl"

    quantity = _detect_quantity_from_context(
        text_segment,
        matched_pattern,
        default_quantity=1.0,
    )

    time_minutes_total = manual_time_minutes_per_unit * quantity

    result_task: Dict[str, Any] = {
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

    return result_task


def _collect_mapping_filenames() -> List[str]:
    """
    Returnerar en lista över alla mapping-filer i 'mappings/' (filnamn, sorterade).
    """
    base_dir = Path(__file__).resolve().parent
    mappings_dir = base_dir / "mappings"

    if not mappings_dir.exists():
        return []

    return sorted([p.name for p in mappings_dir.glob("*.yaml")])


# ---------------------------------------------------------
# Ny, smartare segmentering
# ---------------------------------------------------------

def _smart_split_on_och(segment: str) -> List[str]:
    """
    Försöker avgöra om 'och' i segmentet binder ihop två olika arbetsuppgifter.
    Om både delen före och efter 'och' innehåller verb från vår lista → dela upp.
    Annars behåller vi allt som ett segment.
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
    """
    Delar upp texten i mindre segment (ungefär en 'uppgift' per segment).
    """
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

        och_segments = _smart_split_on_och(part)
        for seg in och_segments:
            seg = seg.strip()
            if seg:
                segments.append(seg)

    return segments


# ---------------------------------------------------------
# Dedupe av tasks (skydd mot dubbletter från flera mappings)
# ---------------------------------------------------------

def _dedupe_tasks(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Tar bort dubbletter av tasks med samma (task_id, text_segment).
    """
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


# ---------------------------------------------------------
# Ny helper: "samma sträcka" / "samma längd"
# ---------------------------------------------------------

def _propagate_same_distance_quantity(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Om ett task-segment innehåller fraser som "samma sträcka"/"samma längd"
    och quantity är 1.0, försök att återanvända quantity från närmast föregående
    task i samma kategori med quantity > 1.

    Exempel:
        ... "dra vp rör infällt i vägg 8 meter ... dra kabel i rör samma sträcka"
    Då ska kabeldragningen också få quantity 8.
    """
    SAME_DISTANCE_PHRASES = ("samma sträcka", "samma längd", "samma väg")

    last_quantity_by_category: Dict[str, float] = {}
    new_tasks: List[Dict[str, Any]] = []

    for t in tasks:
        task = dict(t)

        seg = (task.get("text_segment") or "").lower()
        qty = task.get("quantity")
        cat = task.get("category")

        if isinstance(qty, (int, float)) and qty > 1 and cat:
            last_quantity_by_category[cat] = float(qty)

        if cat and qty in (1, 1.0) and any(phrase in seg for phrase in SAME_DISTANCE_PHRASES):
            prev_qty = last_quantity_by_category.get(cat)
            if prev_qty and prev_qty > 1:
                task["quantity"] = prev_qty
                per_unit = task.get("time_minutes_per_unit")
                if isinstance(per_unit, (int, float)):
                    task["time_minutes_total"] = per_unit * prev_qty

        new_tasks.append(task)

    return new_tasks


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

    segments = _split_into_segments(free_text_stripped)

    for segment in segments:
        segment_matched = False

        for task_def in all_tasks_defs:
            patterns: Optional[List[str]] = task_def.get("patterns")
            if not patterns:
                continue

            matched_pattern_for_this_task: Optional[List[str]] = None

            for pattern in patterns:
                if not isinstance(pattern, str):
                    continue

                if _simple_pattern_match(segment, pattern):
                    matched_pattern_for_this_task = pattern
                    break

            if matched_pattern_for_this_task is not None:
                result_task = _build_task_result(
                    task_def=task_def,
                    matched_pattern=matched_pattern_for_this_task,
                    text_segment=segment,
                )
                matched_tasks.append(result_task)
                segment_matched = True

        if not segment_matched:
            _log_unmatched_segment(segment)

    matched_tasks = _dedupe_tasks(matched_tasks)

    # Justera quantities för "samma sträcka" / "samma längd"
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
            "Byta två vägguttag i vardagsrummet och putsa fönsterna i köket."
        )

    data = interpret_free_text(free_text_input)
    print(json.dumps(data, ensure_ascii=False, indent=2))
