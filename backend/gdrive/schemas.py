from datetime import datetime

from pydantic import BaseModel


class GDriveConnectResponse(BaseModel):
    authorization_url: str


class GDriveStatusResponse(BaseModel):
    connected: bool
    account_label: str | None = None
    connected_at: datetime | None = None
