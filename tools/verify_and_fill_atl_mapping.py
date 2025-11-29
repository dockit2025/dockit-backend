from __future__ import annotations
import argparse
import os
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import pandas as pd
import yaml

ATL_CSV_PATH = Path("knowledge/atl/Del7_ATL_Total.csv")
MAPPING_YAML_PATH = Path("knowledge/atl/atl_mapping.yaml")

def _normalize_text(s: str) -> str:
    if s is None:
        return ""
    s = str(s)
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\u00a0", " ")
    s = s.lower()
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def _read_atl_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Saknas: {path}")
    last_err = None
    for sep in (";", ","):
        try:
            df = pd.read_csv(path, encoding="utf-8-sig", sep=sep, dtype=str, engine="python")
            df.columns = [str(c).strip() for c in df.columns]
            return df
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"Kunde inte läsa CSV med ; eller ,  ({last_err})")

def _load_yaml(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or []
    if isinstance(data, dict):
        out: List[Dict[str, Any]] = []
        for k, v in data.items():
            syns = v if isinstance(v, list) else ([v] if isinstance(v, str) else [])
            out.append({"phrase": k, "synonyms": syns})
        return out
    if isinstance(data, list):
        return data
    return []

def _save_yaml(path: Path, items: List[Dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(items, f, allow_unicode=True, sort_keys=False)

def _build_search_index(df: pd.DataFrame) -> pd.DataFrame:
    col = "Moment/Typ/Sort"
    if col not in df.columns:
        raise KeyError(f"Saknar ATL-kolumn: {col}")
    df = df.copy()
    df["_moment_norm"] = df[col].map(_normalize_text)
    return df

def _candidates_for_terms(df_idx: pd.DataFrame, terms: List[str]) -> List[str]:
    if not terms:
        return []
    terms_norm = [_normalize_text(t) for t in terms if t]
    mask = pd.Series(False, index=df_idx.index)
    for t in terms_norm:
        mask = mask | df_idx["_moment_norm"].str.contains(re.escape(t), na=False)
    vals = df_idx.loc[mask, "Moment/Typ/Sort"].astype(str).dropna().unique().tolist()
    return vals

def _validate_search_exists(df_idx: pd.DataFrame, search: str) -> bool:
    s_norm = _normalize_text(search)
    return any(df_idx["_moment_norm"] == s_norm)

def main() -> None:
    ap = argparse.ArgumentParser(description="Validera och auto-fylla atl_mapping.yaml mot ATL CSV.")
    ap.add_argument("--write", action="store_true", help="Skriv tillbaka uppdaterad YAML när entydig match hittas.")
    args = ap.parse_args()

    df = _read_atl_csv(ATL_CSV_PATH)
    df_idx = _build_search_index(df)

    items = _load_yaml(MAPPING_YAML_PATH)
    if not items:
        print(f"Ingen mapping hittad i {MAPPING_YAML_PATH}")
        return

    ok = 0
    fixed = 0
    unresolved: List[Tuple[str, List[str]]] = []
    missing: List[str] = []

    for it in items:
        phrase = str(it.get("phrase") or "").strip()
        synonyms = it.get("synonyms") or []
        if isinstance(synonyms, str):
            synonyms = [synonyms]
        synonyms = [str(s).strip() for s in synonyms if s]

        search = it.get("search")
        if search:
            if _validate_search_exists(df_idx, search):
                ok += 1
            else:
                missing.append(phrase or "(okänd)")
            continue

        terms = [phrase] + synonyms
        cands = _candidates_for_terms(df_idx, terms)

        if len(cands) == 1:
            it["search"] = cands[0]
            fixed += 1
        elif len(cands) == 0:
            unresolved.append((phrase or "(tom phrase)", []))
        else:
            unresolved.append((phrase or "(tom phrase)", cands[:10]))

    print(f"\n=== RESULTAT ===")
    print(f"Poster med giltig search: {ok}")
    print(f"Auto-fyllda (entydig träff): {fixed}")
    print(f"Obesvarade/ambigua: {len(unresolved)}")
    print(f"Ogiltiga 'search' (finns ej i ATL): {len(missing)}")

    if missing:
        print("\n-- Ogiltiga 'search' (matchar ej ATL):")
        for p in missing[:50]:
            print(f"  - {p}")
        if len(missing) > 50:
            print("  ...")

    if unresolved:
        print("\n-- Obesvarade/ambigua fraser och kandidater (max 10 per rad):")
        for p, cs in unresolved[:100]:
            if not cs:
                print(f"  - {p}: (inga kandidater)")
            else:
                print(f"  - {p}:")
                for c in cs:
                    print(f"      • {c}")
        if len(unresolved) > 100:
            print("  ...")

    if args.write:
        _save_yaml(MAPPING_YAML_PATH, items)
        print(f"\nUppdaterad YAML sparad: {MAPPING_YAML_PATH}")

if __name__ == "__main__":
    main()
