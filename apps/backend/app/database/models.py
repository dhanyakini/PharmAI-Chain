"""SQLAlchemy ORM models — UTC timestamps."""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class UserRole(str, enum.Enum):
    admin = "admin"
    viewer = "viewer"


class ShipmentStatus(str, enum.Enum):
    created = "created"
    in_transit = "in_transit"
    rerouted = "rerouted"
    compromised = "compromised"
    delivered = "delivered"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(256))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.viewer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shipment_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    cargo_type: Mapped[str] = mapped_column(String(128), default="insulin")
    origin_lat: Mapped[float] = mapped_column(Float)
    origin_lng: Mapped[float] = mapped_column(Float)
    destination_lat: Mapped[float] = mapped_column(Float)
    destination_lng: Mapped[float] = mapped_column(Float)
    truck_name: Mapped[str] = mapped_column(String(128))
    status: Mapped[ShipmentStatus] = mapped_column(
        Enum(ShipmentStatus), default=ShipmentStatus.created, index=True
    )
    current_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_temp_low: Mapped[float] = mapped_column(Float, default=35.0)
    target_temp_high: Mapped[float] = mapped_column(Float, default=77.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    telemetry_logs: Mapped[list["TelemetryLog"]] = relationship(back_populates="shipment")
    interventions: Mapped[list["InterventionLog"]] = relationship(back_populates="shipment")
    route_history: Mapped[list["RouteHistory"]] = relationship(back_populates="shipment")


class TelemetryLog(Base):
    __tablename__ = "telemetry_logs"
    __table_args__ = (Index("ix_telemetry_shipment_ts", "shipment_id", "timestamp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id", ondelete="CASCADE"))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    internal_temp: Mapped[float] = mapped_column(Float)
    external_temp: Mapped[float] = mapped_column(Float)
    weather_state: Mapped[str] = mapped_column(String(64))
    route_segment: Mapped[str] = mapped_column(String(128), default="")
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_payload_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    shipment: Mapped["Shipment"] = relationship(back_populates="telemetry_logs")


class InterventionLog(Base):
    __tablename__ = "intervention_logs"
    __table_args__ = (Index("ix_intervention_shipment_ts", "shipment_id", "timestamp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id", ondelete="CASCADE"))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    agent_role: Mapped[str] = mapped_column(String(64))
    trigger_reason: Mapped[str] = mapped_column(Text)
    reasoning_trace: Mapped[str] = mapped_column(Text)
    action_taken: Mapped[str] = mapped_column(String(256))
    suggested_route_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_model_output_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    shipment: Mapped["Shipment"] = relationship(back_populates="interventions")


class RouteHistory(Base):
    __tablename__ = "route_history"
    __table_args__ = (Index("ix_route_shipment_ts", "shipment_id", "timestamp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id", ondelete="CASCADE"))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    route_name: Mapped[str] = mapped_column(String(256))
    reason: Mapped[str] = mapped_column(Text, default="")
    polyline_json: Mapped[list[list[float]] | None] = mapped_column(JSONB, nullable=True)
    distance_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    eta_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)

    shipment: Mapped["Shipment"] = relationship(back_populates="route_history")


class LifecycleEventLog(Base):
    __tablename__ = "lifecycle_event_logs"
    __table_args__ = (Index("ix_lifecycle_shipment_ts", "shipment_id", "timestamp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id", ondelete="CASCADE"))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    event: Mapped[str] = mapped_column(String(128))
    payload_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class WarehouseCandidate(Base):
    __tablename__ = "warehouse_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    state: Mapped[str] = mapped_column(String(8))
    has_cold_storage: Mapped[bool] = mapped_column(Boolean, default=True)
    capacity_units: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
