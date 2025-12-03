from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

# Återanvänd API-nyckelkontrollen från quotes.py
from src.server.api.quotes import verify_api_key

CATALOG_DIR = Path("knowledge") / "catalogs"
PRIMARY_CATALOG = CATALOG_DIR / "price_catalog.json"

router = APIRouter(
    prefix="/articles",
    tags=["articles"],
)


class ArticleSuggestion(BaseModel):
    article_number: str
    name: str
    unit: Optional[str] = None
    price: Optional[float] = None


def _stderr(msg: str) -> None:
    print(f"[articles_autocomplete] {msg}", file=sys.stderr)


def _load_single_catalog(path: Path) -> List[Dict[str, Any]]:
    """
    Läser EN normaliserad prislista (t.ex. price_catalog.json eller price_catalog_ahlsell.json).

    Förväntat format (lista av rader):
    [
      {
        "artikelnummer": "0447001",
        "benamning": "EXQ 3G1,5 R50",
        "enhet": "M",
        "gn_pris": 7.25,
        ...
      },
      ...
    ]
    """
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f) or []
    except Exception as e:  # noqa: BLE001
        _stderr(f"Kunde inte läsa prislista {path}: {e}")
        return []

    if not isinstance(data, list):
        _stderr(f"Prislista {path} förväntas vara en lista med rader.")
        return []

    rows: List[Dict[str, Any]] = []
    for row in data:
        if not isinstance(row, dict):
            continue

        art_nr = str(row.get("artikelnummer") or "").strip()
        if not art_nr:
            continue

        benamning = str(row.get("benamning") or "").strip()
        enhet = str(row.get("enhet") or "").strip() or None
        price_raw = row.get("gn_pris")

        try:
            price_f = float(price_raw) if price_raw is not None else None
        except (TypeError, ValueError):
            price_f = None

        rows.append(
            {
                "artikelnummer": art_nr,
                "benamning": benamning,
                "enhet": enhet,
                "gn_pris": price_f,
            }
        )

    return rows


@lru_cache(maxsize=1)
def _load_merged_catalog() -> Dict[str, Dict[str, Any]]:
    """
    Läser och mergar alla prislistor i knowledge/catalogs:

      - price_catalog.json (primär, t.ex. Storel)
      - alla filer som matchar price_catalog_*.json (t.ex. Ahlsell)

    Returnerar:
      { artikelnummer: { "artikelnummer": ..., "benamning": ..., "enhet": ..., "gn_pris": ... } }
    """
    if not CATALOG_DIR.exists():
        _stderr(f"Hittar inte katalog med prislistor: {CATALOG_DIR}")
        return {}

    merged: Dict[str, Dict[str, Any]] = {}

    # 1) Primära prislistan (om den finns) – får företräde
    if PRIMARY_CATALOG.exists():
        base_rows = _load_single_catalog(PRIMARY_CATALOG)
        for row in base_rows:
            art = row["artikelnummer"]
            merged[art] = row
    else:
        _stderr(f"Hittar inte primär prislista på {PRIMARY_CATALOG}")

    # 2) Övriga prislistor: price_catalog_*.json
    for extra_path in CATALOG_DIR.glob("price_catalog_*.json"):
        if extra_path.resolve() == PRIMARY_CATALOG.resolve():
            continue

        extra_rows = _load_single_catalog(extra_path)
        added = 0
        for row in extra_rows:
            art = row["artikelnummer"]
            # Primär (Storel) vinner vid krock – skriv inte över befintligt
            if art not in merged:
                merged[art] = row
                added += 1

        _stderr(
            f"Läste extra prislista {extra_path.name}: {len(extra_rows)} rader, {added} nya artiklar."
        )

    _stderr(f"Mergad katalog innehåller totalt {len(merged)} artiklar.")
    return merged


def _search_articles(term: str, limit: int = 20) -> List[ArticleSuggestion]:
    """
    Enkel substring-sökning i artikelnummer + benämning (case-insensitive).
    """
    term_norm = term.strip().lower()
    if not term_norm:
        return []

    catalog = _load_merged_catalog()
    results: List[ArticleSuggestion] = []

    for row in catalog.values():
        art = row["artikelnummer"]
        name = row.get("benamning") or ""
        unit = row.get("enhet")
        price = row.get("gn_pris")

        if term_norm in art.lower() or term_norm in name.lower():
            results.append(
                ArticleSuggestion(
                    article_number=art,
                    name=name,
                    unit=unit,
                    price=price,
                )
            )
            if len(results) >= limit:
                break

    return results


@router.get(
    "/autocomplete",
    response_model=List[ArticleSuggestion],
    summary="Autocomplete för artiklar (Storel + Ahlsell)",
)
async def autocomplete_articles(
    request: Request,
    api_key: None = Depends(verify_api_key),
    q: Optional[str] = Query(
        default=None,
        description="Sökterm för artikel (frontend kan använda q eller query)",
    ),
    query: Optional[str] = Query(
        default=None,
        description="Alternativ sökterm; om satt används denna före q",
    ),
) -> List[ArticleSuggestion]:
    """
    Autocomplete-endpoint för artiklar.

    Sökväg:
      GET /articles/autocomplete?q=lampsladd
      GET /articles/autocomplete?query=lampsladd

    Returnerar en lista med artikelförslag (artikelnummer, benämning, enhet, pris).
    """
    # Tillåt både ?q= och ?query= – om båda anges vinner 'query'
    search_term = (query or q or "").strip()
    if len(search_term) < 2:
        # För kort term → returnera tom lista istället för fel
        return []

    try:
        results = _search_articles(search_term, limit=20)
    except Exception as e:  # noqa: BLE001
        _stderr(f"Fel vid artikelsökning för '{search_term}': {e}")
        raise HTTPException(status_code=500, detail="Fel vid artikelsökning") from e

    return results
