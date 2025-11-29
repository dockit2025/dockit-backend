from __future__ import annotations

import json
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

from src.services.favorites import get_favorite_article

# Projektrot, t.ex. D:\dockit-ai
ROOT = Path(__file__).resolve().parents[2]

PRICE_CATALOG_DIR = ROOT / "knowledge" / "catalogs"
PRICE_CATALOG_PRIMARY = PRICE_CATALOG_DIR / "price_catalog.json"
MATERIAL_REF_MAP_PATH = ROOT / "knowledge" / "catalogs" / "material_ref_map.json"
CUSTOMERS_DIR = ROOT / "knowledge" / "customers"

LOG_DIR = ROOT / "knowledge" / "logs"
MISSING_PRICES_LOG = LOG_DIR / "missing_prices.jsonl"
MISSING_MATERIAL_MAP_LOG = LOG_DIR / "missing_material_mappings.jsonl"


def _ensure_log_dir() -> None:
    """
    Ser till att loggmappen finns.
    """
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:  # noqa: BLE001
        print(f"[pricing] Kunde inte skapa loggmapp {LOG_DIR}: {e}", file=sys.stderr)


def _append_json_line(path: Path, payload: Dict[str, Any]) -> None:
    """
    Skriver en rad JSON till en loggfil (JSON Lines-format).
    En rad per händelse → lättare att analysera i efterhand.
    """
    _ensure_log_dir()
    try:
        with path.open("a", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
            f.write("\n")
    except Exception as e:  # noqa: BLE001
        print(f"[pricing] Kunde inte skriva till logg {path}: {e}", file=sys.stderr)


def _log_missing_price(
    *,
    customer_id: Optional[str],
    article_ref: str,
    article_number: str,
) -> None:
    """
    Loggar att vi inte hittade något pris för en given ref/artikelnummer.
    """
    event = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "type": "missing_price",
        "customer_id": customer_id,
        "article_ref": article_ref,
        "article_number": article_number,
    }
    _append_json_line(MISSING_PRICES_LOG, event)


def _log_missing_material_mapping(
    *,
    material_ref: str,
) -> None:
    """
    Loggar att vi saknar en mapping för ett material_ref i material_ref_map.json
    (dvs vi tvingas anta att material_ref redan är ett artikelnummer).
    """
    event = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "type": "missing_material_mapping",
        "material_ref": material_ref,
    }
    _append_json_line(MISSING_MATERIAL_MAP_LOG, event)


@lru_cache(maxsize=1)
def _load_price_catalog() -> Dict[str, float]:
    """
    Läser in normaliserade prislistor från katalogen knowledge/catalogs
    och returnerar { artikelnummer: gn_pris }.

    - price_catalog.json används som primär bas (t.ex. Storel)
    - Alla filer som matchar price_catalog_*.json (t.ex. price_catalog_ahlsell.json)
      läses in och mergas in i samma dict.
    - Kundspecifika prislistor hanteras separat i _load_customer_price_list().
    """
    if not PRICE_CATALOG_DIR.exists():
        print(
            f"[pricing] Hittar inte katalog med prislistor på {PRICE_CATALOG_DIR}",
            file=sys.stderr,
        )
        return {}

    def _load_single_catalog(path: Path) -> Dict[str, float]:
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f) or []
        except Exception as e:  # noqa: BLE001
            print(f"[pricing] Kunde inte läsa prislista {path}: {e}", file=sys.stderr)
            return {}

        result: Dict[str, float] = {}
        if not isinstance(data, list):
            print(
                f"[pricing] Prislista {path} förväntas vara en lista med rader",
                file=sys.stderr,
            )
            return result

        for row in data:
            if not isinstance(row, dict):
                continue

            art_nr = str(row.get("artikelnummer") or "").strip()
            if not art_nr:
                continue

            price_raw = row.get("gn_pris")
            try:
                price_f = float(price_raw)
            except (TypeError, ValueError):
                continue

            result[art_nr] = price_f

        return result

    merged: Dict[str, float] = {}

    # 1) Primära prislistan (om den finns) – får "vinna" vid ev. krockar senare.
    if PRICE_CATALOG_PRIMARY.exists():
        base = _load_single_catalog(PRICE_CATALOG_PRIMARY)
        merged.update(base)
    else:
        print(
            f"[pricing] Hittar inte primär prislista price_catalog.json på {PRICE_CATALOG_PRIMARY}",
            file=sys.stderr,
        )

    # 2) Övriga prislistor som matchar price_catalog_*.json (t.ex. Ahlsell)
    for extra_path in PRICE_CATALOG_DIR.glob("price_catalog_*.json"):
        # Hoppa över primärfilen om den av någon anledning matchar mönstret
        if extra_path.resolve() == PRICE_CATALOG_PRIMARY.resolve():
            continue

        extra = _load_single_catalog(extra_path)

        # Merge-strategi: om artikel redan finns i merged låter vi befintligt värde ligga kvar.
        # Dvs primär prislista + ev. tidigare inlästa filer har företräde.
        added = 0
        for art_nr, price in extra.items():
            if art_nr not in merged:
                merged[art_nr] = price
                added += 1

        print(
            f"[pricing] Läste in extra prislista {extra_path.name} "
            f"({len(extra)} rader, {added} nya artiklar).",
            file=sys.stderr,
        )

    return merged


