from typing import Tuple, Dict, Any
from sqlmodel import Session, select

from src.server.schemas.quote import QuoteDraftIn, QuoteDraftOut
from src.server.models import Customer, Quote, QuoteLine

def compute_subtotals(payload: QuoteDraftIn) -> Tuple[float, float, float]:
    subtotal = sum(l.qty * l.unit_price_sek for l in payload.lines)
    work_sum = sum(l.qty * l.unit_price_sek for l in payload.lines if l.kind.lower() == "work")
    rot = 0.30 * work_sum if payload.apply_rot else 0.0
    total = max(subtotal - rot, 0.0)
    return subtotal, rot, total

def make_draft(payload: QuoteDraftIn) -> QuoteDraftOut:
    subtotal, rot, total = compute_subtotals(payload)
    title = f"Preliminär offert för {payload.customer_name}"
    return QuoteDraftOut(
        title=title,
        subtotal_sek=round(subtotal, 2),
        rot_discount_sek=round(rot, 2),
        total_sek=round(total, 2),
        lines=payload.lines,
    )

def _get_or_create_customer(session: Session, name: str, email: str | None) -> Customer:
    if email:
        existing = session.exec(select(Customer).where(Customer.email == email)).first()
        if existing:
            if name and existing.name != name:
                existing.name = name
                session.add(existing)
            return existing
    existing = session.exec(select(Customer).where(Customer.name == name)).first()
    if existing:
        return existing
    cust = Customer(name=name, email=email or None)
    session.add(cust)
    session.flush()
    return cust

def create_quote(session: Session, payload: QuoteDraftIn) -> Dict[str, Any]:
    subtotal, rot, total = compute_subtotals(payload)
    customer = _get_or_create_customer(session, payload.customer_name, payload.customer_email)

    quote = Quote(
        customer_id=customer.id,
        title=f"Preliminär offert för {payload.customer_name}",
        subtotal_sek=round(subtotal, 2),
        rot_discount_sek=round(rot, 2),
        total_sek=round(total, 2),
    )
    session.add(quote)
    session.flush()

    for l in payload.lines:
        ql = QuoteLine(
            quote_id=quote.id,
            kind=l.kind,
            ref=l.ref,
            description=l.description,
            qty=l.qty,
            unit_price_sek=l.unit_price_sek,
            line_total_sek=l.qty * l.unit_price_sek,
        )
        session.add(ql)

    session.commit()
    session.refresh(quote)

    return {
        "id": quote.id,
        "title": quote.title,
        "subtotal_sek": quote.subtotal_sek,
        "rot_discount_sek": quote.rot_discount_sek,
        "total_sek": quote.total_sek,
    }


