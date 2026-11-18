from datetime import datetime

from pydantic import BaseModel


class HealthResponse(BaseModel):
    ok: bool
    db: bool
    worker_last_seen: datetime | None
