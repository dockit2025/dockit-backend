# file: src/server/services/dockit_task_mapper.py
"""
Dockit task mapping:

- Läser knowledge/dockit/dockit_custom_mapping.yaml
- Matchar fri text mot task.patterns
- (valfritt) använder ATLLoader och PriceListLoader för att ta fram kandidater

Användning (exempel):

    from src.server.loaders.atl_loader_new import ATLLoader, ATLConfig
    from src.server.loaders.pricelist_loader import PriceListLoader, PriceListConfig
    from src.server.services.dockit_task_mapper import (
        load_dockit_custom_mapping,
        match_tasks_from_text,
    )

    atl_loader = ATLLoader(ATLConfig())
    atl_loader.load()

    pricelist_loader = PriceListLoader(PriceListConfig())
    pricelist_loader.load()

    mapping = load_dockit_custom_mapping()
    tasks = match_tasks_from_text(
        "Montera två taklampor och installera laddbox",
        mapping,
        atl_loader=atl_loader,
        pricelist_loader=pricelist_loader,
    )

Funktionen returnerar en lista av MatchedTask-objekt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Union
from pathlib import Path

import yaml

# Importera befintliga loaders
from src.server.loaders.atl_loader_new import ATLLoader  # type: ignore
from src.server.loaders.pricelist_loader import PriceListLoader  # type: ignore


# Standardpath till YAML-mappingen
DEFAULT_MAPPING_PATH = (
    Path(__file__).resolve().parents[3] / "knowledge" / "dockit" / "dockit_custom_mapping.yaml"
)


@dataclass
class MatchedTask:
    """
    Resultat från matchning av fri text mot dockit_custom_mapping.yaml.
    """

    task_id: str
    label: str
    category: Optional[str]

    matched_patterns: List[str] = field(default_factory=list)

    time_source: str = "manual"  # "atl" eller "manual"
    manual_time_minutes_per_unit: Optional[float] = None

    # Rå ATL-träffar (precis som ATLLoader.search returnerar)
    atl_candidates: List[Dict[str, Any]] = field(default_factory=list)

    pricing_source: str = "manual"  # "manual" eller "pricelist"
    material_suggestions: List[str] = field(default_factory=list)

    # Prislisteträffar (förenklat dict-format)
    pricelist_candidates: List[Dict[str, Any]] = field(default_factory=list)

    # Hela task-configen för eventuell vidare användning
    raw_config: Dict[str, Any] = field(default_factory=dict)


def load_dockit_custom_mapping(mapping_path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """
    Läser dockit_custom_mapping.yaml och returnerar hela configen som dict.

    mapping_path:
        - Om None: används DEFAULT_MAPPING_PATH (knowledge/dockit/dockit_custom_mapping.yaml)
    """
    path = Path(mapping_path) if mapping_path is not None else DEFAULT_MAPPING_PATH

    if not path.exists():
        raise FileNotFoundError(f"Dockit custom mapping saknas: {path}")

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if not isinstance(data, dict):
        raise ValueError(f"Felaktig YAML-struktur i {path}: rotobjektet måste vara en dict")

    tasks = data.get("tasks")
    if not isinstance(tasks, dict):
        raise ValueError(f"Felaktig YAML-struktur i {path}: 'tasks' måste vara en dict")

    return data


def _normalize_text(text: str) -> str:
    return text.lower()


def _tokenize(text: str) -> List[str]:
    """
    Enkel tokenisering: dela på whitespace och skiljetecken.
    Räcker för vår pattern-logik just nu.
    """
    import re

    # ersätt allt som inte är bokstav/siffra/åäöÅÄÖ med mellanslag
    cleaned = re.sub(r"[^0-9a-zA-ZåäöÅÄÖ]+", " ", text)
    tokens = [t for t in cleaned.lower().split() if t]
    return tokens


def _find_matched_patterns(text: str, patterns: Iterable[str]) -> List[str]:
    """
    Matchar patterns mot text (case-insensitive) på två sätt:

    1) Direkt substring-match:
       - om pattern.lower() finns som substring i text.lower() → träff

    2) Token-baserad "alla ord måste finnas med"-match:
       - pattern delas upp i ord (t.ex. "byta vägguttag" -> ["byta", "vägguttag"])
       - om alla dessa ord finns bland textens tokens, i valfri ordning
         (t.ex. "byta två vägguttag i vardagsrum") → träff.

    Detta gör att vi fångar fraser som:
        pattern: "byta vägguttag"
        text:    "Byta två vägguttag i vardagsrum"
    """
    if not text:
        return []

    norm_text = _normalize_text(text)
    text_tokens = set(_tokenize(norm_text))

    matched: List[str] = []

    for p in patterns:
        p = p or ""
        p_norm = p.lower().strip()
        if not p_norm:
            continue

        # 1) direkt substring
        if p_norm in norm_text:
            matched.append(p)
            continue

        # 2) tokenbaserad: alla pattern-ord måste finnas i texten
        pat_tokens = _tokenize(p_norm)
        if pat_tokens and all(tok in text_tokens for tok in pat_tokens):
            matched.append(p)

    return matched


def _resolve_atl_candidates_for_task(
    task_config: Dict[str, Any],
    atl_loader: Optional[ATLLoader],
    max_atl_results: int,
) -> List[Dict[str, Any]]:
    """
    Använder atl_refs i task_config för att hämta ATL-kandidater via ATLLoader.

    Förväntad struktur i task_config:
        atl_refs:
          - mapping_key: "..."
            # eller: search_text: "..."
            # variant: 0
            # top_k: 5
    """
    if atl_loader is None:
        return []

    atl_refs = task_config.get("atl_refs") or []
    if not isinstance(atl_refs, list):
        return []

    candidates: List[Dict[str, Any]] = []

    for ref in atl_refs:
        if not isinstance(ref, dict):
            continue

        search_term = ref.get("mapping_key") or ref.get("search_text")
        if not search_term:
            continue

        top_k = ref.get("top_k") or max_atl_results
        try:
            hits = atl_loader.search(str(search_term), top_k=top_k)
        except Exception:
            hits = []

        variant_filter = ref.get("variant")
        if variant_filter is not None:
            v_str = str(variant_filter)
            hits = [h for h in hits if str(h.get("variant")) == v_str]

        candidates.extend(hits)

    return candidates


def _resolve_pricelist_candidates_for_task(
    task_config: Dict[str, Any],
    pricelist_loader: Optional[PriceListLoader],
    max_pricelist_results: int,
) -> List[Dict[str, Any]]:
    """
    Använder material_suggestions som söktermer mot PriceListLoader.search().

    Returnerar en platt lista med dictar:
        {
          "Artikelnummer": ...,
          "Benämning": ...,
          "Enhet": ...,
          "Materialgrupp": ...,
          "Pris": ...,
        }
    """
    if pricelist_loader is None:
        return []

    pricing_source = task_config.get("pricing_source") or "manual"
    if pricing_source != "pricelist":
        return []

    material_suggestions = task_config.get("material_suggestions") or []
    if not isinstance(material_suggestions, list):
        return []

    candidates: List[Dict[str, Any]] = []

    for term in material_suggestions:
        if not term:
            continue

        try:
            df = pricelist_loader.search(str(term), top_k=max_pricelist_results)
        except Exception:
            df = None

        if df is None or getattr(df, "empty", True):
            continue

        for _, row in df.iterrows():
            candidates.append(
                {
                    "Artikelnummer": str(row.get("Artikelnummer", "")).strip(),
                    "Benämning": str(row.get("Benämning", "")).strip(),
                    "Enhet": str(row.get("Enhet", "")).strip(),
                    "Materialgrupp": str(row.get("Materialgrupp", "")).strip(),
                    "Pris": _to_float_or_none(row.get("Pris")),
                }
            )

    return candidates


def _to_float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        text = str(value).strip().replace(",", ".")
        if not text:
            return None
        return float(text)
    except Exception:
        return None


def match_tasks_from_text(
    text: str,
    mapping: Dict[str, Any],
    atl_loader: Optional[ATLLoader] = None,
    pricelist_loader: Optional[PriceListLoader] = None,
    max_atl_results: int = 5,
    max_pricelist_results: int = 3,
) -> List[MatchedTask]:
    """
    Matchar fri text mot tasks i dockit_custom_mapping.yaml.

    Parametrar:
        text:
            Sammanfattning eller beskrivning av jobbet (svenska).
        mapping:
            Dict returnerad av load_dockit_custom_mapping().
        atl_loader:
            ATLLoader-instans (med .load() anropat) eller None.
        pricelist_loader:
            PriceListLoader-instans (med .load() anropat) eller None.
        max_atl_results:
            Standard topp-K vid ATL-sökningar (kan överskridas av atl_refs[i].top_k).
        max_pricelist_results:
            Topp-K för varje material_suggestion i prislistan.

    Returnerar:
        List[MatchedTask]
    """
    if not text:
        return []

    tasks_cfg = mapping.get("tasks") or {}
    if not isinstance(tasks_cfg, dict):
        return []

    results: List[MatchedTask] = []
    norm_text = _normalize_text(text)

    for task_id, cfg in tasks_cfg.items():
        if not isinstance(cfg, dict):
            continue

        patterns = cfg.get("patterns") or []
        matched_patterns = _find_matched_patterns(norm_text, patterns)
        if not matched_patterns:
            continue

        time_source = cfg.get("time_source") or "manual"
        pricing_source = cfg.get("pricing_source") or "manual"

        manual_time = cfg.get("manual_time_minutes_per_unit")
        if manual_time is not None:
            try:
                manual_time = float(manual_time)
            except Exception:
                manual_time = None

        mt = MatchedTask(
            task_id=str(task_id),
            label=str(cfg.get("label", task_id)),
            category=cfg.get("category"),
            matched_patterns=matched_patterns,
            time_source=time_source,
            manual_time_minutes_per_unit=manual_time,
            pricing_source=pricing_source,
            material_suggestions=list(cfg.get("material_suggestions") or []),
            raw_config=cfg,
        )

        # ATL-kandidater om time_source == "atl"
        if time_source == "atl":
            mt.atl_candidates = _resolve_atl_candidates_for_task(
                cfg,
                atl_loader=atl_loader,
                max_atl_results=max_atl_results,
            )

        # Prislisteträffar om pricing_source == "pricelist"
        mt.pricelist_candidates = _resolve_pricelist_candidates_for_task(
            cfg,
            pricelist_loader=pricelist_loader,
            max_pricelist_results=max_pricelist_results,
        )

        results.append(mt)

    return results


def extract_tasks_from_text(
    text: str,
    mapping_path: Optional[Union[str, Path]] = None,
    atl_loader: Optional[ATLLoader] = None,
    pricelist_loader: Optional[PriceListLoader] = None,
    max_atl_results: int = 5,
    max_pricelist_results: int = 3,
) -> List[MatchedTask]:
    """
    Convenience-funktion som själv laddar YAML innan matchning.
    """
    mapping = load_dockit_custom_mapping(mapping_path)
    return match_tasks_from_text(
        text=text,
        mapping=mapping,
        atl_loader=atl_loader,
        pricelist_loader=pricelist_loader,
        max_atl_results=max_atl_results,
        max_pricelist_results=max_pricelist_results,
    )


if __name__ == "__main__":
    # Enkel CLI för manuell testning utan ATL/prislista
    import sys
    from pprint import pprint

    if len(sys.argv) < 2:
        print("Användning: python -m src.server.services.dockit_task_mapper \"beskrivning av jobb\"")
        sys.exit(1)

    job_text = sys.argv[1]
    mapping = load_dockit_custom_mapping()
    tasks = match_tasks_from_text(job_text, mapping)

    print(f"Text: {job_text}")
    print(f"Antal matchade tasks: {len(tasks)}")
    for t in tasks:
        print("-" * 40)
        pprint(t)
