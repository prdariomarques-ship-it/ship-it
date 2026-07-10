from datetime import datetime

from pydantic import BaseModel


class GCalendarConnectResponse(BaseModel):
    authorization_url: str


class GCalendarStatusResponse(BaseModel):
    connected: bool
    account_label: str | None = None
    connected_at: datetime | None = None
