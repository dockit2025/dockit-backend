from fastapi import APIRouter, Query, HTTPException
import json
from pathlib import Path

router = APIRouter()

CATALOG_PATH = Path("knowledge/catalogs/price_catalog.json")

@router.get("/articles/autocomplete")
def autocomplete_articles(query: str = Query(..., min_length=2, max_length=20)):
    """
    Returnerar max 10 artiklar vars artikelnummer börjar med query-strängen.
    """
    if not CATALOG_PATH.exists():
        raise HTTPException(status_code=500, detail="price_catalog.json saknas")

    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    q = query.strip()

    matches = []
    for item in catalog:
        art = str(item.get("artikelnummer") or "").strip()
        if art.startswith(q):
            matches.append({
                "article_number": art,
                "name": item.get("benamning") or item.get("name") or "",
                "unit": item.get("enhet") or "st",
                "price": item.get("gn_pris") or 0
            })

    return matches[:10]
