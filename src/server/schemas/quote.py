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

class MaterialItemIn(BaseModel):
    """
    En rad material i material-läget.
    Exempel:
      - 10m 3x1,5
      - 15m 20mm rör
      - 3 vägguttag
    """
    raw: str                 # originaltexten, t.ex. "10m 3x1,5"
    qty: float               # antal, t.ex. 10
    unit: str                # enhet, t.ex. "m" eller "st"
    material_ref: str        # tolkad materialtyp, t.ex. "KABEL-3G1.5", "VP-ROR-20", "VEGGUTTAG"

    # Dessa sätts/justeras av UI:t efter att elektrikern valt i dropdown:
    work_type: Optional[str] = None      # t.ex. "socket", "lighting", "group_centre"
    environment: Optional[str] = None    # t.ex. "infalt", "utanpa", "utomhus"


class MaterialDraftIn(BaseModel):
    """
    Payload till /quotes/material-draft.
    Hantverkaren anger bara materialrader – inget job_summary.
    """
    customer_name: str
    customer_email: Optional[str] = None

    apply_rot: bool = True               # ROT bara på arbete (som vanligt)
    hourly_rate: Optional[float] = None  # om None → default-timpris

    # Lista med materialrader som redan är tolkade av material_list_parser
    material_items: List[MaterialItemIn]
