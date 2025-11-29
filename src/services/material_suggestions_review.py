from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------
# Paths
# ---------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]

# Se till att projektroten finns i sys.path så att "src.*" fungerar
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PRICE_CATALOG_PATH = ROOT / "knowledge" / "catalogs" / "price_catalog.json"
MATERIAL_REF_MAP_PATH = ROOT / "knowledge" / "catalogs" / "material_ref_map.json"

LOG_DIR = ROOT / "knowledge" / "logs"
MATERIAL_SUGGESTIONS_LOG = LOG_DIR / "material_suggestions.jsonl"

# ---------------------------------------------------------
# Importer för GPT-läget
# ---------------------------------------------------------

from openai import OpenAI
from src.services.ai_specs import load_material_generation_spec
from src.services.ai_suggestions import get_top_missing_material_refs


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def _load_price_catalog() -> Dict[str, float]:
    """Läser {artikelnummer: gn_pris} från price_catalog.json."""
    if not PRICE_CATALOG_PATH.exists():
        return {}

    try:
        with PRICE_CATALOG_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f) or []
    except Exception:
        return {}

    out: Dict[str, float] = {}

    for row in data:
        if not isinstance(row, dict):
            continue
        art = str(row.get("artikelnummer") or "").strip()
        price = row.get("gn_pris")
        try:
            price = float(price)
        except Exception:
            continue
        if art:
            out[art] = price

    return out


def _load_material_ref_map() -> Dict[str, str]:
    """Läser material_ref_map.json."""
    if not MATERIAL_REF_MAP_PATH.exists():
        return {}

    try:
        with MATERIAL_REF_MAP_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f) or {}
    except Exception:
        return {}

    out: Dict[str, str] = {}
    for ref, art in data.items():
        if ref and art:
            out[str(ref)] = str(art).strip()

    return out


def _append_json_line(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
        f.write("\n")


# ---------------------------------------------------------
# Material review (manuell + GPT)
# ---------------------------------------------------------

def _print_header(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70 + "\n")


def _find_similar_articles(article_hint: str, catalog: Dict[str, float]) -> List[Tuple[str, float]]:
    """
    Returnerar en snabb lista på artikelnummer som *kan vara* liknande.
    Enkel heuristik: matcha prefix eller substring.
    """
    out: List[Tuple[str, float]] = []

    hint = str(article_hint or "").lower().strip()
    if not hint:
        return out

    for art, price in catalog.items():
        art_l = art.lower()
        if hint in art_l or art_l.startswith(hint):
            out.append((art, price))

    # Returnera max 10 för överskådlighet
    return out[:10]


def _write_material_mapping(updated: Dict[str, str]) -> None:
    """Skriver mappingen till material_ref_map.json."""
    existing = _load_material_ref_map()
    existing.update(updated)

    MATERIAL_REF_MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MATERIAL_REF_MAP_PATH.open("w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2, sort_keys=True)


def review_material_suggestions(gpt_output: Dict[str, Any]) -> None:
    """
    Huvudfunktion: visar varje material_ref-förslag och låter användaren:
    A = acceptera
    R = avvisa
    E = editera
    """
    suggestions = gpt_output.get("suggested_materials") or {}

    if not suggestions:
        print("Inga materialförslag i GPT-outputen.")
        return

    catalog = _load_price_catalog()

    approved: Dict[str, str] = {}

    for material_ref, suggested_article in suggestions.items():

        _print_header(f"GPT-Förslag – MaterialRef: {material_ref}")

        print(f"Föreslaget artikelnummer: {suggested_article}\n")

        similar = _find_similar_articles(suggested_article, catalog)
        if similar:
            print("Liknande artiklar i prislistan:")
            for art, price in similar:
                print(f"  - {art}  ({price} kr)")
        else:
            print("Inga direkta matchningar i prislistan.")

        print("\nVad vill du göra?")
        print("  [A] Acceptera")
        print("  [R] Avvisa")
        print("  [E] Editera artikelnummer")
        val = input("Val: ").strip().lower()

        if val == "a":
            approved[material_ref] = suggested_article
            print("→ Accepterad.\n")

        elif val == "e":
            new_art = input("Ange nytt artikelnummer: ").strip()
            if new_art:
                approved[material_ref] = new_art
                print("→ Sparad med ändring.\n")
            else:
                print("→ Ingen ändring sparad.\n")

        else:
            print("→ Avvisad.\n")

    # Skriv ändringar till material_ref_map.json
    if approved:
        _write_material_mapping(approved)

        event = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "type": "material_suggestions",
            "approved": approved,
        }
        _append_json_line(MATERIAL_SUGGESTIONS_LOG, event)

        print("\nKLART: följande mappingar sparades:")
        for ref, art in approved.items():
            print(f"  {ref} → {art}")
        print("\n")
    else:
        print("\nInga förslag sparades.\n")


# ---------------------------------------------------------
# GPT-läge: hämta saknade refs -> GPT -> review
# ---------------------------------------------------------

def run_gpt_generation_materials(limit: int = 50) -> Dict[str, Any]:
    """
    1. Hämtar GPT-specifikationen för material
    2. Hämtar saknade material_ref från loggen
    3. Anropar GPT (OpenAI) med JSON-input {"materials": [...]}
    4. Returnerar GPT:s output som dict
    """
    print("\nLaddar GPT-specifikation för material...")
    spec = load_material_generation_spec()

    print("Samlar saknade material_ref från loggen...")
    top_refs = get_top_missing_material_refs(limit=limit)

    if not top_refs:
        print("Inga saknade material_ref hittades i missing_material_mappings.jsonl.")
        return {
            "suggested_materials": {},
            "notes": "Inga saknade material_ref i loggen.",
        }

    materials_in = {
        "materials": [ref for ref, _count in top_refs],
    }

    print("Kontaktar GPT-modellen (material)...")
    client = OpenAI()

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": spec},
            {
                "role": "user",
                "content": json.dumps(materials_in, ensure_ascii=False),
            },
        ],
        response_format={"type": "json_object"},
    )

    try:
        content = response.choices[0].message.content
        data = json.loads(content)
    except Exception:
        print("Kunde inte tolka GPT-svar, returnerar tomma förslag.")
        return {
            "suggested_materials": {},
            "notes": "Kunde inte tolka GPT-svar.",
        }

    print("GPT-generering för material klar.")
    return data


# ---------------------------------------------------------
# CLI
# ---------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Användning:")
        print("  python material_suggestions_review.py <gpt_output.json>")
        print("  python material_suggestions_review.py --gpt")
        sys.exit(1)

    arg = sys.argv[1]

    if arg == "--gpt":
        # Kör GPT-flödet direkt mot loggarna
        gpt_output = run_gpt_generation_materials(limit=50)
        # Spara en kopia av GPT-outputen för spårbarhet
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        out_path = LOG_DIR / "gpt_material_suggestions_runtime.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(gpt_output, f, ensure_ascii=False, indent=2)
        print(f"\nGPT-material-output sparad till: {out_path}\n")

        print("========== STARTAR MATERIAL-REVIEW ==========\n")
        review_material_suggestions(gpt_output)
    else:
        json_path = Path(arg)

        if not json_path.exists():
            print(f"Filen finns inte: {json_path}")
            sys.exit(1)

        with json_path.open("r", encoding="utf-8") as f:
            gpt_output = json.load(f)

        print("\n========== STARTAR MATERIAL-REVIEW ==========\n")
        review_material_suggestions(gpt_output)
