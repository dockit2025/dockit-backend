# 5) src/server/models/material.py
from sqlmodel import SQLModel, Field
from typing import Optional

class Material(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    sku: str
    name: str
    unit_price_sek: float
    unit: str = "st"

