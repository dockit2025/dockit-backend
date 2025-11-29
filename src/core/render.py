# src/core/render.py
"""
Render: offer-JSON + templates/offer_template.html → HTML
- Beräknar rad- och totalsummor
- Formaterar pengar/tid/antal enligt svenska (komma + U+202F)
- Injicerar rader i:
    - <tbody id="material-rows">
    - <tbody id="labor-rows">
    - <div id="totals-box">
- Ersätter alla {{...}} fält inkl. notes.terms
Obs: Post-typografi (en-dash, mm², U+202F-säkring etc.) görs i cleanup-steget.
"""

from pathlib import Path
from typing import Dict, List, Tuple

NBSP_NARROW = "\u202f"  # U+202F smalt icke-brytande mellanrum

# ---------- Formatterare (svenska) ----------

def _group_thousands(int_str: str) -> str:
    """Grupera heltalsdelen med smalt NBSP (U+202F) var 3:e siffra, från höger."""
    s = "".join(ch for ch in int_str if ch.isdigit())
    if len(s) <= 3:
        return s
    parts: List[str] = []
    while s:
        parts.append(s[-3:])
        s = s[:-3]
    return NBSP_NARROW.join(reversed(parts))

def format_money(value: float) -> str:
    """22 844,20 kr (U+202F som tusenavskiljare, komma som decimalseparator)."""
    sign = "-" if value < 0 else ""
    v = abs(float(value or 0.0))
    cents = "{:.2f}".format(v)           # "22844.20"
    int_part, dec_part = cents.split(".")
    return "{}{},{} kr".format(sign, _group_thousands(int_part), dec_part)

def format_hours(value: float) -> str:
    """3,60 h (exakt två decimaler, ingen tusengrupp)."""
    s = "{:.2f}".format(float(value or 0.0)).replace(".", ",")
    return "{} h".format(s)

def format_qty(value: float) -> str:
    """Antal/kvantitet med två decimaler, komma som decimaltecken."""
    return "{:.2f}".format(float(value or 0.0)).replace(".", ",")

# ---------- Render-kärna ----------

def _render_material_rows(material: List[Dict]) -> Tuple[str, float]:
    rows: List[str] = []
    sum_material = 0.0
    for m in (material or []):
        qty = float(m.get("qty", 0) or 0)
        unit_price = float(m.get("unit_price", 0) or 0)
        row_total = qty * unit_price
        sum_material += row_total

        rows.append(
            "<tr>"
            "<td class='mono'>{sku}</td>"
            "<td>{name}</td>"
            "<td class='mono'>{unit}</td>"
            "<td class='mono'>{qty}</td>"
            "<td class='mono'>{unit_price}</td>"
            "<td class='mono'>{row_total}</td>"
            "<td>{supplier}</td>"
            "</tr>".format(
                sku=m.get("sku", ""),
                name=m.get("name", ""),
                unit=m.get("unit", ""),
                qty=format_qty(qty),
                unit_price=format_money(unit_price),
                row_total=format_money(row_total),
                supplier=m.get("supplier", ""),
            )
        )
    return ("".join(rows), sum_material)

def _render_labor_rows(labor: List[Dict], labor_rate: float) -> Tuple[str, float, float]:
    rows: List[str] = []
    sum_hours = 0.0
    sum_labor = 0.0
    rate = float(labor_rate or 0.0)

    for l in (labor or []):
        qty = float(l.get("qty", 0) or 0)
        tpu = float(l.get("time_per_unit", 0) or 0)
        time_total = l.get("time_total", None)
        if time_total in (None, "", 0):
            time_total = tpu * qty

        sum_hours += float(time_total or 0.0)
        row_sum = float(time_total or 0.0) * rate
        sum_labor += row_sum

        # presentation: om 0 → tid/à-pris/radsumma lämnas tomt
        show_empty = (time_total is None) or (float(time_total) == 0.0)
        tid = "" if show_empty else format_hours(float(time_total))
        apris = "" if show_empty else format_money(rate)
        rsum = "" if show_empty else format_money(row_sum)

        notes = (l.get("notes") or "").strip()
        if show_empty:
            suffix = "(Ej tidsatt i Del 7 – tidsätts i annan ATL-del)"
            notes = (notes + " " + suffix).strip()
        notes_html = "<div class=\"small muted\">{}</div>".format(notes) if notes else ""

        rows.append(
            "<tr>"
            "<td>{arbetsmoment}{notes}</td>"
            "<td>{moment}</td>"
            "<td>{underlag}</td>"
            "<td class='mono'>{unit}</td>"
            "<td class='mono'>{tid}</td>"
            "<td class='mono'>{apris}</td>"
            "<td class='mono'>{rsum}</td>"
            "</tr>".format(
                arbetsmoment=l.get("arbetsmoment", ""),
                notes=notes_html,
                moment=l.get("moment", ""),
                underlag=l.get("underlag", ""),
                unit=l.get("unit", ""),
                tid=tid,
                apris=apris,
                rsum=rsum,
            )
        )

    return ("".join(rows), sum_hours, sum_labor)

