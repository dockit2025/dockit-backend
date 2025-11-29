from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple


# Projektrot, t.ex. D:\dockit-ai
ROOT = Path(__file__).resolve().parents[2]

LOG_DIR = ROOT / "knowledge" / "logs"
MATERIAL_LOG_PATH = LOG_DIR / "missing_material_mappings.jsonl"

MATERIAL_REF_MAP_PATH = ROOT / "knowledge" / "catalogs" / "material_ref_map.json"


def _load_existing_material_ref_map() -> Dict[str, str]:
    """
    Läser in material_ref_map.json om den finns.
    Returnerar dict {material_ref: artikelnummer}.
    """
    if not MATERIAL_REF_MAP_PATH.exists():
        return {}

    try:
        with MATERIAL_REF_MAP_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f) or {}
    except Exception as e:  # noqa: BLE001
        print(f"[ai_suggestions] Kunde inte läsa material_ref_map.json: {e}")
        return {}

    mapping: Dict[str, str] = {}
    if isinstance(data, dict):
        for ref, art in data.items():
            if ref is None or art is None:
                continue
            mapping[str(ref)] = str(art).strip()
    return mapping


def load_missing_material_refs() -> Counter:
    """
    Läser missing_material_mappings.jsonl och räknar hur många gånger
    varje material_ref förekommer.

    Returnerar en Counter:
        Counter({ "DIMMER-UNIV": 5, "APPRAM-1FACK": 2, ... })
    """
    counts: Counter = Counter()

    if not MATERIAL_LOG_PATH.exists():
        return counts

    with MATERIAL_LOG_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            if not isinstance(event, dict):
                continue

            if event.get("type") != "missing_material_mapping":
                continue

            ref = event.get("material_ref")
            if not ref:
                continue

            counts[str(ref)] += 1

    return counts


def get_top_missing_material_refs(limit: int = 50) -> List[Tuple[str, int]]:
    """
    Returnerar en lista med de vanligaste saknade material_ref:

        [("DIMMER-UNIV", 5), ("APPRAM-1FACK", 2), ...]

    Filtrerar bort sådana refs som redan finns i material_ref_map.json
    (dvs sådant du redan har åtgärdat).
    """
    counts = load_missing_material_refs()
    if not counts:
        return []

    existing_map = _load_existing_material_ref_map()
    existing_refs = set(existing_map.keys())

    items: List[Tuple[str, int]] = []
    for ref, cnt in counts.most_common():
        if ref in existing_refs:
            # redan mappad → behöver inte längre åtgärdas
            continue
        items.append((ref, cnt))
        if len(items) >= limit:
            break

    return items


def build_material_mapping_prompt(top_refs: List[Tuple[str, int]]) -> str:
    """
    Bygger en textprompt som kan användas mot GPT (manuellt eller via API)
    för att få förslag på artikelnummer per material_ref.

    Användning:
        top_refs = get_top_missing_material_refs(50)
        prompt = build_material_mapping_prompt(top_refs)
        print(prompt)
    """
    if not top_refs:
        return (
            "Det finns för närvarande inga omappade material_ref i loggen "
            "(alla kända refs verkar redan ha mapping i material_ref_map.json)."
        )

    lines: List[str] = []

    lines.append(
        "Du hjälper mig att föreslå artikelnummer från grossistens prislista "
        "för interna materialreferenser i mitt offertsystem för elektriker."
    )
    lines.append("")
    lines.append("Systemet fungerar så här i korthet:")
    lines.append(
        "- Varje materialrad i offerten har en intern material_ref "
        "(t.ex. DIMMER-UNIV)."
    )
    lines.append(
        "- I filen material_ref_map.json mappar jag material_ref → artikelnummer "
        "(från grossistens prislista)."
    )
    lines.append(
        "- Om en material_ref saknar mapping loggas den till "
        "missing_material_mappings.jsonl."
    )
    lines.append("")
    lines.append(
        "Din uppgift nu är att, för varje material_ref nedan, föreslå ett eller flera "
        "rimliga artikelnummer ur grossistens prislista. Om du är osäker, skriv det."
    )
    lines.append("")
    lines.append("Lista över saknade material_ref (med antal förekomster):")
    lines.append("")

    for ref, count in top_refs:
        lines.append(f"- {ref} (förekomster i logg: {count})")

    lines.append("")
    lines.append("Svara i JSON-format med strukturen:")
    lines.append("{")
    lines.append('  "suggestions": {')
    lines.append('    "MATERIAL_REF_1": "ARTIKELNUMMER_1",')
    lines.append('    "MATERIAL_REF_2": "ARTIKELNUMMER_2"')
    lines.append("  },")
    lines.append('  "notes": "valfria kommentarer eller osäkerheter"')
    lines.append("}")

    return "\n".join(lines)


def apply_material_suggestions(suggestions: Dict[str, str]) -> None:
    """
    Tar emot ett dict {material_ref: artikelnummer} (t.ex. från GPT)
    och uppdaterar material_ref_map.json.

    - Befintliga rader behålls.
    - Nya eller uppdaterade refs skrivs in/över.
    - Filen skrivs tillbaka som snygg JSON med indentering.
    """
    existing = _load_existing_material_ref_map()

    # Uppdatera med inkomna förslag
    for ref, art in suggestions.items():
        if ref is None or art is None:
            continue
        ref_s = str(ref).strip()
        art_s = str(art).strip()
        if not ref_s or not art_s:
            continue
        existing[ref_s] = art_s

    # Skriv tillbaka till fil
    MATERIAL_REF_MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MATERIAL_REF_MAP_PATH.open("w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2, sort_keys=True)

    print(
        f"[ai_suggestions] Uppdaterade material_ref_map.json med "
        f"{len(suggestions)} förslag."
    )


if __name__ == "__main__":
    # Enkel CLI-hjälp:
    # 1) Läs topp saknade refs
    # 2) Skriv ut prompt till konsolen
    top = get_top_missing_material_refs(50)
    prompt = build_material_mapping_prompt(top)
    print(prompt)
