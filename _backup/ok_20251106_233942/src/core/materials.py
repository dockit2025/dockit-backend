materials.py
"""
Standardmaterial per ATL-rad. Data enligt rules/material_bindings.md.
"""
from typing import Dict, List

MAPPINGS: Dict[str, List[Dict]] = {
    # Exempel
    "EL-001": [
        {"code":"DOSAKAPS","name":"Kapslad dosa IP54","unit":"st","qty_per_unit":1.0,"unit_price":0.0},
        {"code":"SKRUV4x40","name":"Träskruv 4×40","unit":"st","qty_per_unit":4.0,"unit_price":0.0},
    ]
}

def expand_materials(work_item: Dict) -> List[Dict]:
    lst = []
    for row in MAPPINGS.get(work_item.get("atl_id",""), []):
        qty = round((work_item.get("qty",1.0) or 1.0) * row["qty_per_unit"], 2)
        lst.append({**row, "qty": qty})
    return lst