def _inject_rows(html: str, rows_html: str, tbody_id: str) -> str:
    """Lägg in rader direkt efter öppningstagen för <tbody id="...">."""
    marker = '<tbody id="{}">'.format(tbody_id)
    if marker in html:
        return html.replace(marker, marker + rows_html)
    marker2 = "<tbody id='{}'>".format(tbody_id)
    return html.replace(marker2, marker2 + rows_html)

def _replace(html: str, key: str, value: str) -> str:
    return html.replace("{{" + key + "}}", value if value is not None else "")

def render_offer(offer: Dict, template_path: str) -> Dict[str, object]:
    # 1) Läs mall
    template = Path(template_path).read_text(encoding="utf-8")

    # 2) Beräkna rader och summor
    mat_rows_html, sum_material = _render_material_rows(offer.get("material", []))
    labor_rows_html, sum_hours, sum_labor = _render_labor_rows(
        offer.get("labor", []),
        offer.get("pricing", {}).get("labor_rate", 0.0)
    )

    subtotal_excl = sum_material + sum_labor
    vat_rate = float(offer.get("pricing", {}).get("vat_rate", 0.25))
    vat_amount = subtotal_excl * vat_rate
    total_incl = subtotal_excl + vat_amount

    # 3) Totals-box (exakt fem rader)
    hours_label = format_hours(sum_hours).replace(" h", "")  # "3,60"
    totals_box = (
        "<div class='line'><span>Material</span><span>{m}</span></div>"
        "<div class='line'><span>Arbete ({h} h)</span><span>{a}</span></div>"
        "<div class='line'><span>Delsumma (exkl. moms)</span><span>{d}</span></div>"
        "<div class='line'><span>Moms {vr}&nbsp;%</span><span>{v}</span></div>"
        "<div class='line total'><span>Totalsumma (inkl. moms)</span><span>{t}</span></div>"
    ).format(
        m=format_money(sum_material),
        h=hours_label,
        a=format_money(sum_labor),
        d=format_money(subtotal_excl),
        vr=int(round(vat_rate * 100)),
        v=format_money(vat_amount),
        t=format_money(total_incl),
    )

    # 4) Ersätt fält (inga templatemarkörer ska lämnas)
    html = template
    # Projekt
    html = _replace(html, "project.id", str(offer.get("project", {}).get("id", "")))
    html = _replace(html, "project.title", offer.get("project", {}).get("title", ""))
    html = _replace(html, "project.date", offer.get("project", {}).get("date", ""))
    html = _replace(html, "project.valid_until", offer.get("project", {}).get("valid_until", ""))

    # Parter
    for side in ("supplier", "client"):
        s = offer.get(side, {}) or {}
        html = _replace(html, side + ".name", s.get("name", ""))
        html = _replace(html, side + ".street", s.get("street", ""))
        html = _replace(html, side + ".zip_city", s.get("zip_city", ""))
        html = _replace(html, side + ".orgno", s.get("orgno", ""))
        html = _replace(html, side + ".email", s.get("email", ""))

    # Villkorstext
    html = _replace(html, "notes.terms", (offer.get("notes", {}) or {}).get("terms", ""))

    # 5) Injicera rader & totals
    html = _inject_rows(html, mat_rows_html, "material-rows")
    html = _inject_rows(html, labor_rows_html, "labor-rows")
    html = html.replace('<div id="totals-box"></div>', '<div id="totals-box">' + totals_box + "</div>")

    # 6) Returnera HTML + numeriska totals (för ev. debugging/validator)
    return {
        "html": html,
        "totals": {
            "sum_material": round(sum_material, 2),
            "sum_labor": round(sum_labor, 2),
            "sum_hours": round(sum_hours, 2),
            "subtotal_excl": round(subtotal_excl, 2),
            "vat_amount": round(vat_amount, 2),
            "total_incl": round(total_incl, 2),
        }
    }

