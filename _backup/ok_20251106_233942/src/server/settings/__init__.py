# 10) src/server/schemas/quote.py
from pydantic import BaseModel
from typing import List, Optional

class QuoteLineIn(BaseModel):
    kind: str
    description: str
    qty: float
    unit_price_sek: float
    ref: Optional[str] = None

class QuoteDraftIn(BaseModel):
    customer_name: str
    customer_email: Optional[str] = None
    job_summary: str
    lines: List[QuoteLineIn]
    apply_rot: bool = True

class QuoteDraftOut(BaseModel):
    title: str
    subtotal_sek: float
    rot_discount_sek: float
    total_sek: float
    lines: List[QuoteLineIn]


