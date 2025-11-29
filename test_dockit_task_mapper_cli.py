# file: test_dockit_task_mapper_cli.py
"""
Enkel CLI för att testa Dockit task-mapping från fri text.

Exempel:

    python .\test_dockit_task_mapper_cli.py "Byta två vägguttag i vardagsrum och installera laddbox på uppfarten"

Scriptet:
  - Laddar ATL (Del 7) via ATLLoader
  - Laddar Storel-prislista via PriceListLoader
  - Läser Dockit custom-mapping (knowledge/dockit/dockit_custom_mapping.yaml)
  - Matchar fri text mot tasks och skriver ut:
      - vilka tasks som träffar,
      - hur de matchade,
      - ev. ATL-kandidater,
      - ev. prislisteträffar (när pricing_source = "pricelist").
"""

from __future__ import annotations

import sys
from pprint import pprint
from typing import Optional

from pathlib import Path

# Importera befintliga loaders
from src.server.loaders.atl_loader_new import ATLLoader, ATLConfig  # type: ignore
from src.server.loaders.pricelist_loader import PriceListLoader, PriceListConfig  # type: ignore

# Importera vår nya task-mapper
from src.server.services.dockit_task_mapper import (
    extract_tasks_from_text,
)


def _init_atl_loader() -> Optional[ATLLoader]:
    """
    Skapar en ATLLoader med default-konfiguration och laddar Del 7.
    Om något går fel returneras None.
    """
    try:
        cfg = ATLConfig()  # antar att default pekar på knowledge/atl/Del7_ATL_Total.csv
        loader = ATLLoader(cfg)
        loader.load()
        return loader
    except Exception as exc:  # pragma: no cover
        print(f"[VARNING] Misslyckades att initiera ATLLoader: {exc}")
        return None


def _init_pricelist_loader() -> Optional[PriceListLoader]:
    """
    Skapar en PriceListLoader med default-konfiguration och laddar Storel-GN.
    Om något går fel returneras None.
    """
    try:
        cfg = PriceListConfig()  # antar default -> knowledge/catalogs/Storel-GN.csv
        loader = PriceListLoader(cfg)
        loader.load()
        return loader
    except Exception as exc:  # pragma: no cover
        print(f"[VARNING] Misslyckades att initiera PriceListLoader: {exc}")
        return None


def main() -> None:
    if len(sys.argv) < 2:
        print("Användning:")
        print("  python .\\test_dockit_task_mapper_cli.py \"beskrivning av jobb\"")
        print()
        print("Exempel:")
        print("  python .\\test_dockit_task_mapper_cli.py \"Byta två vägguttag i vardagsrum och installera laddbox på uppfarten\"")
        sys.exit(1)

    job_text = sys.argv[1]
    print("=" * 80)
    print(f"Fri text: {job_text}")
    print("=" * 80)
    print()

    # Initiera loaders
    atl_loader = _init_atl_loader()
    pricelist_loader = _init_pricelist_loader()

    if atl_loader is None:
        print("[INFO] ATLLoader är inte tillgänglig – time_source='atl' ger inga ATL-kandidater.")
    if pricelist_loader is None:
        print("[INFO] PriceListLoader är inte tillgänglig – pricing_source='pricelist' ger inga prislisteträffar.")

    # Kör extraction
    try:
        matched_tasks = extract_tasks_from_text(
            text=job_text,
            mapping_path=None,              # använder default: knowledge/dockit/dockit_custom_mapping.yaml
            atl_loader=atl_loader,
            pricelist_loader=pricelist_loader,
            max_atl_results=5,
            max_pricelist_results=3,
        )
    except FileNotFoundError as exc:
        print(f"[FEL] Hittade inte dockit-mapping: {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"[FEL] Något gick fel vid matchning: {exc}")
        sys.exit(1)

    if not matched_tasks:
        print("Inga tasks matchade den angivna texten.")
        sys.exit(0)

    print(f"Antal matchade tasks: {len(matched_tasks)}")
    print()

    for idx, t in enumerate(matched_tasks, start=1):
        print("-" * 80)
        print(f"Task #{idx}")
        print(f"  id:          {t.task_id}")
        print(f"  label:       {t.label}")
        print(f"  category:    {t.category}")
        print(f"  patterns:    {t.matched_patterns}")
        print(f"  time_source: {t.time_source}")
        print(f"  manual_time_minutes_per_unit: {t.manual_time_minutes_per_unit}")
        print(f"  pricing_source: {t.pricing_source}")
        print(f"  material_suggestions: {t.material_suggestions}")
        print()

        # ATL-kandidater
        if t.time_source == "atl":
            print("  ATL-kandidater:")
            if not t.atl_candidates:
                print("    (inga ATL-träffar för denna task)")
            else:
                for i, hit in enumerate(t.atl_candidates[:5], start=1):
                    moment = hit.get("moment_name")
                    arbetsmoment = hit.get("arbetsmoment")
                    variant = hit.get("variant")
                    variant_text = hit.get("variant_text")
                    unit = hit.get("unit")
                    time_h = hit.get("time_h_per_unit")
                    print(f"    [{i}] moment={moment!r}, arbetsmoment={arbetsmoment!r}")
                    print(f"        variant={variant!r} ({variant_text!r}), enhet={unit!r}, tid_h_per_enhet={time_h}")
            print()

        # Prislisteträffar
        if t.pricing_source == "pricelist":
            print("  Prislisteträffar:")
            if not t.pricelist_candidates:
                print("    (inga prislisteträffar för denna task)")
            else:
                for i, row in enumerate(t.pricelist_candidates[:5], start=1):
                    print(
                        f"    [{i}] "
                        f"Artikelnummer={row.get('Artikelnummer')!r}, "
                        f"Benämning={row.get('Benämning')!r}, "
                        f"Enhet={row.get('Enhet')!r}, "
                        f"Materialgrupp={row.get('Materialgrupp')!r}, "
                        f"Pris={row.get('Pris')!r}"
                    )
            print()

    print("-" * 80)
    print("Klart.")
    print("-" * 80)


if __name__ == "__main__":
    main()
