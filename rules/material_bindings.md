# rules/material_bindings.md  v1.0
mapping per atl_id för standardmaterial.
Exempel:
EL-001: DOSAKAPS 1.0 st, SKRUV4x40 4.0 st
EL-014: EKLK-3G1.5 1.0 meter, DRAGFJADER 0.02 st
EL-052: UTTDUB 1.0 st, RAM1 1.0 st, UNDERL 1.0 st
Beräkning: material.qty = work_item.qty * qty_per_unit
