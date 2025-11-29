from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select

from src.services.quote_service import make_draft, create_quote, material_draft
from src.services.favorites import register_favorite_article, list_favorites_for_customer
from src.services.material_suggestions import get_material_suggestions

from src.server.db.session import get_session
from src.server.models import Quote, QuoteLine, Customer
from src.server.schemas.quote import QuoteDraftIn, MaterialDraftIn  # vi använder in-modellen
from material_list_parser import parse_material_text as _parse_material_text

API_KEY_HEADER_NAME = "X-DOCKIT-API-KEY"
API_KEY_VALUE = "dockit-material-beta-123"


def verify_api_key(x_dockit_api_key: str = Header(None)) -> None:
    """
    Enkel API-nyckelkontroll för betatester.

    Alla anrop mot /quotes-ändpunkter måste skicka:
      X-DOCKIT-API-KEY: dockit-material-beta-123
    """
    if x_dockit_api_key != API_KEY_VALUE:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


router = APIRouter(prefix="/quotes", tags=["quotes"], dependencies=[Depends(verify_api_key)])


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


# ---------- FAVORITARTIKLAR (POST) ----------


class FavoriteMaterialIn(BaseModel):
    """
    Payload för att registrera en favoritartikel för en kund + material_ref.

    Exempel på JSON:
    {
      "customer_id": "123",              # valfritt
      "customer_email": "kund@ex.se",    # gärna denna
      "customer_name": "Kund AB",        # fallback
      "material_ref": "DIMMER-UNIV",
      "article_number": "0000120"
    }
    """
    customer_id: Optional[str] = None
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None
    material_ref: str
    article_number: str


@router.post("/favorite-material", summary="Registrera favoritartikel för kund/material-ref")
def set_favorite_material(payload: FavoriteMaterialIn):
    """
    Registrerar/uppdaterar en favoritartikel för en viss kund + material_ref.

    Frontend kan anropa detta när elektrikern manuellt byter artikel i offerten,
    t.ex. väljer en annan dimmer än standard.
    """
    cust_key = (
        payload.customer_id
        or payload.customer_email
        or payload.customer_name
    )

    if not cust_key:
        raise HTTPException(
            status_code=400,
            detail="customer_id, customer_email eller customer_name måste anges",
        )

    register_favorite_article(
        customer_id=cust_key,
        material_ref=payload.material_ref,
        article_number=payload.article_number,
    )

    return {
        "status": "ok",
        "customer_id": cust_key,
        "material_ref": payload.material_ref,
        "article_number": payload.article_number,
    }


# ---------- FAVORITARTIKLAR (GET) ----------


@router.get(
    "/favorite-materials",
    summary="Lista favoritartiklar för en kund",
)
def get_favorite_materials(
    customer_id: Optional[str] = Query(default=None),
    customer_email: Optional[str] = Query(default=None),
    customer_name: Optional[str] = Query(default=None),
):
    """
    Returnerar alla favoritartiklar för en kund.

    Du kan identifiera kund på tre sätt:
      - customer_id
      - customer_email
      - customer_name

    Exempel:
      GET /quotes/favorite-materials?customer_email=test@example.com
    """
    cust_key = customer_id or customer_email or customer_name
    if not cust_key:
        raise HTTPException(
            status_code=400,
            detail="customer_id, customer_email eller customer_name måste anges som query-parameter",
        )

    favorites = list_favorites_for_customer(cust_key)

    return {
        "customer_id": cust_key,
        "favorites": favorites,
    }


# ---------- MATERIAL-SUGGESTIONS (GET) ----------


@router.get(
    "/material-suggestions",
    summary="Få materialsförslag för kund + material_ref",
)
def material_suggestions(
    material_ref: str = Query(..., description="Materialreferens, t.ex. DIMMER-UNIV"),
    customer_id: Optional[str] = Query(default=None),
    customer_email: Optional[str] = Query(default=None),
    customer_name: Optional[str] = Query(default=None),
):
    """
    Returnerar en prioriterad lista med artikelförslag för en given kund + material_ref.

    Prioritet i svar:
      1) Kundens favorit (om finns)
      2) Global mapping i material_ref_map.json
      3) Direkt-användning av material_ref som artikelnummer (om prissatt)

    Exempel:
      GET /quotes/material-suggestions?customer_email=test@example.com&material_ref=DIMMER-UNIV
    """
    if not material_ref:
        raise HTTPException(status_code=400, detail="material_ref måste anges")

    cust_key = customer_id or customer_email or customer_name

    suggestions = get_material_suggestions(
        customer_id=cust_key,
        material_ref=material_ref,
    )

    return {
        "customer_id": cust_key,
        "material_ref": material_ref,
        "suggestions": suggestions,
    }


# ---------- HÄMTA EN (läggs sist) ----------


@router.post(
    "/material-draft",
    summary="Beräkna offert i material-läge (utkast, ej spara)",
)
def quote_material_draft(
    payload: MaterialDraftIn,
    session: Session = Depends(get_session),
):
    """
    Material-läge: tar emot redan tolkade materialrader (material_items)
    och bygger ett offertutkast baserat på material + work_profiles.
    """
    return material_draft(payload=payload, session=session)


@router.get("/{quote_id}", summary="Hämta sparad offert med rader")
def get_quote(quote_id: int, session: Session = Depends(get_session)):
    q = session.get(Quote, quote_id)
    if not q:
        raise HTTPException(status_code=404, detail="Offerten hittades inte")
    return _serialize_quote(q, session)


class MaterialParseIn(BaseModel):
    """
    Payload till /quotes/material-parse.
    Innehåller bara rå materialtext som ska tolkas till material_items.
    """
    text: str


@router.post(
    "/material-parse",
    summary="Tolkar materialtext till material_items",
)
def quote_material_parse(
    payload: MaterialParseIn,
):
    """
    Tar emot rå materialtext, t.ex.
      "10m 3x1,5, 15m 20mm rör, 3 vägguttag, 2 strömbrytare"
    och returnerar resultatet från material_list_parser.parse_material_text.
    """
    parsed = _parse_material_text(payload.text)
    return parsed




