# file: test_time_calc.py
"""
Snabbtest för:
  - fri text -> tasks (dockit_custom_mapping.yaml)
  - tasks -> tid (ATL eller manual)
  - automatisk quantity från text (svenska talord / siffror)

Körs från projektroten med:
    python .\test_time_calc.py
"""

from __future__ import annotations

import re

from src.server.services.dockit_task_mapper import extract_tasks_from_text
from src.server.services.dockit_task_time_calc import compute_time_for_task
from src.server.loaders.atl_loader_new import ATLLoader, ATLConfig
from src.server.loaders.pricelist_loader import PriceListLoader, PriceListConfig
from src.server.services.quantity_extraction import (
    extract_quantity_from_text_segment,
)


def find_segment_for_task(full_text: str, task) -> str:
    """
    Försök hitta den del av texten som hör till ett visst task.

    Strategi (enkel men funkar för våra tester):
      - dela upp texten på kommatecken och punkt
      - kolla om någon del innehåller någon av taskets patterns
      - om ja -> använd den delen för quantity-extraktion
      - annars -> använd hela texten som fallback
    """
    segments = re.split(r"[,.]", full_text)
    patterns = getattr(task, "patterns", []) or []

    # jobba i lower-case för jämförelse
    lower_patterns = [p.lower() for p in patterns]
    full_lower = full_text.lower()

    # Först: försök matcha på segments
    for seg in segments:
        seg_stripped = seg.strip()
        if not seg_stripped:
            continue
        seg_lower = seg_stripped.lower()
        for p in lower_patterns:
            if p and p in seg_lower:
                return seg_stripped

    # Fallback: om ingen segmentmatch -> försök direkt i hela texten
    for p in lower_patterns:
        if p and p in full_lower:
            return full_text

    # Sista fallback: använd hela texten
    return full_text


def main() -> None:
    # Du kan ändra den här texten fritt vid testning
    text = (
        "Byta tre vägguttag i vardagsrummet, byta en strömbrytare och installera en dimmer, "
        "dra infällda rör till ett nytt uttag i sovrummet, installera en diskmaskin i köket, "
        "sätta upp en taklampa i hallen och installera en laddbox på uppfarten"
    )

    print("=" * 80)
    print(f"Fri text: {text}")
    print("=" * 80)

    # Ladda ATL och prislista
    atl = ATLLoader(ATLConfig())
    atl.load()

    pl = PriceListLoader(PriceListConfig())
    pl.load()

    # Hämta tasks från vår Dockit-task-mapper
    tasks = extract_tasks_from_text(
        text=text,
        atl_loader=atl,
        pricelist_loader=pl,
    )

    print(f"Antal matchade tasks: {len(tasks)}")

    for task in tasks:
        print("-" * 80)
        print(f"Task: {task.task_id} ({task.label})")

        # Hitta relevant textsnutt för just detta task
        segment = find_segment_for_task(text, task)

        # Plocka quantity ur segmentet (svenska talord / siffror / 'några' / 'ett par' etc.)
        qty = extract_quantity_from_text_segment(segment, default=1.0)

        # Räkna tid baserat på quantity
        res = compute_time_for_task(task, quantity=qty)

        print(f"  textsegment:       {segment!r}")
        print(f"  quantity:          {res.quantity}")
        print(f"  time_source:       {res.time_source}")
        print(f"  time_h_per_unit:   {res.time_h_per_unit}")
        print(f"  time_h_total:      {res.time_h_total}")

        if res.atl_row:
            print("  ATL-rad vald:")
            print(f"    moment_name:     {res.atl_row.get('moment_name')!r}")
            print(f"    arbetsmoment:    {res.atl_row.get('arbetsmoment')!r}")
            print(f"    variant:         {res.atl_row.get('variant')!r}")
            print(f"    variant_text:    {res.atl_row.get('variant_text')!r}")
            print(f"    unit:            {res.atl_row.get('unit')!r}")
            print(f"    time_h_per_unit: {res.atl_row.get('time_h_per_unit')!r}")

    print("-" * 80)
    print("Klart.")
    print("-" * 80)


if __name__ == "__main__":
    main()
