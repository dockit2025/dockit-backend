from functools import lru_cache
from pathlib import Path
import json
import sys
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Depends

from src.server.api.quotes import verify_api_key  # återanvänd samma API-nyckelkontroll
from src.services.pricing import PRICE_CATALOG_DIR, PRICE_CATALOG_PRIMARY, PRICE_CATALOG_AHLSELL

router = APIRouter(
    prefix="/articles",
    tags=["articles"],
    dependencies=[Depends(verify_api_key)],
)


@lru_cache(maxsize=1)
def _load_detailed_price_catalog() -> Dict[str, Dict[str, Any]]:
    """
    Läser in prislistorna och returnerar:
      { artikelnummer: hela_raden_som_dict }

    Prioritet:
      1) Ahlsell-kontraktsprislista
      2) Primär GN-prislista (Storel)
      3) Övriga price_catalog_*.json
    """
    if not PRICE_CATALOG_DIR.exists():
        print(
            f"[articles] Hittar inte katalog med prislistor på {PRICE_CATALOG_DIR}",
            file=sys.stderr,
        )
        return {}

    def _load_single_catalog(path: Path) -> Dict[str, Dict[str, Any]]:
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f) or []
        except Exception as e:
            print(f"[articles] Kunde inte läsa prislista {path}: {e}", file=sys.stderr)
            return {}

        result: Dict[str, Dict[str, Any]] = {}
        if not isinstance(data, list):
            print(
                f"[articles] Prislista {path} förväntas vara en lista med rader",
                file=sys.stderr,
            )
            return result

        for row in data:
            if not isinstance(row, dict):
                continue

            art_nr = str(row.get("artikelnummer") or "").strip()
            if not art_nr:
                continue

            # Spara hela raden – vi kan plocka namn/enhet/pris senare
            result[art_nr] = row

        return result

    merged: Dict[str, Dict[str, Any]] = {}

    # 1) Ahlsell – högst prioritet
    if PRICE_CATALOG_AHLSELL.exists():
        ahlsell = _load_single_catalog(PRICE_CATALOG_AHLSELL)
        merged.update(ahlsell)
    else:
        print(
            f"[articles] Hittar inte Ahlsell-prislista på {PRICE_CATALOG_AHLSELL}",
            file=sys.stderr,
        )

    # 2) Primär GN-prislista (Storel) – fyller på saknade artiklar
    if PRICE_CATALOG_PRIMARY.exists():
        base = _load_single_catalog(PRICE_CATALOG_PRIMARY)
        for art_nr, row in base.items():
            if art_nr not in merged:
                merged[art_nr] = row
    else:
        print(
            f"[articles] Hittar inte primär prislista price_catalog.json på "
            f"{PRICE_CATALOG_PRIMARY}",
            file=sys.stderr,
        )

    # 3) Övriga prislistor (price_catalog_*.json)
    for extra_path in PRICE_CATALOG_DIR.glob("price_catalog_*.json"):
        if extra_path.resolve() in {
            PRICE_CATALOG_PRIMARY.resolve(),
            PRICE_CATALOG_AHLSELL.resolve(),
        }:
            continue

        extra = _load_single_catalog(extra_path)
        for art_nr, row in extra.items():
            if art_nr not in merged:
                merged[art_nr] = row

    return merged


def _extract_name(row: Dict[str, Any]) -> Optional[str]:
    """
    Försöker hitta ett vettigt namn i raden.
    Fält kan heta t.ex. 'benamning', 'benämning', 'namn', 'name'.
    """
    for key in ["benamning", "benämning", "namn", "name", "Benämning"]:
        if key in row and row[key]:
            return str(row[key])
    return None


def _extract_unit(row: Dict[str, Any]) -> Optional[str]:
    """
    Försöker hitta enhet i raden.
    """
    for key in ["enhet", "Enhet", "unit"]:
        if key in row and row[key]:
            return str(row[key])
    return None


def _extract_price(row: Dict[str, Any]) -> Optional[float]:
    """
    Försöker plocka gn_pris som float.
    """
    for key in ["gn_pris", "GN-pris", "gnpris"]:
        if key in row and row[key] is not None:
            try:
                return float(row[key])
            except (TypeError, ValueError):
                return None
    return None


@router.get(
    "/search",
    summary="Sök artikel på artikelnummer",
)
def search_article(
    article_ref: str = Query(..., description="Artikelnummer att slå upp, t.ex. 1234567"),
):
    """
    Enkel artikelsök på artikelnummer.

    Returnerar:
      - found: bool
      - article_ref: artikelnumret
      - name: benämning om den finns
      - unit: enhet om den finns
      - price: gn_pris om den finns
    """
    article_ref = (article_ref or "").strip()
    if not article_ref:
        raise HTTPException(status_code=400, detail="article_ref måste anges")

    catalog = _load_detailed_price_catalog()
    row = catalog.get(article_ref)

    if not row:
        return {
            "found": False,
            "article_ref": article_ref,
        }

    name = _extract_name(row)
    unit = _extract_unit(row)
    price = _extract_price(row)

    return {
        "found": True,
        "article_ref": article_ref,
        "name": name,
        "unit": unit,
        "price": price,
    }
