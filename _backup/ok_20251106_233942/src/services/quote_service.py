from typing import Dict, Any
from sqlmodel import Session, select
from src.server.models import Quote, QuoteLine, Customer
from src.server.schemas.quote import QuoteDraftIn

def _calc_totals(payload: QuoteDraftIn) -> Dict[str, float]:
    subtotal = 0.0
    for l in payload.lines:
        qty = float(getattr(l, "qty", 0) or 0)
        price = float(getattr(l, "unit_price_sek", 0) or 0)
        subtotal += qty * price
    rot_discount = 0.0  # placeholder för ROT
    total = subtotal - rot_discount
    return {"subtotal": subtotal, "rot_discount": rot_discount, "total": total}

def make_draft(*, payload: QuoteDraftIn, session: Session) -> Dict[str, Any]:
    totals = _calc_totals(payload)
    out_lines = []
    for l in payload.lines:
        qty = float(getattr(l, "qty", 0) or 0)
        price = float(getattr(l, "unit_price_sek", 0) or 0)
        out_lines.append({
            "kind": getattr(l, "kind", None),
            "ref": getattr(l, "ref", None),
            "description": getattr(l, "description", None),
            "qty": qty,
            "unit_price_sek": price,
            "line_total_sek": qty * price,
        })
    return {
        "id": None,
        "title": f"Preliminär offert för {getattr(payload, 'customer_name', '')}".strip(),
        "customer_name": getattr(payload, "customer_name", None),
        "subtotal_sek": totals["subtotal"],
        "rot_discount_sek": totals["rot_discount"],
        "total_sek": totals["total"],
        "lines": out_lines,
    }

def create_quote(*, payload: QuoteDraftIn, session: Session) -> Quote:
    # Hämta/Skapa kund
    email = getattr(payload, "customer_email", None)
    name  = getattr(payload, "customer_name", None)

    cust = None
    if email:
        cust = session.exec(select(Customer).where(Customer.email == email)).first()
    if not cust and name:
        cust = session.exec(select(Customer).where(Customer.name == name)).first()
    if not cust:
        cust = Customer(name=name, email=email)
        session.add(cust)
        session.commit()
        session.refresh(cust)

    totals = _calc_totals(payload)

    # Skapa offert
    quote = Quote(
        customer_id=cust.id if cust else None,
        title=f"Preliminär offert för {name}" if name else "Preliminär offert",
        subtotal_sek=totals["subtotal"],
        rot_discount_sek=totals["rot_discount"],
        total_sek=totals["total"],
    )
    session.add(quote)
    session.commit()
    session.refresh(quote)

    # Skapa rader
    for l in payload.lines:
        qty = float(getattr(l, "qty", 0) or 0)
        price = float(getattr(l, "unit_price_sek", 0) or 0)
        ql = QuoteLine(
            quote_id=quote.id,
            kind=getattr(l, "kind", None),
            ref=getattr(l, "ref", None),
            description=getattr(l, "description", None),
            qty=qty,
            unit_price_sek=price,
            line_total_sek=qty * price,
        )
        session.add(ql)

    session.commit()
    return quote
