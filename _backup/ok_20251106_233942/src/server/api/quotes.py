from typing import List, Optional
from src.services.quote_service import make_draft, create_quote

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select

from src.server.db.session import get_session
from src.server.models import Quote, QuoteLine, Customer

from src.server.schemas.quote import QuoteDraftIn  # vi använder in-modellen

router = APIRouter(prefix="/quotes", tags=["quotes"])

# ---------- Hjälpare ----------

def _serialize_quote(q: Quote, session: Session) -> dict:
    cust_name: Optional[str] = None
    if getattr(q, "customer_id", None) is not None:
        cust = session.get(Customer, q.customer_id)
        cust_name = cust.name if cust else None

    lines = (
        session.exec(
            select(QuoteLine).where(QuoteLine.quote_id == q.id)
        ).scalars().all()
    )

    return {
        "id": q.id,
        "title": getattr(q, "title", f"Offert #{q.id}"),
        "customer_name": cust_name,
        "subtotal_sek": float(getattr(q, "subtotal_sek", 0) or 0),
        "rot_discount_sek": float(getattr(q, "rot_discount_sek", 0) or 0),
        "total_sek": float(getattr(q, "total_sek", 0) or 0),
        "lines": [
            {
                "kind": l.kind,
                "ref": l.ref,
                "description": l.description,
                "qty": float(l.qty),
                "unit_price_sek": float(l.unit_price_sek),
                "line_total_sek": float(l.line_total_sek),
            }
            for l in lines
        ],
    }

def _list_quotes_impl(skip: int, limit: int, session: Session) -> List[dict]:
    rows = (
        session.exec(
            select(Quote).offset(skip).limit(limit)
        ).scalars().all()
    )
    out: List[dict] = []
    for q in rows:
        out.append(_serialize_quote(q, session))
    return out

# ---------- LISTA (måste ligga före parameterrutten) ----------

@router.get("", summary="Lista alla offerter")
@router.get("/", include_in_schema=False)
def list_quotes(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
):
    return _list_quotes_impl(skip=skip, limit=limit, session=session)

@router.get("/__list", include_in_schema=False)
def list_quotes_failsafe(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
):
    return _list_quotes_impl(skip=skip, limit=limit, session=session)

# ---------- SKAPA (POST) ----------

@router.post("/draft", summary="Beräkna en offert (utkast, ej spara)")
def draft_quote(payload: QuoteDraftIn, session: Session = Depends(get_session)):
    """
    Använder services.make_draft för att räkna fram totaller/ROT på ett utkast.
    Returnerar samma struktur som frontend använder i sin preview.
    """
    return make_draft(payload=payload, session=session)

@router.post("", summary="Spara en offert")
def create_quote_endpoint(payload: QuoteDraftIn, session: Session = Depends(get_session)):
    """
    Skapar en offert och dess rader i databasen via services.create_quote.
    Returnerar den sparade offerten i samma struktur som GET /quotes/{id}.
    """
    result = create_quote(payload=payload, session=session)
    q = (result if hasattr(result, "id") else session.get(Quote, result))
    if not q:
        raise HTTPException(status_code=500, detail="Offerten kunde inte hämtas efter skapande")
    return _serialize_quote(q, session)

# ---------- HÄMTA EN (läggs sist) ----------

@router.get("/{quote_id}", summary="Hämta sparad offert med rader")
def get_quote(quote_id: int, session: Session = Depends(get_session)):
    q = session.get(Quote, quote_id)
    if not q:
        raise HTTPException(status_code=404, detail="Offerten hittades inte")
    return _serialize_quote(q, session)