@lru_cache(maxsize=1)
def _load_material_ref_map() -> Dict[str, str]:
    """
    Läser mappingen Dockit-materialref -> artikelnummer, t.ex.

    {
      "DIMMER-UNIV": "1234567",
      "APPRAM-1FACK": "7654321"
    }
    """
    if not MATERIAL_REF_MAP_PATH.exists():
        return {}

    try:
        with MATERIAL_REF_MAP_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f) or {}
    except Exception as e:  # noqa: BLE001
        print(f"[pricing] Kunde inte läsa material_ref_map.json: {e}", file=sys.stderr)
        return {}

    mapping: Dict[str, str] = {}
    if isinstance(data, dict):
        for ref, art in data.items():
            if ref is None or art is None:
                continue
            mapping[str(ref)] = str(art).strip()

    return mapping


@lru_cache(maxsize=128)
def _load_customer_price_list(customer_id: Optional[str]) -> Dict[str, float]:
    """
    Läser kundspecifik prislista om den finns.

    Struktur:
      knowledge/customers/<customer_id>/price_list.json

    Exempel på innehåll i price_list.json:
    {
      "1234567": 89.50,
      "7654321": 74.25
    }

    Dvs: artikelnummer -> kundens nettopris (exkl. moms).
    """
    if not customer_id:
        return {}

    customer_dir = CUSTOMERS_DIR / str(customer_id)
    price_list_path = customer_dir / "price_list.json"

    if not price_list_path.exists():
        return {}

    try:
        with price_list_path.open("r", encoding="utf-8") as f:
            data = json.load(f) or {}
    except Exception as e:  # noqa: BLE001
        print(
            f"[pricing] Kunde inte läsa kundprislista för {customer_id}: {e}",
            file=sys.stderr,
        )
        return {}

    result: Dict[str, float] = {}
    if isinstance(data, dict):
        for art_nr, price in data.items():
            if art_nr is None or price is None:
                continue
            try:
                result[str(art_nr).strip()] = float(price)
            except (TypeError, ValueError):
                continue

    return result


def _resolve_article_number(
    customer_id: Optional[str],
    material_ref_or_article_ref: str,
) -> str:
    """
    Steg för att hitta vilket artikelnummer vi faktiskt ska slå upp pris för:

    1) Fråga favorites: get_favorite_article(customer_id, material_ref)
       - Om elektriker/kund har valt favoritartikel för just denna materialref
         (t.ex. DIMMER-UNIV), använd det artikelnumret direkt.

    2) Om ingen favorit: använd material_ref_map.json:
         material_ref_map[material_ref] -> artikelnummer

    3) Om fortfarande ingen träff: anta att material_ref_or_article_ref
       redan är ett artikelnummer och använd det rakt av.
       Om värdet inte ser ut som ett rent artikelnummer (bara siffror),
       loggar vi att vi saknar en mapping för denna material_ref.
    """
    material_ref = str(material_ref_or_article_ref)

    # 1) Kundens favoritartikel (om finns)
    try:
        favorite_article = get_favorite_article(customer_id, material_ref)
    except Exception as e:  # noqa: BLE001
        print(
            f"[pricing] Fel vid get_favorite_article({customer_id}, {material_ref}): {e}",
            file=sys.stderr,
        )
        favorite_article = None

    if favorite_article:
        return str(favorite_article).strip()

    # 2) Mapping Dockit-ref -> artikelnummer
    ref_map = _load_material_ref_map()
    mapped = ref_map.get(material_ref)
    if mapped:
        return str(mapped).strip()

    # 3) Fallback: anta att material_ref redan är artikelnummer
    #    Om den INTE är rent numerisk, logga att vi saknar mapping.
    if not material_ref.isdigit():
        _log_missing_material_mapping(material_ref=material_ref)

    return material_ref


def get_price(customer_id: Optional[str], article_ref: str) -> float:
    """
    Hämtar pris (exkl. moms) för en given material-/artikelreferens.

    Prioritetsordning:

      1) Kundens favoritartikel (via favorites.json) styr artikelnumret.
      2) Kundens prislista (price_list.json) styr priset om artikelnumret finns där.
      3) Grossistens prislistor (price_catalog*.json) via gn_pris.
      4) Om inget pris hittas returneras 0.0, ett fel loggas på stderr,
         och en rad skrivs till missing_prices.jsonl.

    Parametrar:
      customer_id: t.ex. kundens e-post eller namn (samma som övriga systemet använder).
      article_ref: material_ref (t.ex. "DIMMER-UNIV") eller ett artikelnummer.
    """
    if not article_ref:
        return 0.0

    # 1) Hitta vilket artikelnummer vi ska slå upp
    article_number = _resolve_article_number(customer_id, article_ref)

    # 2) Kundspecifik prislista (om finns)
    customer_prices = _load_customer_price_list(customer_id)
    if article_number in customer_prices:
        try:
            return float(customer_prices[article_number])
        except (TypeError, ValueError):
            # Om kundpris är trasigt, fortsätt till grossistpris
            pass

    # 3) Grossistpris (GN-pris) från normaliserade kataloger
    catalog = _load_price_catalog()
    base_price = catalog.get(article_number)
    if base_price is not None:
        try:
            return float(base_price)
        except (TypeError, ValueError):
            pass

    # 4) Inget pris hittades
    print(
        f"[pricing] No price found for ref='{article_ref}' "
        f"(mapped_article_number='{article_number}', customer_id={customer_id}). "
        "Using 0.0.",
        file=sys.stderr,
    )

    _log_missing_price(
        customer_id=customer_id,
        article_ref=article_ref,
        article_number=article_number,
    )

    return 0.0
