# 6) src/server/models/work_item.py
from sqlmodel import SQLModel, Field
from typing import Optional

class WorkItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    hours: float
    hourly_rate_sek: float

