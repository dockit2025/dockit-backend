from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List


# Roten till projektet (D:\dockit-ai)
ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = ROOT / "templates" / "quote_document.html"


def _format_currency(value: float | int | None) -> str:
    """
    Formatera tal som svensk valuta: 7875 -> '7 875,00'.
    Om value är None returneras tom sträng.
    """
    if value is None:
        return ""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)

    # 7,875.00 -> 7 875,00
    s = f"{num:,.2f}"
    s = s.replace(",", " ").replace(".", ",")
    return s


def _obj_to_dict(obj: Any) -> Dict[str, Any]:
    """
    Hjälpfunktion: försök göra om quote/line/settings till dict
    oavsett om de är dataclasses, pydantic-modeller eller enkla objekt.
    """
    if obj is None:
        return {}

    if isinstance(obj, dict):
        return dict(obj)

    if is_dataclass(obj):
        return asdict(obj)

    # Pydantic-modeller brukar ha .dict()
    dict_method = getattr(obj, "dict", None)
    if callable(dict_method):
        return dict_method()

    # Fallback: plocka __dict__
    return {
        k: v
        for k, v in vars(obj).items()
        if not k.startswith("_")
    }


def build_rows_html(lines: Iterable[Any]) -> str:
    """
    Bygg HTML-raderna för tabellen (tbody) utifrån Dockit-rader.
    Förväntar sig att varje rad har åtminstone:
      - article_number eller item_no (annars löpnummer)
      - description
      - quantity
      - unit_price
      - line_total eller total
    """
    if not lines:
        return ""

    html_rows: List[str] = []
    for index, line in enumerate(lines, start=1):
        d = _obj_to_dict(line)

        item_no = (
            d.get("article_number")
            or d.get("item_no")
            or d.get("article_ref")
            or str(index)
        )
        description = d.get("description") or d.get("label") or ""
        quantity = d.get("quantity") or d.get("qty") or 0
        unit_price = (
            d.get("unit_price")
            or d.get("unit_price_sek")
            or d.get("price_per_unit")
            or 0
        )
        line_total = (
            d.get("line_total")
            or d.get("line_total_sek")
            or d.get("total")
            or (quantity or 0) * (unit_price or 0)
        )

        # Mängd formaterad med två decimaler
        try:
            quantity_str = f"{float(quantity):.2f}".replace(".", ",")
        except (TypeError, ValueError):
            quantity_str = str(quantity)

        row_html = (
            "<tr>"
            f'<td class="col-artnr">{item_no}</td>'
            f'<td class="col-benamning">{description}</td>'
            f'<td class="col-levant">{quantity_str}</td>'
            f'<td class="col-apris">{_format_currency(unit_price)}</td>'
            f'<td class="col-summa">{_format_currency(line_total)}</td>'
            "</tr>"
        )
        html_rows.append(row_html)

    # Indentering för att passa templaten snyggt
    return "\n          ".join(html_rows)


