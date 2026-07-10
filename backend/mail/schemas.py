from datetime import datetime

from pydantic import BaseModel


class MailConnectResponse(BaseModel):
    authorization_url: str


class MailStatusResponse(BaseModel):
    connected: bool
    email_address: str | None = None
    connected_at: datetime | None = None
