from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List
import html as _html


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = ROOT / "templates" / "quote_document.html"


def _h(x: Any) -> str:
    """
    HTML-escapar fri text så den inte kan förstöra layouten.
    """
    if x is None:
        return ""
    return _html.escape(str(x), quote=True)


def _format_currency(value: float | int | None) -> str:
    if value is None:
        return ""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return _h(value)

    s = f"{num:,.2f}"
    return s.replace(",", " ").replace(".", ",")


def _obj_to_dict(obj: Any) -> Dict[str, Any]:
    if obj is None:
        return {}

    if isinstance(obj, dict):
        return dict(obj)

    if is_dataclass(obj):
        return asdict(obj)

    dict_method = getattr(obj, "dict", None)
    if callable(dict_method):
        return dict_method()

    return {k: v for k, v in vars(obj).items() if not k.startswith("_")}


def build_rows_html(lines: Iterable[Any]) -> str:
    if not lines:
        return ""

    html_rows: List[str] = []
    for index, line in enumerate(lines, start=1):
        d = _obj_to_dict(line)

        item_no_raw = d.get("article_number") or d.get("item_no") or d.get("article_ref") or str(index)
        desc_raw = d.get("description") or d.get("label") or ""

        quantity = d.get("quantity")
        if quantity is None:
            quantity = d.get("qty", 0)

        unit_price = d.get("unit_price") or d.get("unit_price_sek") or d.get("price_per_unit") or 0

        line_total = d.get("line_total") or d.get("line_total_sek") or d.get("total")
        if line_total is None:
            try:
                line_total = float(quantity or 0) * float(unit_price or 0)
            except Exception:
                line_total = 0

        try:
            quantity_str = f"{float(quantity):.2f}".replace(".", ",")
        except Exception:
            quantity_str = _h(quantity)

        row_html = (
            "<tr>"
            f'<td class="col-artnr">{_h(item_no_raw)}</td>'
            f'<td class="col-benamning">{_h(desc_raw)}</td>'
            f'<td class="col-levant">{quantity_str}</td>'
            f'<td class="col-apris">{_format_currency(unit_price)}</td>'
            f'<td class="col-summa">{_format_currency(line_total)}</td>'
            "</tr>"
        )
        html_rows.append(row_html)

    return "\n          ".join(html_rows)


def _parse_date_any(s: str) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None

    if s.endswith("Z"):
        s = s[:-1]

    candidates = [
        ("%Y-%m-%d", 10),
        ("%Y-%m-%d %H:%M:%S", 19),
        ("%Y-%m-%dT%H:%M:%S", 19),
        ("%Y-%m-%dT%H:%M:%S.%f", None),
    ]

    for fmt, n in candidates:
        try:
            ss = s if n is None else s[:n]
            return datetime.strptime(ss, fmt)
        except Exception:
            continue
    return None


