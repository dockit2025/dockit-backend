# test_lookup_with_fallback.py
from __future__ import annotations

import os
import sys
import glob
from pathlib import Path
from typing import List, Dict, Optional

from src.server.loaders.atl_loader_new import ATLLoader
from src.server.loaders.pricelist_loader import PriceListLoader, PriceListConfig


def _resolve_pricelist_path() -> str:
    """
    Hitta prislistan robust:
    1) PRICELIST_PATH (fil eller mapp)
    2) knowledge/catalogs/Storel-GN.csv
    3) knowledge/catalogs/Storel-GN (utan .csv) eller med .csv tillagt
    4) första *.csv i knowledge/catalogs/
    5) D:\dockit-ai\knowledge\catalogs\Storel-GN.csv
    6) valfri *.csv rekursivt under knowledge/catalogs/
    """
    # 1) Miljövariabel
    env_p = os.environ.get("PRICELIST_PATH")
    if env_p:
        p = Path(env_p)
        if p.is_file():
            return str(p)
        if p.is_dir():
            candidates = sorted(p.glob("*.csv"))
            if candidates:
                return str(candidates[0])
        if not p.suffix and p.with_suffix(".csv").is_file():
            return str(p.with_suffix(".csv"))

    # 2) Repo-relativ standard
    base = Path("knowledge/catalogs")

    # 2a) exakt fil
    p_csv = base / "Storel-GN.csv"
    if p_csv.is_file():
        return str(p_csv)

    # 2b) namn utan extension (om OS döljer .csv) eller prova med .csv
    p_noext = base / "Storel-GN"
    if p_noext.is_file():
        return str(p_noext)
    if p_noext.with_suffix(".csv").is_file():
        return str(p_noext.with_suffix(".csv"))

    # 2c) första CSV i katalogen
    first_csvs = sorted(base.glob("*.csv"))
    if first_csvs:
        return str(first_csvs[0])

    # 3) Absolut fallback
    abs_csv = Path(r"D:\dockit-ai\knowledge\catalogs\Storel-GN.csv")
    if abs_csv.is_file():
        return str(abs_csv)

    # 4) Rekursiv sista chans
    any_csv = glob.glob(str(base / "**" / "*.csv"), recursive=True)
    if any_csv:
        return any_csv[0]

    # Om inget hittas, returnera standardstigen (loadern får kasta fel)
    return str(p_csv)


def _fmt_time(v: Optional[float]) -> str:
    if v is None:
        return "-"
    try:
        return f"{float(v):.2f}"
    except Exception:
        return "-"


def main() -> None:
    query = " ".join(sys.argv[1:]).strip() or "downlight"
    print(f"Sökterm: {query}")

    # 1) Försök ATL
    atl = ATLLoader()
    atl.load()
    atl_hits: List[Dict[str, Optional[str]]] = atl.search(query, top_k=5)

    if atl_hits:
        print("\n=== Träffar i ATL (top 5 rader, expanderat per variant) ===")
        for i, r in enumerate(atl_hits, 1):
            print(
                f"{i:>2}. moment: {r.get('moment_name')} | arb.moment: {r.get('arbetsmoment')} "
                f"| variant: {r.get('variant')} | enhet: {r.get('unit')} | tid/h per enhet: {_fmt_time(r.get('time_h_per_unit'))}"
            )
        return

    # 2) Fallback: Prislista
    print("\nInga ATL-träffar – söker i prislistan …")
    csv_path = _resolve_pricelist_path()
    print(f"Prislista hittad: {csv_path}")

    pl = PriceListLoader(PriceListConfig(csv_path=csv_path))
    pl.load()

    price_hits = pl.search(query, top_k=10)

    # Var EXPRESS med tomkontroll för DataFrame
    if price_hits is None or getattr(price_hits, "empty", False):
        print("Inga träffar i prislistan heller.")
        return

    print(f"=== Träffar i prislistan (top 10) — fil: {csv_path} ===")
    for i, (_, r) in enumerate(price_hits.head(10).iterrows(), 1):
        artikel = r.get("Artikelnummer") or r.get("artikelnummer") or "-"
        namn = r.get("Benämning") or r.get("namn") or "-"
        enhet = r.get("Enhet") or r.get("enhet") or "-"
        pris = (
            r.get("Pris")
            or r.get("pris")
            or r.get("Pris_SEK")
            or r.get("pris_sek")
            or "-"
        )
        print(f"{i:>2}. {artikel} | {namn} | enhet: {enhet} | pris: {pris}")


if __name__ == "__main__":
    main()
