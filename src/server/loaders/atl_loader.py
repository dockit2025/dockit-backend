from __future__ import annotations
import csv, re
from pathlib import Path
from typing import List, Dict, Optional

ATL_INDEX: List[Dict] = []
VARIANT_COLS = ["0","-1","-2","-3","-4","-5","-6","-7","-8","-9"]

def _dec_to_float(val: str) -> Optional[float]:
    if val is None: return None
    s = str(val).strip().replace(",", ".")
    if not s: return None
    try: return float(s)
    except ValueError: return None

def _slug(s: str) -> str:
    s = s or ""
    s = re.sub(r"[^A-Za-z0-9]+","_",s).strip("_").lower()
    s = re.sub(r"_+","_",s)
    return s

def _guess_unit(enhet_field: str) -> str:
    if not enhet_field: return ""
    s = enhet_field.strip().lower()
    if s.startswith("m"): return "m"
    if "st" in s: return "st"
    return s

def init_atl_index(project_root: Optional[str] = None) -> int:
    root = Path(project_root) if project_root else Path(__file__).resolve().parents[3]
    csv_path = root / "knowledge" / "atl" / "Del7_ATL_Total.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"Hittar inte ATL-filen: {csv_path}")

    ATL_INDEX.clear()
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            arbetsmoment = row.get("Arbetsmoment")
            grupp = row.get("Grupp")
            rad = row.get("Rad")
            name = row.get("Moment/Typ/Sort") or ""
            variant_text = row.get("Underlag/Variant") or ""
            unit = _guess_unit(row.get("Enhet") or "")
            base_code = _slug(f"{name}_{unit}")

            for vcol in VARIANT_COLS:
                if vcol in row:
                    t = _dec_to_float(row.get(vcol))
                    if t is None: continue
                    ATL_INDEX.append({
                        "moment_code": base_code,
                        "moment_name": name,
                        "group": grupp,
                        "row": rad,
                        "arbetsmoment": arbetsmoment,
                        "variant": vcol,
                        "variant_text": variant_text,
                        "unit": unit,
                        "time_h_per_unit": t
                    })
    return len(ATL_INDEX)

def find_time_by_name(name_query: str, prefer_variant: Optional[str] = None) -> Optional[Dict]:
    q = (name_query or "").strip().lower()
    if not q: return None
    cands = [r for r in ATL_INDEX if q in (r["moment_name"] or "").lower()]
    if not cands: return None
    if prefer_variant:
        for r in cands:
            if r.get("variant") == str(prefer_variant):
                return r
    for r in cands:
        if r.get("variant") == "0":
            return r
    return cands[0] if cands else None

def find_times(name_query: str) -> List[Dict]:
    q = (name_query or "").strip().lower()
    if not q: return []
    return [r for r in ATL_INDEX if q in (r["moment_name"] or "").lower()]
