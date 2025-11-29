# file: src/server/services/dockit_task_time_calc.py
"""
Tidberäkning för Dockit-tasks.

Bygger vidare på MatchedTask från dockit_task_mapper.py och räknar fram
tid i timmar per task, baserat på:

- time_source == "manual" -> manual_time_minutes_per_unit
- time_source == "atl"    -> ATL-rad(er) med time_h_per_unit

Inga gissningar:
- Vi väljer alltid den första ATL-raden med ett giltigt numeriskt värde
  i time_h_per_unit.
- Om ingen giltig tid hittas returneras tid = None.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, List

from .dockit_task_mapper import MatchedTask


@dataclass
class TaskTimeResult:
    """
    Resultat från tidberäkning för en task.
    """

    task_id: str
    label: str

    quantity: float

    # total tid i timmar (eller None om vi inte kunde räkna)
    time_h_total: Optional[float]

    # tid per enhet i timmar (från manual eller ATL)
    time_h_per_unit: Optional[float]

    # källa: "manual", "atl" eller "unknown"
    time_source: str

    # om ATL användes: en förenklad representation av vilken rad vi byggde på
    atl_row: Optional[Dict[str, Any]]


def _choose_best_atl_row(candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Väljer den första ATL-raden som har ett giltigt numeriskt värde i 'time_h_per_unit'.

    Inga gissningar:
    - Vi försöker inte slå ihop flera rader.
    - Vi försöker inte tolka NaN som 0.
    """
    for row in candidates:
        value = row.get("time_h_per_unit")
        if value is None:
            continue
        try:
            # time_h_per_unit ska redan vara float enligt ATLLoader, men vi är defensiva
            v = float(value)
        except Exception:
            continue

        # Filtrera bort NaN (float('nan') != float('nan'))
        if v != v:
            continue

        return row

    return None


def compute_time_for_task(
    task: MatchedTask,
    quantity: float = 1.0,
) -> TaskTimeResult:
    """
    Räknar fram tid i timmar för en given task och kvantitet.

    Strategi:
      - Om task.time_source == "manual" och manual_time_minutes_per_unit finns:
          time_h_per_unit = manual_time_minutes_per_unit / 60
      - Om task.time_source == "atl" och det finns atl_candidates:
          välj första kandidat med giltig time_h_per_unit (ej NaN),
          time_h_per_unit = den kandidatens time_h_per_unit
      - Annars: time_h_per_unit = None, time_h_total = None
    """
    qty = float(quantity) if quantity is not None else 1.0
    if qty < 0:
        qty = 0.0

    time_source = task.time_source or "unknown"
    time_h_per_unit: Optional[float] = None
    atl_row: Optional[Dict[str, Any]] = None

    if task.time_source == "manual" and task.manual_time_minutes_per_unit is not None:
        try:
            time_h_per_unit = float(task.manual_time_minutes_per_unit) / 60.0
        except Exception:
            time_h_per_unit = None

    elif task.time_source == "atl" and task.atl_candidates:
        atl_row = _choose_best_atl_row(task.atl_candidates)
        if atl_row is not None:
            value = atl_row.get("time_h_per_unit")
            try:
                v = float(value)
            except Exception:
                v = float("nan")

            if v == v:  # ej NaN
                time_h_per_unit = v

    if time_h_per_unit is None:
        time_h_total = None
    else:
        time_h_total = time_h_per_unit * qty

    return TaskTimeResult(
        task_id=task.task_id,
        label=task.label,
        quantity=qty,
        time_h_total=time_h_total,
        time_h_per_unit=time_h_per_unit,
        time_source=time_source,
        atl_row=atl_row,
    )
