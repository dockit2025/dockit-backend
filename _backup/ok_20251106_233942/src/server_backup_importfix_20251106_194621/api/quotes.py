from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from src.server.schemas.quote import QuoteDraftIn, QuoteDraftOut
from src.server.services.quote_service import make_draft, create_quote
from src.server.db.session import get_session
from src.server.models import Quote, QuoteLine, Customer

router = APIRouter(prefix="/quotes", tags=["quotes"])

@router.post("/draft", response_model=QuoteDraftOut)
def create_draft(payload: QuoteDraftIn):
    return make_draft(payload)

@router.post("", summary="Spara offert och få ID")
def save_quote(payload: QuoteDraftIn, session: Session = Depends(get_session)):
    return create_quote(session, payload)

@router.get("", summary="Lista alla offerter")
@router.get("/", summary="Lista alla offerter (trailing slash)")
def list_quotes(skip: int = 0, limit: int = 50, session: Session = Depends(get_session)):
    q = session.exec(select(Quote).offset(skip).limit(limit)).all()
    out = []
    for it in q:
        cust_name = None
        if it.customer_id:
            c = session.get(Customer, it.customer_id)
            cust_name = c.name if c else None
        out.append({
            "id": it.id,
            "title": it.title,
            "customer_name": cust_name,
            "subtotal_sek": it.subtotal_sek,
            "rot_discount_sek": it.rot_discount_sek,
            "total_sek": it.total_sek,
        })
    return out

@router.get("/list", summary="Lista alla offerter (statisk path)")
def list_quotes_alias(skip: int = 0, limit: int = 50, session: Session = Depends(get_session)):
    return list_quotes(skip=skip, limit=limit, session=session)

@router.get("/{quote_id}", summary="Hämta sparad offert med rader")
def get_quote(quote_id: int, session: Session = Depends(get_session)):
    quote = session.get(Quote, quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Offerterna hittades inte")

    customer_name = None
    if quote.customer_id:
        cust = session.get(Customer, quote.customer_id)
        customer_name = cust.name if cust else None

    lines = session.exec(select(QuoteLine).where(QuoteLine.quote_id == quote_id)).all()
    return {
        "id": quote.id,
        "title": quote.title,
        "customer_name": customer_name,
        "subtotal_sek": quote.subtotal_sek,
        "rot_discount_sek": quote.rot_discount_sek,
        "total_sek": quote.total_sek,
        "lines": [
            {
                "kind": l.kind,
                "ref": l.ref,
                "description": l.description,
                "qty": l.qty,
                "unit_price_sek": l.unit_price_sek,
                "line_total_sek": l.line_total_sek,
            }
            for l in lines
        ],
    }

