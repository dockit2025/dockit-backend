# validate_atl_mapping.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union
import sys
import math
import argparse
import json
import re

CANDIDATE_FILENAMES = ("atl_mapping.yaml", "atl_mapping.yml")
ATL_GLOB_HINTS = [
    "**/atl*.yaml", "**/atl*.yml",
    "**/*atl*mapping*.yaml", "**/*atl*mapping*.yml",
    "**/*atl*map*.yaml", "**/*atl*map*.yml",
    "**/atl*.json", "**/*atl*mapping*.json",
]

ALLOWED_UNITS = {"st", "m", "h", "tim", "m2", "m^2", "m²", "m3", "m^3", "m³", "punkt"}
REQ_ATL_FIELDS = ("moment_code", "moment_name", "unit", "time_h_per_unit")

def find_project_root(start: Path) -> Path:
    cur = start.resolve()
    for _ in range(12):
        if (cur / "dockit.db").exists() or (cur / "src" / "server").exists() or (cur / "dockit-ui").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return start.resolve()

def discover_candidates(root: Path) -> List[Path]:
    found: List[Path] = []
    for pattern in ATL_GLOB_HINTS:
        found.extend(root.glob(pattern))
    uniq = sorted({p.resolve() for p in found}, key=lambda p: (len(p.as_posix()), p.as_posix()))
    return uniq

def find_atl_mapping(root: Path) -> Optional[Path]:
    for fn in CANDIDATE_FILENAMES:
        p = root / fn
        if p.exists():
            return p
    matches: List[Path] = []
    for fn in CANDIDATE_FILENAMES:
        matches += list(root.rglob(fn))
    if matches:
        matches.sort(key=lambda p: len(p.as_posix()))
        return matches[0]
    return None

def load_yaml_or_json(path: Path) -> Any:
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml
        except Exception:
            print("ERROR: PyYAML saknas. Installera: pip install pyyaml", file=sys.stderr)
            raise
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    if path.suffix.lower() == ".json":
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    try:
        import yaml  # type: ignore
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return None

