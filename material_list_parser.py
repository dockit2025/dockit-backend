from __future__ import annotations

import re
import json
from typing import Any, Dict, List


def _normalize_whitespace(text: str) -> str:
    """
    Slår ihop extra mellanslag och trim: " 10  m kabel " -> "10 m kabel".
    """
    return re.sub(r"\s+", " ", (text or "")).strip()


def _parse_quantity_and_unit(chunk: str) -> Dict[str, Any]:
    """
    Försöker hitta ett tal + ev. enhet i en delsträng.

    Exempel:
      "10m kabel 3x1,5"      -> qty=10, unit="m"
      "3 st vägguttag"       -> qty=3, unit="st"
      "vägguttag i kök"      -> qty=1, unit="st" (default)
    """
    text = _normalize_whitespace(chunk).lower()

    # Fångar första talet + ev. enhet (m, meter, m., st)
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(m|meter|m\.|st)?\b", text)
    if m:
        num_str = m.group(1).replace(",", ".")
        try:
            qty = float(num_str)
        except ValueError:
            qty = 1.0

        unit_raw = (m.group(2) or "").lower()
        if unit_raw in ("m", "meter", "m."):
            unit = "m"
        else:
            # "st" eller okänd enhet → vi tolkar som styck
            unit = "st"
    else:
        # Om vi inte hittar något tal alls
        qty = 1.0
        unit = "st"

    return {"qty": qty, "unit": unit}


def _guess_vp_ror_ref(text_norm: str) -> str:
    """
    Gissar vilken VP-rör-dimension som avses baserat på texten.
    Returnerar en material_ref (VP-ROR-16MM, VP-ROR-20, ...).
    """
    # Vi letar efter XXmm i texten
    m = re.search(r"(\d+)\s*mm", text_norm)
    if m:
        dim = m.group(1)
        if dim == "16":
            return "VP-ROR-16MM"
        if dim == "20":
            return "VP-ROR-20"
        if dim == "25":
            return "VP-ROR-25"
        if dim == "32":
            return "VP-ROR-32"
        if dim == "40":
            return "VP-ROR-40"
        if dim == "50":
            return "VP-ROR-50"

    # Om ingen specifik dimension hittas men vi vet att det är rör
    return "VP-ROR-16MM"


def _guess_material_ref(core_text: str) -> str:
    """
    Grov typning av material baserat på texten.
    Det här är ENDAST en intern "material_ref", inte ett artikelnummer.

    Viktigt:
      - Vi lägger oss på en trygg nivå:
        kabel / rör / uttag / dimmer / brytare / spot / kronbrytare / taklampa / dosor / kabelkanal.
      - Inga antaganden om arbetsmoment eller ATL.
    """
    t = _normalize_whitespace(core_text).lower()

    # Kabel 3G1,5 / 3x1,5-varianter
    if "3x1,5" in t or "3x1.5" in t or "3g1,5" in t or "3g1.5" in t:
        return "KABEL-3G1.5"

    # Kabelkanal (vit standard – vi använder en ref som mappar till din artikel)
    if "kabelkanal" in t:
        return "KABELKANAL-VIT"

    # Dosor – apparat / koppling / tak
    # Plural "apparatdosor" matchas av stammen "apparatdos"
    if "apparatdosa" in t or "apparatdos" in t:
        return "APPARATDOSA"
    if "kopplingsdosa" in t:
        return "KOPPLINGSDOSA"
    if "takdosa" in t:
        return "TAKDOSA"

    # VP-rör / rör – använd dimensioner om de finns, annars 16 mm som default
    if "vp" in t or "vp-rör" in t or "vp rör" in t or "vp-ror" in t or "rör" in t or "ror" in t:
        return _guess_vp_ror_ref(t)

    # Taklampa / plafond / takarmatur
    # Plural "taklampor" matchas via "taklamp"
    if (
        "takarmatur" in t
        or "taklampa" in t
        or "taklamp" in t
        or "plafond" in t
    ):
        return "TAKLAMPA"

    # Vägguttag (vanliga eluttag, inte nätverksuttag)
    if (
        ("vägguttag" in t or "vagguttag" in t or "eluttag" in t or "uttag" in t)
        and "nätverk" not in t
        and "natverk" not in t
        and "rj45" not in t
    ):
        # I material-läget jobbar vi främst med infällda uttag
        return "VAGGUTTAG-INF"

    # Kronbrytare – måste kollas före generell strömbrytare
    if "kron" in t and "brytare" in t:
        return "KRONBRYTARE"

    # Strömbrytare (generell kod – detaljer får UI/mapper lösa)
    if "strömbrytare" in t or "strombrytare" in t or "brytare" in t:
        return "STROMBRYTARE"

    # Spottar / spotlight
    if "spot" in t or "spotlight" in t or "spottar" in t or "spotlights" in t:
        return "SPOTLIGHT"

    # Dimmer
    if "dimmer" in t or "dimmers" in t:
        return "DIMMER-UNIV"

    return "UNKNOWN"


