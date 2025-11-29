from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Optional

# Projektrot, t.ex. D:\dockit-ai
ROOT = Path(__file__).resolve().parents[2]

# Sökväg till ATL-filen (justera filnamn om du döpt den annorlunda)
ATL_CSV_PATH = ROOT / "knowledge" / "atl" / "Del7_ATL_Total.csv"


def _load_atl_rows():
    """
    Läser in ATL-filen som semikolon-separerad CSV.
    Returnerar en iterator med dictar per rad.
    """
    if not ATL_CSV_PATH.exists():
        raise FileNotFoundError(f"Hittar inte ATL-fil på: {ATL_CSV_PATH}")

    with ATL_CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            yield row


def lookup_time_minutes(moment_name: str, variant_index: int) -> Optional[float]:
    """
    Slår upp tid (minuter per enhet) för givet arbetsmoment + variantindex.

    moment_name: exakt text i kolumnen "Moment/Typ/Sort"
    variant_index: t.ex. 0, -1, -2 ... som i kolumnrubrikerna "0", "-1", ...
    """
    moment_name = (moment_name or "").strip()
    key = str(variant_index)

    if not moment_name:
        return None

    for row in _load_atl_rows():
        row_name = (row.get("Moment/Typ/Sort") or "").strip()
        if row_name != moment_name:
            continue

        raw_val = (row.get(key) or "").strip()
        if not raw_val:
            # ingen tid angiven för den här varianten
            return None

        # Byt ut svensk decimal-komma mot punkt
        raw_normalized = raw_val.replace(",", ".")
        try:
            minutes = float(raw_normalized)
        except ValueError:
            return None

        return minutes

    # Hittade inget moment med exakt den texten
    return None


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("Användning:")
        print("  python atl_lookup.py \"Moment/Typ/Sort-text\" <variant_index>")
        print("Exempel:")
        print("  python atl_lookup.py \"Infällda rör (VP 16–20 mm)\" 0")
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


def get_atl_time_minutes(arbetsmoment: str, variant_index: int) -> float:
    """
    Wrapper kring lookup_time_minutes.

    - arbetsmoment: text i kolumnen "Moment/Typ/Sort"
    - variant_index: t.ex. 0, -1, -2, ...

    ATL-värdena tolkas nu som timmar per enhet.
    Vi returnerar alltid minuter per enhet till resten av systemet.
    """
    raw = lookup_time_minutes(arbetsmoment, variant_index)
    if raw is None:
        return 0.0
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return val * 60.0

