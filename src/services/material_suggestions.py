# fil: src/services/material_suggestions.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import json

from src.services.pricing import get_price
from src.services.favorites import get_favorite_article


# Projektrot, t.ex. D:\dockit-ai
ROOT = Path(__file__).resolve().parents[2]
MATERIAL_REF_MAP_PATH = ROOT / "knowledge" / "catalogs" / "material_ref_map.json"


def _load_material_ref_map() -> Dict[str, str]:
    """
    Läser in material_ref_map.json som:
    {
      "DIMMER-UNIV": "0000110",
      "APPRAM-1FACK": "0000120",
      ...
    }
    """
    if not MATERIAL_REF_MAP_PATH.exists():
        return {}

    try:
        with MATERIAL_REF_MAP_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}

    if not isinstance(data, dict):
        return {}

    out: Dict[str, str] = {}
    for k, v in data.items():
        if not isinstance(k, str):
            continue
        if not isinstance(v, str):
            v = str(v)
        k = k.strip()
        v = v.strip()
        if not k or not v:
            continue
        out[k] = v
    return out


def get_material_suggestions(
    customer_id: Optional[str],
    material_ref: str,
) -> List[Dict[str, Any]]:
    """
    Bygger en lista med materialsförslag för en given kund + material_ref.

    Prioritet:
      1) Kundens favorit (om finns)
      2) Global mapping i material_ref_map.json
      3) Direkt-användning av material_ref som artikelnummer (om prissatt)

    Returnerar lista i denna form (ordning = prioritet):
    [
      {
        "source": "favorite" | "mapping" | "direct",
        "article_ref": "<det som ska användas i pricing>",
        "price_sek": 97.0 eller 0.0,
      },
      ...
    ]
    """
    material_ref = (material_ref or "").strip()
    if not material_ref:
        return []

    ref_map = _load_material_ref_map()

    suggestions: List[Dict[str, Any]] = []

    # 1) Kundens favorit (om finns)
    favorite_article: Optional[str] = get_favorite_article(customer_id, material_ref)
    if favorite_article:
        favorite_article = favorite_article.strip()
        if favorite_article:
            price_for_customer = get_price(customer_id, material_ref)
            suggestions.append(
                {
                    "source": "favorite",
                    "article_ref": favorite_article,
                    "price_sek": price_for_customer,
                }
            )

    # 2) Global mapping (om finns och inte redan är samma som favorit)
    mapped_article: Optional[str] = ref_map.get(material_ref)
    if mapped_article:
        mapped_article = mapped_article.strip()
        if mapped_article and mapped_article != favorite_article:
            # Vi tar grossistpriset (utan kund-id) som info
            base_price = get_price(None, mapped_article)
            suggestions.append(
                {
                    "source": "mapping",
                    "article_ref": mapped_article,
                    "price_sek": base_price,
                }
            )

    # 3) Direkt-användning av material_ref som artikelnummer (om prissatt)
    #    och om det inte redan är samma som ovan
    direct_price = get_price(None, material_ref)
    if direct_price > 0:
        already_has_direct = any(
            s.get("article_ref") == material_ref for s in suggestions
        )
        if not already_has_direct:
            suggestions.append(
                {
                    "source": "direct",
                    "article_ref": material_ref,
                    "price_sek": direct_price,
                }
            )

    return suggestions