def _strip_leading_qty_and_unit(chunk: str) -> str:
    """
    Tar bort ledande "10m", "3 st" osv, och lämnar bara själva materialtexten.

    Exempel:
      "10 m kabel 3x1,5"   -> "kabel 3x1,5"
      "3 st vägguttag"     -> "vägguttag"
    """
    text = _normalize_whitespace(chunk)
    m = re.match(
        r"^(\d+(?:[.,]\d+)?)\s*(m|meter|m\.|st)?\b\s*(.*)$",
        text,
        flags=re.IGNORECASE,
    )
    if not m:
        return text
    tail = m.group(3) or ""
    return tail.strip() or text


def parse_material_text(text: str) -> Dict[str, Any]:
    """
    Parsar en fri text-sträng med material till strukturerad lista.

    Input-exempel:
      "10m 3x1,5, 8m vp-rör 16mm infällt, 3 infällda vägguttag, 1 dimmer"

    Output-struktur:
      {
        "free_text": "<originaltext>",
        "items": [
          {
            "raw": "10m 3x1,5",
            "parsed_core": "3x1,5",
            "qty": 10.0,
            "unit": "m",
            "material_ref": "KABEL-3G1.5"
          },
          ...
        ]
      }

    Viktigt:
      - Ingen tolkning av arbetsmoment, environment eller work_type.
      - Endast 1:1-tolkning av det som faktiskt står i texten.
    """
    raw_text = text or ""
    normalized = _normalize_whitespace(raw_text)

    if not normalized:
        return {"free_text": "", "items": []}

    # Skydda kabelbeteckningar som 3x1,5 så att kommat inte används som separator
    safe_text = re.sub(
        r"(\d+x\d+),(\d)",
        r"\1.\2",
        normalized,
        flags=re.IGNORECASE,
    )

    # Dela på "riktiga" kommatecken
    parts = [p.strip() for p in safe_text.split(",") if p.strip()]
    items: List[Dict[str, Any]] = []

    for part in parts:
        qty_unit = _parse_quantity_and_unit(part)
        core = _strip_leading_qty_and_unit(part)
        material_ref = _guess_material_ref(core)

        item: Dict[str, Any] = {
            "raw": part,
            "parsed_core": core,
            "qty": qty_unit["qty"],
            "unit": qty_unit["unit"],
            "material_ref": material_ref,
        }
        items.append(item)

    return {"free_text": raw_text, "items": items}


if __name__ == "__main__":
    # Enkel CLI för att testa parsningen manuellt:
    import sys

    if len(sys.argv) > 1:
        input_text = " ".join(sys.argv[1:])
    else:
        input_text = "10m 3x1,5, 8m vp-rör 20mm, 3 vägguttag, 1 dimmer, 1 apparatdosa, 1 kopplingsdosa, 1 takdosa, 5m kabelkanal, 3 taklampor"

    parsed = parse_material_text(input_text)
    print(json.dumps(parsed, ensure_ascii=False, indent=2))
