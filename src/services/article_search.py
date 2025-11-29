# fil: src/services/article_search.py

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

# Projektrot, t.ex. D:\dockit-ai
ROOT = Path(__file__).resolve().parents[2]
PRICE_CATALOG_PATH = ROOT / "knowledge" / "catalogs" / "price_catalog.json"


@lru_cache(maxsize=1)
def _load_price_catalog() -> List[Dict[str, Any]]:
    """
    Läser in hela price_catalog.json EN gång och cache:ar det i minnet.

    Förväntad struktur per rad:
    {
      "artikelnummer": "0000110",
      "benamning": "EKKJ 3X2,5/2,5",
      "enhet": "M",
      "materialgrupp": "00DEC",
      "gn_pris": 55.0,
      ...
    }
    """
    if not PRICE_CATALOG_PATH.exists():
        raise FileNotFoundError(f"Hittar inte price_catalog.json på {PRICE_CATALOG_PATH}")

    with PRICE_CATALOG_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f) or []

    if not isinstance(data, list):
        raise ValueError("price_catalog.json förväntas vara en lista med rader")

    cleaned: List[Dict[str, Any]] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        cleaned.append(row)

    return cleaned


def _compute_match_score(query: str, benamning: str) -> int:
    """
    Enkel poängsättning mellan söksträng och benämning.

    - +3 poäng om hela query finns som substring
    - +2 poäng per query-ord som hittas i benämningen
    - +1 extra om ordet finns i början av benämningen
    """
    q = (query or "").strip().lower()
    b = (benamning or "").strip().lower()
    if not q or not b:
        return 0

    score = 0

    # Hela frasen
    if q in b:
        score += 3

    # Ord-för-ord
    words = [w for w in q.replace(",", " ").split() if w]
    for w in words:
        if w in b:
            score += 2
            if b.startswith(w):
                score += 1

    return score


def search_articles(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Sök i price_catalog.json efter artiklar vars benämning matchar query.

    Returnerar en lista med de bästa träffarna, sorterade efter score:
    [
      {
        "artikelnummer": "...",
        "benamning": "...",
        "gn_pris": 97.0,
        "enhet": "ST",
        "materialgrupp": "...",
        "score": 7,
      },
      ...
    ]
    """
    query = (query or "").strip()
    if not query:
        return []

    catalog = _load_price_catalog()
    results: List[Dict[str, Any]] = []

    for row in catalog:
        ben = str(row.get("benamning") or "")
        score = _compute_match_score(query, ben)
        if score <= 0:
            continue

        out_row = dict(row)
        out_row["score"] = score
        results.append(out_row)

    # Sortera bästa träffarna först
    results.sort(key=lambda r: (-r.get("score", 0), str(r.get("benamning") or "")))

    if limit and limit > 0:
        results = results[:limit]

    return results


if __name__ == "__main__":
    # Enkel manuell test från kommandoraden:
    import pprint

    print("Test: sök på 'dimmer'")
    hits = search_articles("dimmer", limit=20)
    pprint.pp(hits)