def build_context_from_quote(
    quote: Any,
    company_settings: Any,
    *,
    document_title: str = "Offert",
) -> Dict[str, str]:
    q = _obj_to_dict(quote)
    c = _obj_to_dict(company_settings)

    document_number = q.get("number") or q.get("quote_number") or q.get("id") or ""
    document_date = q.get("created_date_str") or q.get("created_at_str") or q.get("created_at") or q.get("date") or ""
    if not str(document_date).strip():
        document_date = date.today().strftime("%Y-%m-%d")

    ocr_number = q.get("ocr") or document_number

    customer_number = q.get("customer_number") or q.get("customer_id") or ""

    cust_obj = q.get("customer") or {}
    if not isinstance(cust_obj, dict):
        cust_obj = {}

    customer_name_full = str(cust_obj.get("name") or q.get("customer_name") or "").strip()
    customer_address_line1 = str(cust_obj.get("address") or "").strip()
    customer_postcode = str(cust_obj.get("postcode") or "").strip()
    customer_city = str(cust_obj.get("city") or "").strip()
    customer_postcode_city = " ".join([p for p in [customer_postcode, customer_city] if p]).strip()
    customer_country = str(cust_obj.get("country") or "").strip()

    customer_orgnr = str(cust_obj.get("orgnr") or "").strip()
    reverse_charge = bool(cust_obj.get("reverse_charge") or False)

    customer_vat_number = q.get("customer_vat_number") or q.get("customer_vat") or ""
    auto_vat = ""
    if customer_orgnr:
        digits = "".join(ch for ch in customer_orgnr if ch.isdigit())
        if len(digits) == 10:
            auto_vat = f"SE{digits}01"

    vat_to_show = str(customer_vat_number).strip() or auto_vat
    customer_vat_block = ""
    if vat_to_show:
        customer_vat_block = f"<h4>Ert VAT-nummer</h4><p>{_h(vat_to_show)}</p>"

    our_reference = q.get("our_reference") or q.get("salesperson") or c.get("contact_person") or ""
    payment_terms = q.get("payment_terms_label") or q.get("payment_terms") or c.get("payment_terms") or ""
    late_interest = q.get("late_interest_label") or q.get("late_interest") or c.get("late_interest") or ""

    due_date = q.get("due_date") or ""
    if not str(due_date).strip():
        import re
        m = re.search(r"(\d+)", str(payment_terms))
        days = int(m.group(1)) if m else 0
        d0 = _parse_date_any(str(document_date))
        if d0 and days > 0:
            due_date = (d0 + timedelta(days=days)).strftime("%Y-%m-%d")

    company_name = c.get("company_name") or c.get("name") or ""
    company_address_line1 = c.get("address") or c.get("address_line1") or ""
    company_postcode = c.get("postcode") or c.get("zip_code") or ""
    company_city = c.get("city") or ""
    company_country = c.get("country") or "Sverige"
    company_phone = c.get("phone") or ""
    company_email = c.get("email") or ""
    company_bankgiro = c.get("bankgiro") or ""
    company_iban = c.get("iban") or ""
    company_bic = c.get("bic") or c.get("swift") or ""
    company_org_number = c.get("org_number") or c.get("organization_number") or ""
    company_f_tax_text = c.get("f_tax_text") or "Ja"
    company_logo_url = c.get("logo_url") or ""

    lines = q.get("lines") or q.get("items") or []
    rows_html = build_rows_html(lines)

    vat_percent_value = float(q.get("vat_percent") or 25)
    ex_vat_raw = q.get("total_ex_vat") or q.get("total_sek") or q.get("subtotal_sek") or 0

    inc_vat_raw = q.get("total_inc_vat") or q.get("total_incl_vat")
    if inc_vat_raw is None:
        try:
            inc_vat_raw = float(ex_vat_raw) * (1.0 + vat_percent_value / 100.0)
        except Exception:
            inc_vat_raw = ex_vat_raw

    vat_raw = q.get("vat_amount")
    if vat_raw is None:
        try:
            vat_raw = float(inc_vat_raw) - float(ex_vat_raw)
        except Exception:
            vat_raw = 0

    total_ex_vat = _format_currency(ex_vat_raw)
    vat_percent = str(int(vat_percent_value) if vat_percent_value.is_integer() else vat_percent_value)
    vat_amount = _format_currency(vat_raw)
    total_inc_vat = _format_currency(inc_vat_raw)

    note_text_raw = q.get("summary") or q.get("note") or q.get("description") or "Diverse elarbeten enligt överenskommelse."
    note_text = _h(note_text_raw)

    context: Dict[str, str] = {
        "document_title": _h(document_title),
        "document_number": _h(document_number),
        "document_date": _h(document_date),
        "ocr_number": _h(ocr_number),

        "customer_number": _h(customer_number),
        "customer_orgnr": _h(customer_orgnr),
        "customer_vat_number": _h(customer_vat_number),
        "customer_vat_block": str(customer_vat_block),
        "customer_vat_row": f"<tr><td>Ert VAT-nummer</td><td>{_h(vat_to_show)}</td></tr>" if vat_to_show else "",

        "customer_name_full": _h(customer_name_full),
        "customer_address_line1": _h(customer_address_line1),
        "customer_postcode_city": _h(customer_postcode_city),
        "customer_country": _h(customer_country),

        "our_reference": _h(our_reference),
        "payment_terms": _h(payment_terms),
        "due_date": _h(due_date),
        "late_interest": _h(late_interest),

        "company_logo_url": _h(company_logo_url),
        "company_name": _h(company_name),
        "company_address_line1": _h(company_address_line1),
        "company_postcode": _h(company_postcode),
        "company_city": _h(company_city),
        "company_country": _h(company_country),
        "company_phone": _h(company_phone),
        "company_email": _h(company_email),
        "company_bankgiro": _h(company_bankgiro),
        "company_iban": _h(company_iban),
        "company_bic": _h(company_bic),
        "company_org_number": _h(company_org_number),
        "company_f_tax_text": _h(company_f_tax_text),

        "rows_html": rows_html,

        "total_ex_vat": total_ex_vat,
        "vat_percent": _h(vat_percent),
        "vat_amount": vat_amount,
        "total_inc_vat": total_inc_vat,

        "note_text": note_text,
        "reverse_charge_notice": _h("Omvänd betalningsskyldighet") if reverse_charge else "",
        "total_display": total_ex_vat if reverse_charge else total_inc_vat,
        "payable_display": total_ex_vat if reverse_charge else total_inc_vat,
    }

    return context


def render_quote_html(context: Dict[str, Any]) -> str:
    html = TEMPLATE_PATH.read_text(encoding="utf-8")

    for key, value in context.items():
        html = html.replace(f"[[{key}]]", str(value))

    import re
    html = re.sub(r"\[\[[a-zA-Z0-9_]+\]\]", "", html)
    return html
