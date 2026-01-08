from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any


# Projektrot, t.ex. D:\dockit-ai
ROOT = Path(__file__).resolve().parents[2]

# Runtime-sanning (kompilerad, innehåller kolumnen "Del")
ATL_CSV_PATH = ROOT / "knowledge" / "atl" / "compiled" / "atl_total.csv"

# Enkel cache (vi vill inte läsa CSV på varje call)
_ATL_ROWS: Optional[List[Dict[str, str]]] = None

_VARIANT_KEYS = ["0", "-1", "-2", "-3", "-4", "-5", "-6", "-7", "-8", "-9"]


def _load_atl_rows() -> List[Dict[str, str]]:
    """
    Läser ATL som semikolon-separerad CSV och returnerar alla rader.
    """
    global _ATL_ROWS
    if _ATL_ROWS is not None:
        return _ATL_ROWS

    if not ATL_CSV_PATH.exists():
        raise FileNotFoundError(f"Hittar inte ATL-fil på: {ATL_CSV_PATH}")

    with ATL_CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        _ATL_ROWS = [row for row in reader if isinstance(row, dict)]

    return _ATL_ROWS


def _find_unique_row(moment_name: str, *, del_hint: Optional[int] = None) -> Optional[Dict[str, str]]:
    """
    Returnerar exakt 1 ATL-rad för Moment/Typ/Sort (om möjligt), annars None.

    Samma determinism-regler som lookup_time_minutes:
    - filtrera på del_hint om angivet
    - annars, om flera matchar: försök Del=7 som bakåtkompatibilitet
    - om fortfarande fler än 1: returnera None (ingen gissning)
    """
    moment_name = (moment_name or "").strip()
    if not moment_name:
        return None

    rows = _load_atl_rows()
    matches = [r for r in rows if (r.get("Moment/Typ/Sort") or "").strip() == moment_name]
    if not matches:
        return None

    if del_hint is not None:
        matches_hint = [r for r in matches if (r.get("Del") or "").strip() == str(int(del_hint))]
        matches = matches_hint or matches

    if del_hint is None and len(matches) > 1:
        matches7 = [r for r in matches if (r.get("Del") or "").strip() == "7"]
        if len(matches7) == 1:
            matches = matches7

    if len(matches) != 1:
        return None

    return matches[0]


def lookup_time_minutes(moment_name: str, variant_index: int, *, del_hint: Optional[int] = None) -> Optional[float]:
    """
    Slår upp tid (minuter per enhet) för givet Moment/Typ/Sort + variant.

    - moment_name: exakt text i kolumnen "Moment/Typ/Sort"
    - variant_index: t.ex. 0, -1, -2 ... som i kolumnrubrikerna "0", "-1", ...
    - del_hint: om angivet (t.ex. 7) filtrerar vi matchning till den delen

    Viktigt:
    - Om flera rader matchar och vi inte kan välja deterministiskt -> returnera None (ingen gissning).
    """
    moment_name = (moment_name or "").strip()
    key = str(int(variant_index))  # normalisera till "0", "-1", ...

    if not moment_name:
        return None

    row = _find_unique_row(moment_name, del_hint=del_hint)
    if row is None:
        return None

    raw_val = (row.get(key) or "").strip()
    if not raw_val:
        return None

    raw_normalized = raw_val.replace(",", ".")
    try:
        hours_per_unit = float(raw_normalized)
    except ValueError:
        return None

    # ATL-värden i filer är timmar per enhet (t.ex. 0,03 h/m) -> returnera minuter per enhet
    return hours_per_unit * 60.0


def get_atl_time_minutes(arbetsmoment: str, variant_index: int) -> float:
    """
    Wrapper: returnerar alltid minuter per enhet (float).
    (Behåller signaturen för nuvarande call sites.)
    """
    minutes = lookup_time_minutes(arbetsmoment, variant_index, del_hint=None)
    if minutes is None:
        return 0.0
    return float(minutes)


def get_atl_variant_options(moment_name: str, *, del_hint: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """
    Returnerar underlag för UI: vilka varianter som finns för ett ATL-moment.

    Output (exempel):
    {
      "moment": "...",
      "del": 6,
      "underlag_variant_text": "...",
      "enhet": "m rör",
      "variants": [
        {"variant": 0, "hours_per_unit": 0.03, "minutes_per_unit": 1.8},
        {"variant": -7, "hours_per_unit": 0.05, "minutes_per_unit": 3.0},
        ...
      ]
    }

    Om momentet är ambigöst (flera rader) -> None.
    """
    row = _find_unique_row(moment_name, del_hint=del_hint)
    if row is None:
        return None

    underlag_text = (row.get("Underlag/Variant") or "").strip()
    enhet = (row.get("Enhet") or "").strip()
    del_str = (row.get("Del") or "").strip()
    del_val: Optional[int] = None
    try:
        del_val = int(del_str) if del_str else None
    except Exception:
        del_val = None

    variants: List[Dict[str, Any]] = []
    for k in _VARIANT_KEYS:
        raw_val = (row.get(k) or "").strip()
        if not raw_val:
            continue
        try:
            hours = float(raw_val.replace(",", "."))
        except Exception:
            continue
        variants.append(
            {
                "variant": int(k),
                "hours_per_unit": hours,
                "minutes_per_unit": hours * 60.0,
            }
        )

    return {
        "moment": (row.get("Moment/Typ/Sort") or "").strip(),
        "del": del_val,
        "underlag_variant_text": underlag_text,
        "enhet": enhet,
        "variants": variants,
    }


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("Användning:")
        print('  python -m src.services.atl_lookup "Moment/Typ/Sort-text" <variant_index>')
        print("Exempel:")
        print('  python -m src.services.atl_lookup "Infällda rör (VP 16–20 mm)" 0')
        return 1

    moment_name = argv[1]
    try:
        variant_index = int(argv[2])
    except ValueError:
        print(f"Ogiltigt variant_index: {argv[2]}")
        return 1

    minutes = lookup_time_minutes(moment_name, variant_index)
    print(f"Arbetsmoment: '{moment_name}', variant {variant_index} → {minutes} minuter")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
