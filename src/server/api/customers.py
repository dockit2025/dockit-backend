from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from src.server.api.quotes import verify_api_key
from src.server.db.session import get_session
from src.server.models import Customer


router = APIRouter(
    prefix="/customers",
    tags=["customers"],
    dependencies=[Depends(verify_api_key)],
)


class CustomerIn(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    orgnr: Optional[str] = None

    # Frontend-fält (accepteras men lagras inte än)
    postcode: Optional[str] = None
    city: Optional[str] = None


class CustomerUpdateIn(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    orgnr: Optional[str] = None

    postcode: Optional[str] = None
    city: Optional[str] = None


def _serialize_customer(c: Customer) -> Dict[str, Any]:
    return {
        "id": c.id,
        "name": c.name,
        "email": c.email,
        "phone": c.phone,
        "address": c.address,
        "orgnr": c.orgnr,
        "postcode": None,
        "city": None,
    }


@router.get("")
@router.get("/", include_in_schema=False)
def list_customers(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    session: Session = Depends(get_session),
) -> List[Dict[str, Any]]:
    rows = session.exec(select(Customer).offset(skip).limit(limit)).all()
    return [_serialize_customer(c) for c in rows]


@router.get("/{customer_id}")
def get_customer(customer_id: int, session: Session = Depends(get_session)) -> Dict[str, Any]:
    c = session.get(Customer, customer_id)
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")
    return _serialize_customer(c)


@router.post("")
@router.post("/", include_in_schema=False)
def create_customer(payload: CustomerIn, session: Session = Depends(get_session)) -> Dict[str, Any]:
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    c = Customer(
        name=name,
        email=(payload.email or None),
        phone=(payload.phone or None),
        address=(payload.address or None),
        orgnr=(payload.orgnr or None),
    )
    session.add(c)
    session.commit()
    session.refresh(c)
    return _serialize_customer(c)


@router.put("/{customer_id}")
def update_customer(customer_id: int, payload: CustomerUpdateIn, session: Session = Depends(get_session)) -> Dict[str, Any]:
    c = session.get(Customer, customer_id)
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")

    if payload.name is not None:
        name = (payload.name or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="name cannot be empty")
        c.name = name

    if payload.email is not None:
        c.email = payload.email or None
    if payload.phone is not None:
        c.phone = payload.phone or None
    if payload.address is not None:
        c.address = payload.address or None
    if payload.orgnr is not None:
        c.orgnr = payload.orgnr or None

    session.add(c)
    session.commit()
    session.refresh(c)
    return _serialize_customer(c)
