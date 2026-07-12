from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import BIGINT, DATE, JSON, NUMERIC, TEXT, TIMESTAMP, VARCHAR, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base


class Client(Base):
    __tablename__ = 'clients'

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    email: Mapped[str] = mapped_column(VARCHAR(255), nullable=False, unique=True)
    phone: Mapped[Optional[str]] = mapped_column(VARCHAR(20), nullable=True)
    address: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    deals: Mapped[list['Deal']] = relationship('Deal', back_populates='client')
    kpis: Mapped[list['KPI']] = relationship('KPI', back_populates='client', foreign_keys='KPI.client_id')

    def __repr__(self) -> str:
        return f'<Client id={self.id} name={self.name}>'


class Deal(Base):
    __tablename__ = 'deals'
    __table_args__ = (
        Index('deals_client_id_idx', 'client_id'),
        Index('deals_status_idx', 'status'),
        Index('deals_expected_close_idx', 'expected_close_date'),
        Index('deals_created_at_idx', 'created_at'),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(BIGINT, ForeignKey('clients.id'), nullable=False)
    title: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    value: Mapped[Optional[Decimal]] = mapped_column(NUMERIC(precision=12, scale=2), nullable=True)
    status: Mapped[Optional[str]] = mapped_column(VARCHAR(50), nullable=True)
    expected_close_date: Mapped[Optional[datetime]] = mapped_column(DATE, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    client: Mapped[Client] = relationship('Client', back_populates='deals')
    followups: Mapped[list['Followup']] = relationship('Followup', back_populates='deal')
    projects: Mapped[list['Project']] = relationship('Project', back_populates='deal')
    kpis: Mapped[list['KPI']] = relationship('KPI', back_populates='deal', foreign_keys='KPI.deal_id')

    def __repr__(self) -> str:
        return f'<Deal id={self.id} title={self.title}>'


class Followup(Base):
    __tablename__ = 'followups'
    __table_args__ = (
        Index('followups_deal_id_idx', 'deal_id'),
        Index('followups_scheduled_at_idx', 'scheduled_at'),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    deal_id: Mapped[int] = mapped_column(BIGINT, ForeignKey('deals.id'), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    deal: Mapped[Deal] = relationship('Deal', back_populates='followups')

    def __repr__(self) -> str:
        return f'<Followup id={self.id} deal_id={self.deal_id}>'


class Project(Base):
    __tablename__ = 'projects'
    __table_args__ = (
        Index('projects_deal_id_idx', 'deal_id'),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    deal_id: Mapped[int] = mapped_column(BIGINT, ForeignKey('deals.id'), nullable=False)
    name: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    status: Mapped[Optional[str]] = mapped_column(VARCHAR(50), nullable=True)
    budget: Mapped[Optional[Decimal]] = mapped_column(NUMERIC(precision=12, scale=2), nullable=True)
    spent: Mapped[Optional[Decimal]] = mapped_column(NUMERIC(precision=12, scale=2), default=Decimal('0'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    deal: Mapped[Deal] = relationship('Deal', back_populates='projects')

    def __repr__(self) -> str:
        return f'<Project id={self.id} name={self.name}>'


class KPI(Base):
    __tablename__ = 'kpis'
    __table_args__ = (
        Index('kpis_client_id_idx', 'client_id'),
        Index('kpis_deal_id_idx', 'deal_id'),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    client_id: Mapped[Optional[int]] = mapped_column(BIGINT, ForeignKey('clients.id'), nullable=True)
    deal_id: Mapped[Optional[int]] = mapped_column(BIGINT, ForeignKey('deals.id'), nullable=True)
    metric_name: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    metric_value: Mapped[Optional[Decimal]] = mapped_column(NUMERIC(precision=12, scale=4), nullable=True)
    period: Mapped[Optional[str]] = mapped_column(VARCHAR(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    client: Mapped[Optional[Client]] = relationship('Client', back_populates='kpis', foreign_keys=[client_id])
    deal: Mapped[Optional[Deal]] = relationship('Deal', back_populates='kpis', foreign_keys=[deal_id])

    def __repr__(self) -> str:
        return f'<KPI id={self.id} metric_name={self.metric_name}>'
