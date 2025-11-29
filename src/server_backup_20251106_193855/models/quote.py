# 7) src/server/models/quote.py
from sqlmodel import SQLModel, Field
from typing import Optional

class Quote(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    customer_id: Optional[int] = Field(default=None, foreign_key="customer.id")
    title: str
    subtotal_sek: float = 0.0
    rot_discount_sek: float = 0.0
    total_sek: float = 0.0

class QuoteLine(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    quote_id: int = Field(foreign_key="quote.id")
    kind: str                  # "work" | "material"
    ref: Optional[str] = None  # t.ex. SKU
    description: str
    qty: float
    unit_price_sek: float
    line_total_sek: float

