# 4) src/server/models/customer.py
from sqlmodel import SQLModel, Field
from typing import Optional

class Customer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    orgnr: Optional[str] = None

