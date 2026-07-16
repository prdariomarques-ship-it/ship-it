from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class ClientBase(BaseModel):
    name: str = Field(
        ..., min_length=1, max_length=255, description="Client business name"
    )
    email: EmailStr = Field(..., description="Client contact email")
    phone: Optional[str] = Field(None, max_length=20, description="Client phone number")
    address: Optional[dict] = Field(
        None, description="Full address object {street, city, state, country, zip}"
    )


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    address: Optional[dict] = None


class ClientRead(ClientBase):
    id: int
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DealBase(BaseModel):
    client_id: int = Field(..., description="Reference to clients.id")
    title: str = Field(
        ..., min_length=1, max_length=255, description="Deal/opportunity title"
    )
    value: Optional[Decimal] = Field(
        None, decimal_places=2, description="Deal value in currency"
    )
    status: Optional[str] = Field(
        None, max_length=50, description="Status: open, closed_won, closed_lost"
    )
    expected_close_date: Optional[date] = Field(
        None, description="Expected close date for forecasting"
    )


class DealCreate(DealBase):
    pass


class DealUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    value: Optional[Decimal] = Field(None, decimal_places=2)
    status: Optional[str] = Field(None, max_length=50)
    expected_close_date: Optional[date] = None


class DealRead(DealBase):
    id: int
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class FollowupBase(BaseModel):
    deal_id: int = Field(..., description="Reference to deals.id")
    scheduled_at: datetime = Field(
        ..., description="When followup is scheduled (for jobs)"
    )
    completed_at: Optional[datetime] = Field(
        None, description="When followup was actually completed"
    )
    notes: Optional[str] = Field(None, description="Internal notes about followup")


class FollowupCreate(FollowupBase):
    pass


class FollowupUpdate(BaseModel):
    scheduled_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    notes: Optional[str] = None


class FollowupRead(FollowupBase):
    id: int
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProjectBase(BaseModel):
    deal_id: int = Field(..., description="Reference to deals.id")
    name: str = Field(
        ..., min_length=1, max_length=255, description="Project name/title"
    )
    status: Optional[str] = Field(
        None, max_length=50, description="Status: planning, active, completed, on_hold"
    )
    budget: Optional[Decimal] = Field(
        None, decimal_places=2, description="Project budget allocation"
    )
    spent: Optional[Decimal] = Field(
        None, decimal_places=2, description="Amount spent so far"
    )


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    status: Optional[str] = Field(None, max_length=50)
    budget: Optional[Decimal] = Field(None, decimal_places=2)
    spent: Optional[Decimal] = Field(None, decimal_places=2)


class ProjectRead(ProjectBase):
    id: int
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class KPIBase(BaseModel):
    client_id: Optional[int] = Field(
        None, description="Reference to clients.id (optional)"
    )
    deal_id: Optional[int] = Field(None, description="Reference to deals.id (optional)")
    metric_name: str = Field(
        ..., min_length=1, max_length=255, description="KPI metric name"
    )
    metric_value: Optional[Decimal] = Field(
        None, decimal_places=4, description="Metric numeric value"
    )
    period: Optional[str] = Field(
        None, max_length=50, description="Period label (Q3 2026, 2026, YTD)"
    )


class KPICreate(KPIBase):
    pass


class KPIUpdate(BaseModel):
    metric_name: Optional[str] = Field(None, min_length=1, max_length=255)
    metric_value: Optional[Decimal] = Field(None, decimal_places=4)
    period: Optional[str] = Field(None, max_length=50)


class KPIRead(KPIBase):
    id: int
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None

    class Config:
        from_attributes = True
