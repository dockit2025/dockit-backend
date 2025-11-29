from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set, Tuple

import pandas as pd
import yaml


# ------------------------------------------------------------
# Konfiguration
# ------------------------------------------------------------
@dataclass
class ATLConfig:
    # CSV med ATL-data
    atl_csv_path: str = "knowledge/atl/Del7_ATL_Total.csv"
    # YAML med synonymer/mappning (kan ligga som dict, lista, eller schema med "mappings")
    atl_mapping_path: str = "knowledge/atl/atl_mapping.yaml"


# ------------------------------------------------------------
# Hjälp: normalisering
# ------------------------------------------------------------
def _normalize_text(s: str) -> str:
    if s is None:
        return ""
    s = str(s).lower()
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\u00a0", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _concat_string_columns(df: pd.DataFrame, cols: Optional[Iterable[str]] = None) -> pd.Series:
    if cols is None:
        cols = df.columns
    return df[list(cols)].astype(str).agg(" ".join, axis=1)


# ------------------------------------------------------------
# Loader
# ------------------------------------------------------------
class ATLLoader:
    """
    Läser ATL-CSV robust (hanterar ; eller , som separator) och bygger ett
    sökindex över all text. Läser även en flexibel YAML-mappning
    (synonymer/fraser) som kan vara dict, lista eller schema med 'mappings'.
    """

    def __init__(self, config: Optional[ATLConfig] = None) -> None:
        self.config = config or ATLConfig()
        self.df: Optional[pd.DataFrame] = None

        # mapping_terms: { "fras": ["syn1", "syn2", "målsträng ur 'search'", ...] }
        self.mapping_terms: Dict[str, List[str]] = {}
        # optionellt metadata per fras (t.ex. default_variant, unit_hint)
        self.mapping_meta: Dict[str, Dict[str, Optional[str]]] = {}

        self._csv_sep = ","

    def load(self) -> None:
        self._load_csv()
        self._load_mapping()
        # Bas-synonymer att alltid ha med
        self._ensure_fallback_synonyms(["uttag", "armatur", "downlight"])
        self._build_index()

    # --------------------------------------------------------
    # CSV
    # --------------------------------------------------------
    def _load_csv(self) -> None:
        """
        Läs ATL CSV robust: prova ; först (vanligt när decimal=,),
        falla tillbaka till , om ; misslyckas. Läs allt som str.
        """
        from pathlib import Path

        path = Path(self.config.atl_csv_path)
        if not path.exists():
            raise FileNotFoundError(f"Hittar inte ATL CSV: {path}")

        last_err = None
        for sep in (";", ","):
            try:
                df = pd.read_csv(
                    path,
                    encoding="utf-8-sig",
                    sep=sep,
                    dtype=str,          # läs allt som text (säkrast)
                    engine="python",    # tolerant parser
                )
                # Trimma kolumnnamn
                df.columns = [str(c).strip() for c in df.columns]
                self.df = df
                self._csv_sep = sep
                return
            except Exception as e:
                last_err = e
                continue

        raise RuntimeError(f"Kunde inte läsa ATL CSV med ; eller ,  ({last_err})")

    # --------------------------------------------------------
    # MAPPNING (YAML)
    # --------------------------------------------------------
    def _load_mapping(self) -> None:
        """
        Stöd för tre format:

        1) Dict:
            uttag:
              - vägguttag
              - apparatuttag

        2) Lista:
            - phrase: "uttag"
              synonyms: ["vägguttag","apparatuttag"]
              search: "Vägguttag snabbkoppling"
              default_variant: 0
              unit_hint: "st"

        3) Schema med rot-nyckeln "mappings":
            mappings:
              - phrases: ["vägguttag", "apparatuttag"]
                search:  "Vägguttag snabbkoppling"
                default_variant: 0
                unit_hint: "st"
        """
        path = self.config.atl_mapping_path
        if not os.path.exists(path):
            self.mapping_terms = {}
            self.mapping_meta = {}
            return

        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        terms: Dict[str, List[str]] = {}
        meta: Dict[str, Dict[str, Optional[str]]] = {}

        def _add_phrase_entry(phrase: str, syns: List[str], search_target: Optional[str],
                              default_variant: Optional[str], unit_hint: Optional[str]) -> None:
            p = (phrase or "").strip().lower()
            if not p:
                return
            vals: List[str] = []
            # synonymer
            vals.extend([str(x).strip().lower() for x in (syns or []) if x])
            # lägg även in söksträngen (mål i CSV) som en term att OR-söka på
            if search_target:
                vals.append(str(search_target).strip().lower())
            # undvik dubbletter + inkludera sig själv
            coll = list({p, *vals})
            terms[p] = coll
            meta[p] = {
                "search": (search_target or None),
                "default_variant": (str(default_variant) if default_variant is not None else None),
                "unit_hint": (unit_hint or None),
            }

        if isinstance(raw, dict) and "mappings" in raw and isinstance(raw["mappings"], list):
            # (3) Rot-nyckeln 'mappings'
            for item in raw["mappings"]:
                if not isinstance(item, dict):
                    continue
                phrases = item.get("phrases")
                if isinstance(phrases, str):
                    phrases = [phrases]
                if not phrases or not isinstance(phrases, list):
                    continue
                search_target = item.get("search")
                default_variant = item.get("default_variant")
                unit_hint = item.get("unit_hint")
                extra_syns = item.get("synonyms") or item.get("alias") or item.get("aliases") or []
                if isinstance(extra_syns, str):
                    extra_syns = [extra_syns]
                for ph in phrases:
                    _add_phrase_entry(ph, extra_syns, search_target, default_variant, unit_hint)

        elif isinstance(raw, dict):
            # (1) Enkel dict fras->synonymlista
            for k, v in raw.items():
                if k == "mappings":
                    # om någon lagt fel format, hoppa över – hanterat ovan
                    continue
                key = str(k).strip().lower()
                syns: List[str] = []
                if isinstance(v, list):
                    syns = [str(x).strip().lower() for x in v if x]
                elif isinstance(v, str):
                    syns = [v.strip().lower()]
                _add_phrase_entry(key, syns, None, None, None)

        elif isinstance(raw, list):
            # (2) Lista av dict-poster
            for item in raw:
                if not isinstance(item, dict):
                    continue
                phrase = (
                    str(item.get("phrase") or item.get("key") or item.get("name") or "")
                    .strip()
                    .lower()
                )
                if not phrase:
                    continue
                syns = item.get("synonyms") or item.get("alias") or item.get("aliases") or []
                if isinstance(syns, str):
                    syns = [syns]
                search_target = item.get("search")
                default_variant = item.get("default_variant")
                unit_hint = item.get("unit_hint")
                _add_phrase_entry(phrase, syns, search_target, default_variant, unit_hint)

        # spara
        self.mapping_terms = terms
        self.mapping_meta = meta

    def _ensure_fallback_synonyms(self, required_keys: Iterable[str]) -> None:
        """
        Se till att vissa nycklar alltid finns,
        åtminstone med sig själva som term att söka på.
        """
        if not isinstance(self.mapping_terms, dict):
            self.mapping_terms = {}
        for key in required_keys:
            k = str(key).strip().lower()
            if k not in self.mapping_terms:
                self.mapping_terms[k] = [k]
            elif not self.mapping_terms[k]:
                self.mapping_terms[k] = [k]

    # --------------------------------------------------------
    # INDEX
    # --------------------------------------------------------
    def _build_index(self) -> None:
        if self.df is None:
            raise RuntimeError("ATL CSV är inte laddad.")
        # Skapa en stor söksträng av alla kolumner
        self.df["_search_text"] = _concat_string_columns(self.df, self.df.columns).map(_normalize_text)

    # --------------------------------------------------------
    # SÖK
    # --------------------------------------------------------
    def _expand_query(self, query: str, extra_terms: Optional[Iterable[str]]) -> Set[str]:
        """
        Bygger upp en termmängd av query + ev. extra + synonymer + ev. 'search'-mål.
        Om query matchar en fras i mappningen adderas även dess 'search'-sträng.
        """
        q = str(query or "").strip().lower()
        terms: Set[str] = set()
        if q:
            terms.add(q)
        if extra_terms:
            terms.update([str(t).strip().lower() for t in extra_terms if t])

        # slå upp i mappning
        for key, syns in (self.mapping_terms or {}).items():
            syns_set = set([key, *(syns or [])])
            if q and (q == key or q in syns_set):
                terms.update(syns_set)

        return terms or ({q} if q else set())

    def _terms_to_regex(self, terms: Set[str]) -> str:
        """
        Bygg enkel OR-regex av termerna.
        """
        escaped = [re.escape(t) for t in terms if t]
        return "|".join(escaped) if escaped else ""

    def _parse_variant_times(self, row: pd.Series) -> List[Tuple[str, Optional[float]]]:
        """
        Hämta variantkolumner (0, -1, -2, ...) och konvertera till float timmar.
        Returnerar lista [(variant, time_h_per_unit), ...] där None betyder tomt.
        """
        variant_cols = [c for c in row.index if re.fullmatch(r"-?\d+", str(c))]
        out: List[Tuple[str, Optional[float]]] = []
        for vc in variant_cols:
            raw = str(row.get(vc, "") or "").strip()
            if not raw:
                out.append((str(vc), None))
                continue
            raw = raw.replace(",", ".")
            try:
                out.append((str(vc), float(raw)))
            except ValueError:
                out.append((str(vc), None))
        return out

    def _row_to_records(self, row: pd.Series) -> List[Dict[str, Optional[str]]]:
        """
        Gör om en rad till en eller flera records – en per variantkolumn.
        Standardiserade nycklar:
            - moment_name, group, row, arbetsmoment, variant, variant_text, unit, time_h_per_unit
        """
        moment_name = str(row.get("Moment/Typ/Sort", "") or "").strip()
        variant_text = str(row.get("Underlag/Variant", "") or "").strip()
        unit = str(row.get("Enhet", "") or "").strip()
        group = str(row.get("Grupp", "") or "").strip()
        rrow = str(row.get("Rad", "") or "").strip()
        arbetsmoment = str(row.get("Arbetsmoment", "") or "").strip()

        variants = self._parse_variant_times(row)
        recs: List[Dict[str, Optional[str]]] = []
        for var, time_val in variants:
            recs.append(
                {
                    "moment_name": moment_name or None,
                    "group": group or None,
                    "row": rrow or None,
                    "arbetsmoment": arbetsmoment or None,
                    "variant": var,
                    "variant_text": variant_text or None,
                    "unit": unit or None,
                    "time_h_per_unit": time_val,
                }
            )
        return recs

    def search(
        self,
        query: str,
        extra_terms: Optional[Iterable[str]] = None,
        top_k: int = 10
    ) -> List[Dict[str, Optional[str]]]:
        """
        Textsökning med synonymer och mapping. Returnerar upp till top_k rader
        (expanderade per variant).
        """
        if self.df is None:
            raise RuntimeError("ATL-data inte laddad. Kör load() först.")

        terms = self._expand_query(query, extra_terms)
        regex = self._terms_to_regex(terms)
        if not regex:
            return []

        mask = self.df["_search_text"].str.contains(regex, regex=True, na=False)
        base = self.df[mask].head(top_k)  # begränsa antal rader först
        out: List[Dict[str, Optional[str]]] = []
        for _, r in base.iterrows():
            out.extend(self._row_to_records(r))
        return out


# ------------------------------------------------------------
# Snabbfunktion (valfri)
# ------------------------------------------------------------
def search_atl(query: str, top_k: int = 5) -> List[Dict[str, Optional[str]]]:
    loader = ATLLoader()
    loader.load()
    return loader.search(query, top_k=top_k)
