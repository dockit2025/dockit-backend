from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Projektrot, t.ex. D:\dockit-ai
ROOT = Path(__file__).resolve().parents[2]

# ------------------------------------------------------------
#  LOGGAR & MATERIAL-MAPPING (BEFINTLIG FUNKTIONALITET)
# ------------------------------------------------------------

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


# ------------------------------------------------------------
#  ATL-INTEGRATION FÖR GPT/SANDBOX (NY FUNKTIONALITET)
# ------------------------------------------------------------

ATL_PATH = ROOT / "knowledge" / "ATL" / "Del7_ATL_Total.csv"


@dataclass
class ATLRow:
    arbetsmoment: int          # kolumn "Arbetsmoment"
    grupp: str                 # "Grupp"
    rad: str                   # "Rad"
    moment_text: str           # "Moment/Typ/Sort"
    underlag_text: str         # "Underlag/Variant"
    enhet: str                 # "Enhet"
    times: Dict[str, float]    # t.ex. {"0": 0.03, "-1": 0.06, ...}

    @property
    def id_str(self) -> str:
        """
        Unikt id som kan användas mot GPT och i YAML.
        Just nu använder vi arbetsmoment-numret som sträng.
        """
        return str(self.arbetsmoment)


_ATL_CACHE: Optional[List[ATLRow]] = None


def load_atl_rows() -> List[ATLRow]:
    """
    Läser Del7_ATL_Total.csv och returnerar en lista ATLRow.

    Hanterar svenska kommatecken i tidskolumnerna (0,03 -> 0.03).

    Om filen saknas returneras en tom lista (ingen hård crash).
    """
    global _ATL_CACHE
    if _ATL_CACHE is not None:
        return _ATL_CACHE

    rows: List[ATLRow] = []
    if not ATL_PATH.exists():
        print(f"[ai_suggestions] Varning: ATL-fil saknas: {ATL_PATH}")
        _ATL_CACHE = []
        return _ATL_CACHE

    # Många ATL-exporter är semikolon- eller tabbseparerade.
    # Vi försöker först med tabb. Vid problem kan vi byta till delimiter=";".
    with ATL_PATH.open("r", encoding="utf-8") as f:
        # Justera delimiter här om din fil är semikolonseparerad.
        reader = csv.DictReader(f, delimiter="\t")
        for raw in reader:
            if not raw:
                continue

            try:
                arbetsmoment = int(raw.get("Arbetsmoment") or 0)
            except ValueError:
                continue

            times: Dict[str, float] = {}
            for key, value in raw.items():
                if key in (
                    "Arbetsmoment",
                    "Grupp",
                    "Rad",
                    "Moment/Typ/Sort",
                    "Underlag/Variant",
                    "Enhet",
                ) or not value:
                    continue

                key_str = str(key).strip()
                val_str = str(value).strip().replace(",", ".")
                try:
                    t = float(val_str)
                except ValueError:
                    continue
                times[key_str] = t

            row = ATLRow(
                arbetsmoment=arbetsmoment,
                grupp=str(raw.get("Grupp") or "").strip(),
                rad=str(raw.get("Rad") or "").strip(),
                moment_text=str(raw.get("Moment/Typ/Sort") or "").strip(),
                underlag_text=str(raw.get("Underlag/Variant") or "").strip(),
                enhet=str(raw.get("Enhet") or "").strip(),
                times=times,
            )
            rows.append(row)

    _ATL_CACHE = rows
    print(f"[ai_suggestions] Läste {len(rows)} ATL-rader från {ATL_PATH}")
    return rows


def _tokenize(text: str) -> List[str]:
    text = text.lower()
    # enkel tokenisering – bokstäver/siffror inkl åäö
    return re.findall(r"[a-z0-9åäö]+", text)


def _similarity_score(segment: str, row: ATLRow) -> float:
    """
    Enkel heuristik för likhet mellan ett textsegment och en ATL-rad.

    Vi använder token-overlap (Jaccard) + liten bonus för fler gemensamma ord.
    Det här är bara ett filter för vilka rader GPT ska få – själva "intelligensen"
    kommer i nästa steg hos GPT.
    """
    seg_tokens = set(_tokenize(segment))
    if not seg_tokens:
        return 0.0

    text = f"{row.moment_text} {row.underlag_text} {row.enhet}"
    row_tokens = set(_tokenize(text))
    if not row_tokens:
        return 0.0

    overlap = seg_tokens & row_tokens
    if not overlap:
        return 0.0

    # Jaccard + bonus
    jaccard = len(overlap) / len(seg_tokens | row_tokens)
    bonus = 0.02 * len(overlap)
    return jaccard + bonus


def find_atl_candidates_for_segment(
    segment_text: str,
    max_rows: int = 20,
    min_score: float = 0.05,
) -> List[ATLRow]:
    """
    Returnerar de ATL-rader som språkligt liknar segmentet mest.

    max_rows: hur många rader vi max skickar till GPT per segment.
    min_score: filter så att helt irrelevanta rader faller bort.
    """
    atl_rows = load_atl_rows()
    if not atl_rows:
        return []

    scored: List[Tuple[float, ATLRow]] = []
    for row in atl_rows:
        score = _similarity_score(segment_text, row)
        if score >= min_score:
            scored.append((score, row))

    # sortera bästa först
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:max_rows]
    return [r for _, r in top]


def build_gpt_input_with_atl_for_segments(
    segments: List[Dict[str, Any]],
    max_rows_per_segment: int = 20,
) -> Dict[str, Any]:
    """
    Bygger gpt_input-struktur att skickas till AIClient.generate_tasks,
    där varje segment får en lista över atl_candidates.

    Struktur:

    {
      "segments": [...],
      "atl_candidates": [
        {
          "segment_id": "...",
          "segment_text": "...",
          "rows": [
            {
              "arbetsmoment": 501,
              "moment_id": "501",
              "grupp": "501",
              "rad": "10",
              "moment_text": "...",
              "underlag_text": "...",
              "enhet": "m rör",
              "times": { "0": 0.03, "-1": 0.06, ... }
            },
            ...
          ]
        },
        ...
      ]
    }
    """
    atl_candidates: List[Dict[str, Any]] = []

    for seg in segments:
        seg_id = seg.get("segment_id") or ""
        seg_text = seg.get("segment_text") or ""
        if not seg_id or not seg_text:
            continue

        candidates = find_atl_candidates_for_segment(
            segment_text=seg_text,
            max_rows=max_rows_per_segment,
        )

        rows_payload: List[Dict[str, Any]] = []
        for row in candidates:
            rows_payload.append(
                {
                    "arbetsmoment": row.arbetsmoment,
                    "moment_id": row.id_str,
                    "grupp": row.grupp,
                    "rad": row.rad,
                    "moment_text": row.moment_text,
                    "underlag_text": row.underlag_text,
                    "enhet": row.enhet,
                    "times": row.times,
                }
            )

        atl_candidates.append(
            {
                "segment_id": seg_id,
                "segment_text": seg_text,
                "rows": rows_payload,
            }
        )

    return {
        "segments": segments,
        "atl_candidates": atl_candidates,
    }


if __name__ == "__main__":
    # Enkel CLI-hjälp för materialdelen:
    # 1) Läs topp saknade refs
    # 2) Skriv ut prompt till konsolen
    top = get_top_missing_material_refs(50)
    prompt = build_material_mapping_prompt(top)
    print(prompt)
