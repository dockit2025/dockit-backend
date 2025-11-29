"""
Mängduttag ur fri text. Regler enligt rules/quantity_extraction.md.
"""
from typing import Tuple, Optional
import re

RE_QTY = re.compile(r"(?P<qty>\d+[.,]?\d*)\s*(?P<unit>st|stycken|meter|m|m2|m³|m3|mm|cm|dm|kvadrat|punkter?)", re.I)

def extract_qty(text: str) -> Tuple[float, str, bool]:
    """
    return (qty, unit, is_default)
    """
    m = RE_QTY.search(text)
    if not m:
        return (1.0, "", True)
    qty = float(m.group("qty").replace(",", "."))
    unit = m.group("unit").lower().replace("m2","m²").replace("m3","m³")
    return (qty, unit, False)

