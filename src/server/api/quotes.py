from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Header
from sqlalchemy.orm import Session
from sqlalchemy import select
from pydantic import BaseModel

from src.services.quote_service import make_draft, create_quote, material_draft
from src.services.favorites import register_favorite_article, list_favorites_for_customer
from src.services.material_suggestions import get_material_suggestions

from src.server.db.session import get_session
from src.server.models import Quote, QuoteLine, Customer
from src.server.schemas.quote import QuoteDraftIn, MaterialDraftIn
from material_list_parser import parse_material_text as _parse_material_text


# ==============================
# API KEY
# ==============================

API_KEY_HEADER_NAME = "X-DOCKIT-API-KEY"
API_KEY_VALUE = "dockit-material-beta-123"


def verify_api_key(x_dockit_api_key: str = Header(None)) -> None:
    if x_dockit_api_key != API_KEY_VALUE:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


router = APIRouter(
    prefix="/quotes",
    tags=["quotes"],
    dependencies=[Depends(verify_api_key)],
)


# ==============================
# HELPERS
# ==============================

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
    return [_serialize_quote(q, session) for q in rows]


def _get_company_settings() -> dict:
    return {
        "company_name": "Dockit El AB",
        "address": "Exempelgatan 1",
        "address_line1": "Exempelgatan 1",
        "postcode": "414 00",
        "zip_code": "414 00",
        "city": "Göteborg",
        "country": "Sverige",
        "phone": "070-000 00 00",
        "email": "info@dockit.se",
        "bankgiro": "123-4567",
        "iban": "",
        "org_number": "5590-0000",
        "f_tax_text": "Ja",
        "logo_url": "/static/dockit-logo.png",
    }


# ==============================
# LISTA
# ==============================

@router.get("", summary="Lista alla offerter")
@router.get("/", include_in_schema=False)
def list_quotes(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
):
    return _list_quotes_impl(skip=skip, limit=limit, session=session)


# ==============================
# SKAPA & DRAFT
# ==============================

@router.post("/draft", summary="Beräkna offert (utkast)")
def draft_quote(payload: QuoteDraftIn, session: Session = Depends(get_session)):
    return make_draft(payload=payload, session=session)


@router.post("", summary="Spara offert")
def create_quote_endpoint(payload: QuoteDraftIn, session: Session = Depends(get_session)):
    result = create_quote(payload=payload, session=session)
    q = result if hasattr(result, "id") else session.get(Quote, result)
    if not q:
        raise HTTPException(status_code=500, detail="Offerten kunde inte hämtas efter skapande")
    return _serialize_quote(q, session)


# ==============================
# FAVORITER
# ==============================

class FavoriteMaterialIn(BaseModel):
    customer_id: Optional[str] = None
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None
    material_ref: str
    article_number: str


@router.post("/favorite-material")
def set_favorite_material(payload: FavoriteMaterialIn):
    cust_key = (
        payload.customer_id
        or payload.customer_email
        or payload.customer_name
    )
    if not cust_key:
        raise HTTPException(status_code=400, detail="customer-id or email required")

    register_favorite_article(
        customer_id=cust_key,
        material_ref=payload.material_ref,
        article_number=payload.article_number,
    )

    return {"status": "ok"}


@router.get("/favorite-materials")
def get_favorite_materials(
    customer_id: Optional[str] = Query(default=None),
    customer_email: Optional[str] = Query(default=None),
    customer_name: Optional[str] = Query(default=None),
):
    cust_key = customer_id or customer_email or customer_name
    if not cust_key:
        raise HTTPException(status_code=400, detail="customer-id or email required")

    return {
        "customer_id": cust_key,
        "favorites": list_favorites_for_customer(cust_key),
    }


# ==============================
# MATERIAL SUGGESTIONS
# ==============================

@router.get("/material-suggestions")
def material_suggestions(
    material_ref: str,
    customer_id: Optional[str] = None,
    customer_email: Optional[str] = None,
    customer_name: Optional[str] = None,
):
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


# ==============================
# MATERIAL DRAFT
# ==============================

@router.post("/material-draft")
def quote_material_draft(payload: MaterialDraftIn, session: Session = Depends(get_session)):
    return material_draft(payload=payload, session=session)


# ==============================
# MATERIAL PARSE
# ==============================

class MaterialParseIn(BaseModel):
    text: str
    customer_email: Optional[str] = None


@router.post("/material-parse")
def quote_material_parse(payload: MaterialParseIn):
    parsed = _parse_material_text(payload.text)
    items = parsed.get("items") or []

    enriched = []
    for item in items:
        ref = item.get("material_ref")
        raw = item.get("raw")
        parsed_core = item.get("parsed_core")
        qty = item.get("qty")
        unit = item.get("unit")

        # article lookup reused from pricing service
        from src.services.favorites import get_favorite_article
        from pathlib import Path
        import json

        def _load_material_ref_map():
            path = Path("knowledge/catalogs/material_ref_map.json")
            if not path.exists():
                return {}
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return {}

        def _load_price_catalog():
            path = Path("knowledge/catalogs/price_catalog.json")
            if not path.exists():
                return []
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return []

        # resolve article
        article_number = None
        if payload.customer_email:
            fav = get_favorite_article(payload.customer_email, ref)
            if fav:
                article_number = fav

        if not article_number:
            refmap = _load_material_ref_map()
            rawmap = refmap.get(ref) or refmap.get(str(ref).upper())
            if rawmap:
                article_number = rawmap

        article_name = ""
        unit_from_catalog = unit
        unit_price = 0

        if article_number:
            catalog = _load_price_catalog()
            for row in catalog:
                if str(row.get("artikelnummer")).strip() == str(article_number).strip():
                    article_name = row.get("benamning") or ""
                    unit_from_catalog = row.get("enhet") or "st"
                    unit_price = row.get("gn_pris") or 0
                    break

        enriched.append({
            "raw": raw,
            "parsed_core": parsed_core,
            "qty": qty,
            "unit": unit,
            "material_ref": ref,
            "article_number": article_number,
            "article_name": article_name,
            "unit_price": unit_price,
            "unit_from_catalog": unit_from_catalog,
        })

    return {
        "free_text": payload.text,
        "items": enriched,
    }


# ==============================
# GET SINGLE QUOTE
# ==============================

@router.get("/{quote_id}")
def get_quote(quote_id: int, session: Session = Depends(get_session)):
    q = session.get(Quote, quote_id)
    if not q:
        raise HTTPException(status_code=404, detail="Offerten hittades inte")
    return _serialize_quote(q, session)