def to_str_or_none(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s if s != "" else None
    return str(v)

def to_float_or_none(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
        return float(str(v).replace(",", "."))
    except Exception:
        return None

def to_int_or_str_or_none(v: Any) -> Optional[Union[int, str]]:
    if v is None:
        return None
    if isinstance(v, (int, str)) and not isinstance(v, bool):
        s = str(v).strip()
        return int(s) if s.isdigit() else s
    try:
        return int(v)
    except Exception:
        s = str(v).strip()
        return s if s else None

# ----------------- MODE DETEKTION -----------------
def detect_mode(data: Any) -> str:
    """
    Returnerar:
      - "ATL_ROWS": klassiskt ATL-radformat (moment_code/moment_name/unit/time_h_per_unit)
      - "PHRASE_MAP": fras→ATL (phrase, moment_code, variant/variants)
      - "UNKNOWN": annat/tomt
    """
    sample: List[Dict[str, Any]] = []
    if isinstance(data, list):
        for e in data:
            if isinstance(e, dict):
                sample.append(e)
                if len(sample) >= 20:
                    break
    elif isinstance(data, dict):
        for _, v in list(data.items())[:20]:
            if isinstance(v, dict):
                sample.append(v)

    def has_any(keys: Iterable[str], d: Dict[str, Any]) -> bool:
        return any(k in d for k in keys)

    if sample and all(has_any(REQ_ATL_FIELDS, e) for e in sample if isinstance(e, dict)):
        return "ATL_ROWS"

    if sample and all(has_any(("phrase", "moment_code"), e) for e in sample if isinstance(e, dict)):
        return "PHRASE_MAP"

    return "UNKNOWN"

# ----------------- VALIDATION: ATL_ROWS -----------------
def normalize_atl_row(e: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(e)
    out["moment_code"] = to_str_or_none(e.get("moment_code"))
    out["moment_name"] = to_str_or_none(e.get("moment_name"))
    out["unit"] = to_str_or_none(e.get("unit"))
    out["time_h_per_unit"] = to_float_or_none(e.get("time_h_per_unit"))
    out["variant"] = to_int_or_str_or_none(e.get("variant"))
    out["variant_text"] = to_str_or_none(e.get("variant_text"))
    out["group"] = to_str_or_none(e.get("group"))
    out["row"] = to_str_or_none(e.get("row"))
    am = e.get("arbetsmoment", None)
    out["arbetsmoment"] = None if am is None else to_str_or_none(am)
    return out

def iter_atl_rows(data: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(data, list):
        for i, e in enumerate(data):
            if isinstance(e, dict):
                yield normalize_atl_row(e)
            else:
                yield {"__error__": f"Rad {i}: förväntade dict men fick {type(e).__name__}"}
        return
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, dict):
                row = {"key": k, **v}
                yield normalize_atl_row(row)
            else:
                yield {"__error__": f"Nyckel {k!r}: förväntade dict men fick {type(v).__name__}"}
        return
    yield {"__fatal__": f"Toppnivå måste vara list eller dict, fick {type(data).__name__}"}

def validate_atl_rows(entries: Iterable[Dict[str, Any]], label: str) -> int:
    total = 0
    errors: List[str] = []
    warnings: List[str] = []
    duplicates: Dict[Tuple[Optional[str], Optional[Union[int, str]]], int] = {}
    unknown_units: set = set()
    samples: List[Dict[str, Any]] = []

    for idx, e in enumerate(entries, start=1):
        total += 1
        if "__fatal__" in e:
            print("=== ATL Mapping – Schema- och kvalitetskontroll ===")
            print(f"Källa: {label}")
            print("Fel:")
            print(f" - {e['__fatal__']}")
            return 1
        if "__error__" in e:
            errors.append(e["__error__"])
            continue

        if len(samples) < 5:
            samples.append(e)

        for f in REQ_ATL_FIELDS:
            if e.get(f) is None:
                errors.append(f"Rad {idx}: saknar obligatoriskt fält '{f}'.")

        mc = e.get("moment_code")
        mn = e.get("moment_name")
        unit = e.get("unit")
        tpu = e.get("time_h_per_unit")
        variant = e.get("variant")
        group = e.get("group")
        row = e.get("row")

        if mc is not None and not isinstance(mc, str):
            errors.append(f"Rad {idx}: moment_code ska vara str.")
        if mn is not None and not isinstance(mn, str):
            errors.append(f"Rad {idx}: moment_name ska vara str.")
        if unit is not None and not isinstance(unit, str):
            errors.append(f"Rad {idx}: unit ska vara str.")
        if tpu is not None:
            if not isinstance(tpu, float):
                errors.append(f"Rad {idx}: time_h_per_unit kunde inte tolkas som float.")
            elif not (tpu >= 0.0 and math.isfinite(tpu)):
                errors.append(f"Rad {idx}: time_h_per_unit måste vara >= 0 och ändligt.")

        if unit is not None and unit.lower() not in ALLOWED_UNITS:
            unknown_units.add(unit)

        if group is not None and not group.isdigit():
            warnings.append(f"Rad {idx}: group '{group}' är inte numerisk sträng.")
        if row is not None and not row.isdigit():
            warnings.append(f"Rad {idx}: row '{row}' är inte numerisk sträng.")

        key = (mc, variant)
        if mc is not None:
            duplicates[key] = duplicates.get(key, 0) + 1

    print("=== ATL Mapping – Schema- och kvalitetskontroll (ATL-rader) ===")
    print(f"Källa: {label}")
    print(f"Antal poster: {total}")

    if samples:
        print("\nExempelposter (upp till 5):")
        for e in samples:
            print(f" - {e.get('moment_code')} | {e.get('moment_name')} | unit={e.get('unit')} | time_h_per_unit={e.get('time_h_per_unit')} | variant={e.get('variant')}")

    if unknown_units:
        print("\nOkända/enhetsvarningar:")
        for u in sorted(unknown_units):
            print(f" - Oidentifierad enhet: {u}")

    dup_list = [(k, c) for k, c in duplicates.items() if c > 1]
    if dup_list:
        print("\nDubbletter (moment_code, variant):")
        dup_list.sort(key=lambda x: (-x[1], x[0][0] or "", str(x[0][1])))
        for (mc, variant), count in dup_list[:50]:
            print(f" - ({mc}, {variant}) förekommer {count} gånger")
        if len(dup_list) > 50:
            print(f" ... och {len(dup_list)-50} fler dubblettnycklar.")

    if warnings:
        print("\nVarningar:")
        for w in warnings[:100]:
            print(f" - {w}")
        if len(warnings) > 100:
            print(f" ... {len(warnings)-100} fler varningar.")

    if errors:
        print("\nFel:")
        for e in errors[:200]:
            print(f" - {e}")
        if len(errors) > 200:
            print(f" ... {len(errors)-200} fler fel.")
        return 1

    return 0

# ----------------- VALIDATION: PHRASE_MAP -----------------
def normalize_phrase_row(e: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    out["phrase"] = to_str_or_none(e.get("phrase"))
    out["moment_code"] = to_str_or_none(e.get("moment_code"))
    # stöd både variant (singel) och variants (lista)
    raw_variants = e.get("variants", e.get("variant"))
    if isinstance(raw_variants, list):
        out["variants"] = [to_int_or_str_or_none(v) for v in raw_variants]
    else:
        v = to_int_or_str_or_none(raw_variants)
        out["variants"] = [v] if v is not None else []
    # valfria fält
    out["notes"] = to_str_or_none(e.get("notes"))
    out["confidence"] = to_float_or_none(e.get("confidence"))
    return out

def iter_phrase_map(data: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(data, list):
        for i, e in enumerate(data):
            if isinstance(e, dict):
                yield normalize_phrase_row(e)
            else:
                yield {"__error__": f"Rad {i}: förväntade dict men fick {type(e).__name__}"}
        return
    if isinstance(data, dict):
        # tillåt mapping: key=phrase, value=dict
        for k, v in data.items():
            if isinstance(v, dict):
                row = {"phrase": k, **v}
                yield normalize_phrase_row(row)
            else:
                yield {"__error__": f"Nyckel {k!r}: förväntade dict men fick {type(v).__name__}"}
        return
    yield {"__fatal__": f"Toppnivå måste vara list eller dict, fick {type(data).__name__}"}

def validate_phrase_map(entries: Iterable[Dict[str, Any]], label: str) -> int:
    total = 0
    errors: List[str] = []
    warnings: List[str] = []
    dup_phrase: Dict[str, int] = {}
    samples: List[Dict[str, Any]] = []

    def norm_phrase(p: Optional[str]) -> Optional[str]:
        return p.lower().strip() if isinstance(p, str) else None

    mc_pat = re.compile(r"^[A-Z0-9_][A-Z0-9_\-\.]*$")  # tillåt stora bokstäver/siffror/underscore

    for idx, e in enumerate(entries, start=1):
        total += 1
        if "__fatal__" in e:
            print("=== ATL Mapping – Frasmappningskontroll ===")
            print(f"Källa: {label}")
            print("Fel:")
            print(f" - {e['__fatal__']}")
            return 1
        if "__error__" in e:
            errors.append(e["__error__"])
            continue

        if len(samples) < 5:
            samples.append(e)

        phrase = e.get("phrase")
        mc = e.get("moment_code")
        variants = e.get("variants", [])

        if not phrase:
            errors.append(f"Rad {idx}: saknar 'phrase'.")
        if not mc:
            errors.append(f"Rad {idx}: saknar 'moment_code'.")
        elif isinstance(mc, str) and not mc_pat.match(mc):
            warnings.append(f"Rad {idx}: moment_code '{mc}' avviker från rekommenderat format [A-Z0-9_-.].")

        if not isinstance(variants, list):
            errors.append(f"Rad {idx}: 'variants' måste vara lista eller saknas.")
        else:
            # tillåt str/int; tom lista är ok (betyder “ingen variant specificerad”)
            bad = [v for v in variants if not isinstance(v, (int, str))]
            if bad:
                errors.append(f"Rad {idx}: 'variants' innehåller otillåtna värden: {bad!r}")

        np = norm_phrase(phrase)
        if np:
            dup_phrase[np] = dup_phrase.get(np, 0) + 1

    print("=== ATL Mapping – Frasmappningskontroll ===")
    print(f"Källa: {label}")
    print(f"Antal frasmappningar: {total}")

    if samples:
        print("\nExempelposter (upp till 5):")
        for e in samples:
            print(f" - \"{e.get('phrase')}\" → {e.get('moment_code')} | variants={e.get('variants')}")

    dups = [(p, c) for p, c in dup_phrase.items() if c > 1]
    if dups:
        print("\nDubbletter (phrase, case-insensitivt):")
        dups.sort(key=lambda x: -x[1])
        for p, c in dups[:50]:
            print(f" - \"{p}\" förekommer {c} gånger")
        if len(dups) > 50:
            print(f" ... och {len(dups)-50} fler dubbletter.")

    if warnings:
        print("\nVarningar:")
        for w in warnings[:100]:
            print(f" - {w}")
        if len(warnings) > 100:
            print(f" ... {len(warnings)-100} fler varningar.")

    if errors:
        print("\nFel:")
        for e in errors[:200]:
            print(f" - {e}")
        if len(errors) > 200:
            print(f" ... {len(errors)-200} fler fel.")
        return 1

    return 0

# ----------------- MAIN -----------------
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=str, help="Sökväg till ATL-fil (yaml/yml/json).")
    parser.add_argument("--discover", action="store_true", help="Lista möjliga ATL-filer i projektet.")
    args = parser.parse_args()

    start = Path(__file__).parent
    root = find_project_root(start)

    if args.discover:
        print(f"Söker kandidater under: {root}")
        cands = discover_candidates(root)
        if not cands:
            print("Inga kandidater hittades.")
            return 1
        for p in cands[:200]:
            try:
                size = p.stat().st_size
            except Exception:
                size = -1
            rel = p.relative_to(root)
            print(f"- {rel}  ({size} bytes)")
        if len(cands) > 200:
            print(f"... {len(cands)-200} fler träffar undertryckta.")
        return 0

    if args.path:
        path = (root / args.path).resolve() if not Path(args.path).is_absolute() else Path(args.path)
        if not path.exists():
            print(f"ERROR: Filen finns inte: {path}", file=sys.stderr)
            return 1
    else:
        path = find_atl_mapping(root)
        if not path:
            print("ERROR: Hittade ingen atl_mapping.yaml/.yml. Kör med --discover.", file=sys.stderr)
            return 1

    data = load_yaml_or_json(path)
    label = str(path.relative_to(root)) if str(path).startswith(str(root)) else str(path)

    if data is None:
        print("=== ATL Mapping – Kontroll ===")
        print(f"Källa: {label}")
        print("Fel:")
        print(" - Filen verkar vara tom (eller endast kommentarer).")
        return 1

    mode = detect_mode(data)
    if mode == "ATL_ROWS":
        return validate_atl_rows(iter_atl_rows(data), label)
    if mode == "PHRASE_MAP":
        return validate_phrase_map(iter_phrase_map(data), label)

    print("=== ATL Mapping – Kontroll ===")
    print(f"Källa: {label}")
    print("Fel:")
    print(" - Okänt format. Stöd ges för:")
    print("   * ATL-rader (moment_code/moment_name/unit/time_h_per_unit)")
    print("   * Frasmappningar (phrase/moment_code/variant|variants)")
    return 1

if __name__ == "__main__":
    sys.exit(main())