def build_context_from_quote(
    quote: Any,
    company_settings: Any,
    *,
    document_title: str = "Offert",
) -> Dict[str, str]:
    """
    Bygg context-dict med alla fält som templaten använder.

    Den här funktionen är medvetet tolerant: den försöker läsa ut fält
    från quote och settings oavsett om de är dict, dataclass eller modell.

    Du kan justera mappingen här när du vet exakt vilka fält som finns
    i Dockits quote- och settings-modeller.
    """
    q = _obj_to_dict(quote)
    c = _obj_to_dict(company_settings)

    # Datum / nummer
    document_number = (
        q.get("number")
        or q.get("quote_number")
        or q.get("id")
        or ""
    )
    document_date = (
        q.get("created_date_str")
        or q.get("created_at_str")
        or q.get("created_at")
        or q.get("date")
        or ""
    )
    ocr_number = q.get("ocr") or document_number

    # Kund
    customer_number = q.get("customer_number") or ""
    customer_vat_number = q.get("customer_vat_number") or q.get("customer_vat") or ""

    our_reference = (
        q.get("our_reference")
        or q.get("salesperson")
        or c.get("contact_person")
        or ""
    )

    payment_terms = q.get("payment_terms_label") or q.get("payment_terms") or ""
    due_date = q.get("due_date") or ""
    late_interest = q.get("late_interest_label") or q.get("late_interest") or ""

    # Företag
    company_name = c.get("company_name") or c.get("name") or ""
    company_address_line1 = c.get("address") or c.get("address_line1") or ""
    company_postcode = c.get("postcode") or c.get("zip_code") or ""
    company_city = c.get("city") or ""
    company_country = c.get("country") or "Sverige"
    company_phone = c.get("phone") or ""
    company_email = c.get("email") or ""
    company_bankgiro = c.get("bankgiro") or ""
    company_iban = c.get("iban") or ""
    company_org_number = c.get("org_number") or c.get("organization_number") or ""
    company_f_tax_text = c.get("f_tax_text") or "Ja"
    company_logo_url = c.get("logo_url") or ""

    # Rader
    lines = q.get("lines") or q.get("items") or []
    rows_html = build_rows_html(lines)

    # Summering – stöd även Dockit-fält (subtotal_sek / total_sek)
    subtotal_raw = (
        q.get("total_ex_vat")
        or q.get("subtotal_ex_vat")
        or q.get("subtotal_sek")
        or 0
    )
    total_raw = (
        q.get("total_inc_vat")
        or q.get("total")
        or q.get("total_sek")
        or subtotal_raw
    )

    vat_raw = q.get("vat_amount")
    if vat_raw is None:
        try:
            vat_raw = float(total_raw) - float(subtotal_raw)
        except Exception:
            vat_raw = 0

    vat_percent_value = q.get("vat_percent") or 25

    total_ex_vat = _format_currency(subtotal_raw)
    vat_percent = str(vat_percent_value)
    vat_amount = _format_currency(vat_raw)
    total_inc_vat = _format_currency(total_raw)

    # Övrig text
    note_text = (
        q.get("summary")
        or q.get("note")
        or q.get("description")
        or "Diverse elarbeten enligt överenskommelse."
    )

    context: Dict[str, str] = {
        "document_title": document_title,
        "document_number": str(document_number),
        "document_date": str(document_date),
        "ocr_number": str(ocr_number),
        "customer_number": str(customer_number),
        "customer_vat_number": str(customer_vat_number),
        "our_reference": str(our_reference),
        "payment_terms": str(payment_terms),
        "due_date": str(due_date),
        "late_interest": str(late_interest),
        "company_logo_url": str(company_logo_url),
        "company_name": str(company_name),
        "company_address_line1": str(company_address_line1),
        "company_postcode": str(company_postcode),
        "company_city": str(company_city),
        "company_country": str(company_country),
        "company_phone": str(company_phone),
        "company_email": str(company_email),
        "company_bankgiro": str(company_bankgiro),
        "company_iban": str(company_iban),
        "company_org_number": str(company_org_number),
        "company_f_tax_text": str(company_f_tax_text),
        "rows_html": rows_html,
        "total_ex_vat": total_ex_vat,
        "vat_percent": vat_percent,
        "vat_amount": vat_amount,
        "total_inc_vat": total_inc_vat,
        "note_text": str(note_text),
    }

    return context


def render_quote_html(context: Dict[str, Any]) -> str:
    """
    Läs HTML-templaten och ersätt alla [[nyckel]] med context-värden.
    Allt som inte finns i context ersätts med tom sträng.
    """
    html = TEMPLATE_PATH.read_text(encoding="utf-8")

    # Ersätt kända nycklar
    for key, value in context.items():
        placeholder = f"[[{key}]]"
        html = html.replace(placeholder, str(value))

    # Rensa kvarvarande [[...]] placeholders
    # så att det inte står taggar kvar i PDF/HTML.
    import re

    html = re.sub(r"\[\[[a-zA-Z0-9_]+\]\]", "", html)
    return html


