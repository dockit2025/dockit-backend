# 9) src/server/schemas/common.py
from typing import Optional
from pydantic import BaseModel

class Message(BaseModel):
    message: str
    git_sha: Optional[str] = None
    build_utc: Optional[str] = None
