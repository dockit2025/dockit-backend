from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import SQLModel, Field
from sqlalchemy import UniqueConstraint


class MissingTaskSegment(SQLModel, table=True):
    """
    Aggregerad admin-kö för "missing task segments".
    Syfte:
      - funka i prod (DB-backed, inte fil i container)
      - kunna threshold-gata (min_count) innan man ens föreslår tasks
    """
    __tablename__ = "missing_task_segment"
    __table_args__ = (UniqueConstraint("segment_key"),)

    id: Optional[int] = Field(default=None, primary_key=True)

    # Normaliserad nyckel (lowercase, collapse whitespace)
    segment_key: str = Field(index=True)

    # Senaste "exempel" (för admin-läsbarhet)
    example: str = Field(default="")

    count: int = Field(default=1, index=True)

    first_seen_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
