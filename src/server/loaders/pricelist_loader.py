# src/server/loaders/pricelist_loader.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import pandas as pd


@dataclass
class PriceListConfig:
    # Pekar på en CSV-fil, en mapp med CSV-filer, eller ett mönster som "*.csv"
    csv_path: str = "knowledge/catalogs/Storel-GN.csv"


class PriceListLoader:
    def __init__(self, config: Optional[PriceListConfig] = None) -> None:
        self.config = config or PriceListConfig()
        self.df: Optional[pd.DataFrame] = None
        self.files: List[Path] = []

    # ---- Filupplockning -----------------------------------------------------
    def _resolve_paths(self) -> List[Path]:
        p = Path(self.config.csv_path)
        if p.is_file():
            return [p]
        if p.is_dir():
            return sorted([x for x in p.glob("*.csv") if x.is_file()])
        # wildcard-stöd (t.ex. "...\\Storel-GN\\*.csv")
        if any(ch in p.name for ch in ["*", "?"]):
            return sorted([x for x in p.parent.glob(p.name) if x.is_file()])
        raise FileNotFoundError(f"Hittar ingen prislista vid: {self.config.csv_path}")

    # ---- Läsning med robust semikolon-hantering -----------------------------
    def _read_one_csv(self, path: Path) -> pd.DataFrame:
        # Försök med ';' och några vanliga encodings
        encodings = ["utf-8-sig", "cp1252", "latin-1"]
        for enc in encodings:
            try:
                df = pd.read_csv(
                    path,
                    sep=";",
                    header=0,
                    dtype=str,
                    engine="python",
                    encoding=enc,
                )
                # Om Pandas misslyckade och gav en kolumn där rubriken innehåller ';',
                # gör en manuell split.
                if len(df.columns) == 1 and ";" in str(df.columns[0]):
                    raise ValueError("Single-column read; forcing manual semicolon split")
                df.columns = [str(c).strip() for c in df.columns]
                return self._cleanup_columns(df)
            except Exception:
                continue

        # Manuell fallback om allt ovan misslyckar
        # Läser som råtext och splittar rader på ';'
        rows: List[List[str]] = []
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                # Ta bort radslut och splitta på semikolon
                parts = [col.strip() for col in line.rstrip("\r\n").split(";")]
                rows.append(parts)

        if not rows:
            return pd.DataFrame()

        header = rows[0]
        data = rows[1:]
        # Rensa tomma headerfält (t.ex. sista ";;")
        header = [h.strip() for h in header]
        # Om dubbletter/tomma namn – ersätt med col_i
        fixed_header: List[str] = []
        used = set()
        for i, h in enumerate(header):
            name = h if h else f"col_{i}"
            if name in used or not name:
                name = f"{name}_{i}"
            used.add(name)
            fixed_header.append(name)

        # Pad/trunka rader till header-längd
        width = len(fixed_header)
        norm_data: List[List[str]] = []
        for row in data:
            if len(row) < width:
                row = row + [""] * (width - len(row))
            elif len(row) > width:
                row = row[:width]
            norm_data.append(row)

        df = pd.DataFrame(norm_data, columns=fixed_header)
        return self._cleanup_columns(df)

    # ---- Kolumnstädning och normalisering -----------------------------------
    def _cleanup_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        # Ta bort helt tomma kolumner och trimmar text
        for c in df.columns:
            df[c] = df[c].astype(str).str.strip()

        # Släng kolumner som är helt tomma
        empty_cols = [c for c in df.columns if (df[c] == "").all()]
        if empty_cols:
            df = df.drop(columns=empty_cols)

        # Normalisera några vanliga svenska kolumnnamn
        # Vi accepterar både exakta och "nästan"-namn (med olika case/blanktecken)
        def _lc(s: str) -> str:
            return str(s or "").strip().lower()

        rename_map = {}
        cols_lc = {_lc(c): c for c in df.columns}

        # Kandidatnycklar vi vill ha
        want = {
            "artikelnummer": ["artikelnummer", "artnr", "art.nr", "art nr", "artnummer"],
            "benämning": ["benämning", "benamning", "namn", "ben.", "produktbenämning"],
            "enhet": ["enhet", "st", "m", "kg"],
            "pris": ["pris", "gn-pris", "gnpris", "gn_pris", "nettopris", "à-pris", "à pris"],
        }

        for target, aliases in want.items():
            for alias in aliases:
                if alias in cols_lc:
                    rename_map[cols_lc[alias]] = target.capitalize() if target != "pris" else "Pris"
                    break  # första träff vinner

        if rename_map:
            df = df.rename(columns=rename_map)

        return df

    # ---- Publika API:n -------------------------------------------------------
    def load(self) -> None:
        self.files = self._resolve_paths()
        frames = [self._read_one_csv(p) for p in self.files]
        frames = [f for f in frames if f is not None and not f.empty]
        if not frames:
            raise FileNotFoundError(f"Inga läsbara prislistor i: {self.config.csv_path}")
        # Konkateniera om flera filer
        self.df = pd.concat(frames, ignore_index=True)

    def search(self, term: str, top_k: int = 10) -> pd.DataFrame:
        if self.df is None:
            raise RuntimeError("Prislista ej laddad. Kör load() först.")
        t = (term or "").strip().lower()
        if not t:
            return self.df.head(top_k)

        # 1) Primär sökning: Benämning + Artikelnummer om de finns
        mask_parts = []
        if "Benämning" in self.df.columns:
            mask_parts.append(self.df["Benämning"].fillna("").str.lower().str.contains(t, regex=False))
        if "Artikelnummer" in self.df.columns:
            mask_parts.append(self.df["Artikelnummer"].fillna("").astype(str).str.lower().str.contains(t, regex=False))

        if mask_parts:
            mask = mask_parts[0]
            for m in mask_parts[1:]:
                mask |= m
            hits = self.df[mask].copy()
        else:
            hits = self.df.head(0).copy()

        # 2) Fallback: sök över alla strängkolumner om inga träffar
        if hits.empty:
            str_cols = [c for c in self.df.columns if self.df[c].dtype == object]
            if str_cols:
                mask_any = self.df[str_cols].apply(
                    lambda s: s.fillna("").astype(str).str.lower().str.contains(t, regex=False)
                ).any(axis=1)
                hits = self.df[mask_any].copy()

        # Sortering (om möjliga fält finns)
        sort_cols = [c for c in ["Benämning", "Pris"] if c in hits.columns]
        if sort_cols:
            hits.sort_values(sort_cols, inplace=True, na_position="last")

        return hits.head(top_k)
