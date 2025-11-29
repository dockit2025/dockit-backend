from fastapi import APIRouter, Depends
from sqlmodel import Session
from src.server.db import get_session
from src.services.quote_service import make_draft, create_quote
from src.server.schemas.quotes import QuoteCreate, QuoteDraftCreate, QuoteOut, QuoteDraftOut

router = APIRouter(prefix="/quotes", tags=["quotes"])

@router.post("/draft", response_model=QuoteDraftOut)
def post_draft(payload: QuoteDraftCreate, session: Session = Depends(get_session)):
    return make_draft(payload=payload, session=session)

@router.post("", response_model=QuoteOut)
def post_quote(payload: QuoteCreate, session: Session = Depends(get_session)):
    return create_quote(payload=payload, session=session)

