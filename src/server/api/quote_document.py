from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from src.server.db.session import get_session
from src.server.models import Quote
from src.services.quote_document import build_context_from_quote, render_quote_html
from src.server.api.quotes import _get_company_settings, _serialize_quote  # återanvänd helpers

router = APIRouter(prefix="/quotes", tags=["quotes"])  # ingen API-nyckel

@router.get(
    "/{quote_id}/document",
    summary="Generera offertdokument (HTML) – ingen API-nyckel behövs",
)
def get_quote_document_noauth(
    quote_id: int,
    session: Session = Depends(get_session),
):
    q = session.get(Quote, quote_id)
    if not q:
        raise HTTPException(status_code=404, detail="Offerten hittades inte")

    company_settings = _get_company_settings()
    quote_data = _serialize_quote(q, session)  # innehåller rader + totals

    ctx = build_context_from_quote(
        quote=quote_data,
        company_settings=company_settings,
        document_title="Offert",
    )
    html = render_quote_html(ctx)

    return HTMLResponse(content=html)
