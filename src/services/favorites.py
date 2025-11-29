# fil: src/services/favorites.py

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from datetime import datetime


# ROOT = projektroten, t.ex. D:\dockit-ai
ROOT = Path(__file__).resolve().parents[2]
FAVORITES_PATH = ROOT / "knowledge" / "customers" / "favorites.json"


def _ensure_dir() -> None:
    """
    Ser till att katalogen knowledge/customers finns.
    """
    FAVORITES_PATH.parent.mkdir(parents=True, exist_ok=True)


def _load_favorites() -> Dict[str, Dict[str, Dict[str, Any]]]:
    """
    Läser in favorites.json.

    Struktur:
    {
      "customer:<nyckel>": {
        "DIMMER-UNIV": {
          "article_number": "0000110",
          "usage_count": 3,
          "updated_at": "2025-11-16T12:34:56"
        },
        ...
      },
      ...
    }
    """
    _ensure_dir()

    if not FAVORITES_PATH.exists():
        return {}

    try:
        with FAVORITES_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        # Om filen är korrupt – börja om tomt hellre än att krascha
        return {}

    if not isinstance(data, dict):
        return {}

    cleaned: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for cust_key, cust_map in data.items():
        if not isinstance(cust_key, str):
            continue
        if not isinstance(cust_map, dict):
            continue

        inner: Dict[str, Dict[str, Any]] = {}
        for material_ref, info in cust_map.items():
            if not isinstance(material_ref, str):
                continue
            if not isinstance(info, dict):
                continue
            inner[material_ref] = dict(info)

        cleaned[cust_key] = inner

    return cleaned


def _save_favorites(data: Dict[str, Dict[str, Dict[str, Any]]]) -> None:
    """
    Skriver tillbaka hela favorites-strukturen till JSON.
    """
    _ensure_dir()
    with FAVORITES_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _make_customer_key(customer_id: Optional[str]) -> Optional[str]:
    """
    Gör om ett godtyckligt kund-id (t ex email) till en nyckel för favorites.

    Exempel:
      "test@example.com" → "customer:test@example.com"
    """
    if not customer_id:
        return None
    cid = str(customer_id).strip()
    if not cid:
        return None
    return f"customer:{cid}"


def get_favorite_article(
    customer_id: Optional[str],
    material_ref: str,
) -> Optional[str]:
    """
    Hämta favorit-artikelnummer för en given kund + material_ref.

    Returnerar:
      - artikelnummer (str) om favorit finns
      - None om ingen favorit sparad
    """
    cust_key = _make_customer_key(customer_id)
    if not cust_key:
        return None

    favorites = _load_favorites()
    cust_map = favorites.get(cust_key) or {}
    entry = cust_map.get(material_ref)
    if not isinstance(entry, dict):
        return None

    art = entry.get("article_number")
    if not art:
        return None
    return str(art).strip() or None


def register_favorite_article(
    customer_id: Optional[str],
    material_ref: str,
    article_number: str,
) -> None:
    """
    Registrerar/uppdaterar en favoritartikel för en kund + material_ref.

    Används när elektrikern byter artikel i offerten:
      - t ex väljer en annan dimmer än standard.
    """
    cust_key = _make_customer_key(customer_id)
    if not cust_key:
        # Om vi inte vet vilken kund det gäller, kan vi inte spara favorit
        return

    material_ref = str(material_ref).strip()
    article_number = str(article_number).strip()
    if not material_ref or not article_number:
        return

    favorites = _load_favorites()

    cust_map = favorites.get(cust_key)
    if cust_map is None:
        cust_map = {}
        favorites[cust_key] = cust_map

    entry = cust_map.get(material_ref)
    if entry is None:
        entry = {
            "article_number": article_number,
            "usage_count": 1,
            "updated_at": datetime.utcnow().isoformat(timespec="seconds"),
        }
    else:
        # Uppdatera befintlig favorit
        entry = dict(entry)
        entry["article_number"] = article_number
        try:
            old_count = int(entry.get("usage_count", 0))
        except (TypeError, ValueError):
            old_count = 0
        entry["usage_count"] = old_count + 1
        entry["updated_at"] = datetime.utcnow().isoformat(timespec="seconds")

    cust_map[material_ref] = entry
    _save_favorites(favorites)


def list_favorites_for_customer(
    customer_id: Optional[str],
) -> Dict[str, Dict[str, Any]]:
    """
    Returnerar alla favoritartiklar för en kund.

    Struktur:
    {
      "DIMMER-UNIV": {
        "article_number": "...",
        "usage_count": ...,
        "updated_at": "..."
      },
      ...
    }

    Om ingen kund-id anges eller kunden inte har några favoriter
    returneras en tom dict.
    """
    cust_key = _make_customer_key(customer_id)
    if not cust_key:
        return {}

    favorites = _load_favorites()
    cust_map = favorites.get(cust_key) or {}

    # Kopiera så att anroparen inte kan mutera interna strukturen av misstag
    return {ref: dict(info) for ref, info in cust_map.items() if isinstance(info, dict)}
