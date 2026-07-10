from datetime import datetime

from pydantic import BaseModel


class GContactsConnectResponse(BaseModel):
    authorization_url: str


class GContactsStatusResponse(BaseModel):
    connected: bool
    account_label: str | None = None
    connected_at: datetime | None = None
