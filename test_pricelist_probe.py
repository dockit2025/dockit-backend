# test_pricelist_probe.py
from __future__ import annotations
from pathlib import Path
import pandas as pd

CSV = Path(r"D:\dockit-ai\knowledge\catalogs\Storel-GN.csv")

def _read_any(path: Path) -> pd.DataFrame:
    # Testa olika sep + header
    for sep in ["\t", ";", ",", "|"]:
        for header in [0, None]:
            try:
                df = pd.read_csv(path, sep=sep, header=header, engine="python", dtype=str, encoding="utf-8-sig")
                if df is not None and not df.empty:
                    df.columns = [str(c).strip() for c in df.columns]
                    return df
            except Exception:
                pass
    # Sista chans
    df = pd.read_csv(path, sep=None, header=None, engine="python", dtype=str, encoding="utf-8-sig")
    df.columns = [f"col_{i}" for i in range(len(df.columns))]
    return df

def main():
    if not CSV.is_file():
        print(f"Filen saknas: {CSV}")
        return

    df = _read_any(CSV)
    print("Antal rader:", len(df))
    print("Kolumner:", list(df.columns))

    print("\nFörsta 5 rader:")
    with pd.option_context("display.max_colwidth", 200, "display.width", 200):
        print(df.head(5).to_string(index=False))

    # Skapa ev. Benämning när saknas (positionell tolkning)
    if all(c.startswith("col_") for c in df.columns):
        # typisk ordning: 0=Artikelnummer, 1=Benämning, 2=Enhet, 3=Varugrupp, 4=Pris
        rename_map = {}
        if "col_0" in df.columns: rename_map["col_0"] = "Artikelnummer"
        if "col_1" in df.columns: rename_map["col_1"] = "Benämning"
        if "col_2" in df.columns: rename_map["col_2"] = "Enhet"
        if "col_3" in df.columns: rename_map["col_3"] = "Varugrupp"
        if "col_4" in df.columns: rename_map["col_4"] = "Pris"
        df = df.rename(columns=rename_map)

    # Lista topp 5 träffar med 'downlight' över ALLA kolumner
    term = "downlight"
    mask_any = df.apply(lambda s: s.astype(str).str.lower().str.contains(term, regex=False, na=False)).any(axis=1)
    hits = df[mask_any].head(10)
    print(f"\nTräffar (alla kolumner) på '{term}': {len(hits)}")
    with pd.option_context("display.max_colwidth", 200, "display.width", 200):
        print(hits.to_string(index=False))

if __name__ == "__main__":
    main()
