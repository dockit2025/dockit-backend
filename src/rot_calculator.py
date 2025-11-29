"""
ROT-beräkning för offertmotorn.

Grundidé:
- ROT gäller endast på arbetskostnad (work-rader som är ROT-berättigade).
- ROT-belopp = min(arbetskostnad * rot_rate, max_rot_per_person * num_persons)
- ROT fördelas proportionerligt över alla ROT-berättigade work-rader.

Denna modul är fristående och jobbar på listor av dicts, t.ex. dina genererade rader
innan de skickas tillbaka från /quotes/draft.

Antagande om radstruktur (justera vid behov):
- line["line_type"] == "work" eller "material"
- line.get("is_rot_eligible", False) markerar om raden är ROT-berättigad
- line["total_price_sek"] är totalbelopp (inkl. moms) för raden

Du kan sedan:
- anropa apply_rot_to_lines(lines, config)
- få tillbaka (updated_lines, rot_summary)
och själv bestämma hur du presenterar ROT på offerten (t.ex. en separat rad).
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Tuple


@dataclass
class RotConfig:
    # Standard-ROT (justera rot_rate om reglerna ändras, t.ex. tillfälligt 50 %)
    rot_rate: float = 0.30               # 30 % av arbetskostnaden
    max_per_person_sek: int = 50_000     # max ROT per person och år
    num_persons: int = 1                 # antal personer som ROT ska delas på

    @property
    def max_total_rot_sek(self) -> int:
        return self.max_per_person_sek * self.num_persons


def _get_rot_eligible_work_lines(lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filtrerar ut ROT-berättigade arbetsrader.
    """
    eligible = []
    for line in lines:
        if line.get("line_type") != "work":
            continue
        if not line.get("is_rot_eligible", False):
            continue
        total = line.get("total_price_sek")
        if total is None:
            continue
        if total <= 0:
            continue
        eligible.append(line)
    return eligible


def apply_rot_to_lines(
    lines: List[Dict[str, Any]],
    config: RotConfig,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Beräknar och applicerar ROT på ROT-berättigade work-rader.

    Strategi:
    1. Räkna fram total ROT-berättigad arbetskostnad.
    2. Beräkna teoretiskt ROT: arbetskostnad * rot_rate.
    3. Begränsa ROT till max_total_rot_sek.
    4. Fördela ROT-beloppet proportionerligt på varje ROT-rad.
    5. Lägg till nycklar på raderna:
       - "rot_share_sek": hur mycket av total ROT som hör till denna rad
       - "total_after_rot_sek": radens total efter ROT (dvs total_price_sek - rot_share_sek)

    Funktionen förändrar INTE inputlistan in-place, utan returnerar en ny lista.
    rot_summary ger ett sammandrag för offerten.
    """
    eligible_lines = _get_rot_eligible_work_lines(lines)

    if not eligible_lines:
        # Inga ROT-berättigade rader – returnera original + tom summary
        return list(lines), {
            "rot_applied": False,
            "rot_rate": config.rot_rate,
            "rot_amount_sek": 0,
            "rot_limited_by_max": False,
            "max_total_rot_sek": config.max_total_rot_sek,
            "num_persons": config.num_persons,
        }

    # 1. Total ROT-berättigad arbetskostnad
    total_rot_eligible = sum(l["total_price_sek"] for l in eligible_lines)

    # 2. Teoretiskt ROT-belopp
    theoretical_rot = total_rot_eligible * config.rot_rate

    # 3. Begränsa av maxbelopp
    max_total_rot = config.max_total_rot_sek
    rot_amount = min(theoretical_rot, max_total_rot)
    rot_limited_by_max = rot_amount < theoretical_rot

    if rot_amount <= 0:
        # Rent defensivt – inget att göra
        return list(lines), {
            "rot_applied": False,
            "rot_rate": config.rot_rate,
            "rot_amount_sek": 0,
            "rot_limited_by_max": False,
            "max_total_rot_sek": config.max_total_rot_sek,
            "num_persons": config.num_persons,
        }

    # 4. Fördela ROT proportionerligt baserat på radens andel av arbetskostnaden
    updated_lines: List[Dict[str, Any]] = []
    for line in lines:
        new_line = dict(line)

        if line in eligible_lines:
            share_ratio = line["total_price_sek"] / total_rot_eligible
            line_rot = rot_amount * share_ratio

            # Runda av till hela kronor (du kan byta till ören om du vill vara mer exakt)
            line_rot_rounded = round(line_rot)

            new_line["rot_share_sek"] = line_rot_rounded
            new_line["total_after_rot_sek"] = line["total_price_sek"] - line_rot_rounded
        else:
            # Ingen ROT på den här raden
            new_line["rot_share_sek"] = 0
            # För icke-ROT-rader är total_after_rot samma som original
            if "total_price_sek" in line:
                new_line["total_after_rot_sek"] = line["total_price_sek"]

        updated_lines.append(new_line)

    rot_summary = {
        "rot_applied": True,
        "rot_rate": config.rot_rate,
        "rot_amount_sek": round(rot_amount),
        "rot_limited_by_max": rot_limited_by_max,
        "max_total_rot_sek": config.max_total_rot_sek,
        "num_persons": config.num_persons,
        "total_rot_eligible_work_sek": total_rot_eligible,
    }

    return updated_lines, rot_summary
