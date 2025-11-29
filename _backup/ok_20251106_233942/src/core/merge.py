merge.py
"""
Text → ATL-kandidater.
- Indexera ATL (arbetsmoment + Synonymer)
- Matchning: exakt fras > synonym > token-Jaccard > fuzzy (valfritt)
- Returnera list[dict]: {atl_id, arbetsmoment, unit, qty, ai_confidence, raw_phrase, notes, unresolved}
"""
from typing import List, Dict

def merge_text_to_atl(input_text: str, atl_rows: List[Dict], mode: str = "accurate") -> List[Dict]:
    # Placeholder: koppla mot reglerna i rules/merge_rules.md och quantity_extraction.md
    # Här ska du implementera tokenisering, n-gram och synonymindex.
    return []

