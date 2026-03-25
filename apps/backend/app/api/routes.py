"""Route generation and saving."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, require_admin
from app.database.models import RouteHistory, Shipment, ShipmentStatus, utcnow
from app.services.routing_service import generate_route_polyline

router = APIRouter(prefix="/routes", tags=["routes"])


class RouteGenerateRequest(BaseModel):
    origin_lat: float
    origin_lng: float
    destination_lat: float
    destination_lng: float


class RoutePreviewResponse(BaseModel):
    polyline: list[list[float]]  # [[lat, lng], ...]
    distance_km: float
    eta_minutes: float


class RouteSaveRequest(BaseModel):
    origin_lat: float
    origin_lng: float
    destination_lat: float
    destination_lng: float
    truck_name: str = Field(min_length=1, max_length=128)
    cargo_type: str = "insulin"
    target_temp_low_f: float = 35.0
    target_temp_high_f: float = 77.0


class RouteSaveResponse(BaseModel):
    shipment_id: int
    shipment_code: str
    route: RoutePreviewResponse


@router.post("/generate", response_model=RoutePreviewResponse)
async def generate_route(
    req: RouteGenerateRequest,
    _: Any = Depends(require_admin),
) -> RoutePreviewResponse:
    try:
        res = await generate_route_polyline(
            origin_lat=req.origin_lat,
            origin_lng=req.origin_lng,
            destination_lat=req.destination_lat,
            destination_lng=req.destination_lng,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    return RoutePreviewResponse(**res)


@router.post("/save", response_model=RouteSaveResponse, status_code=status.HTTP_201_CREATED)
async def save_route_and_create_shipment(
    req: RouteSaveRequest,
    _: Any = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> RouteSaveResponse:
    route = await generate_route_polyline(
        origin_lat=req.origin_lat,
        origin_lng=req.origin_lng,
        destination_lat=req.destination_lat,
        destination_lng=req.destination_lng,
    )

    shipment_code = uuid4().hex
    shipment = Shipment(
        shipment_code=shipment_code,
        cargo_type=req.cargo_type,
        origin_lat=req.origin_lat,
        origin_lng=req.origin_lng,
        destination_lat=req.destination_lat,
        destination_lng=req.destination_lng,
        truck_name=req.truck_name,
        status=ShipmentStatus.created,
        current_lat=req.origin_lat,
        current_lng=req.origin_lng,
        target_temp_low=req.target_temp_low_f,
        target_temp_high=req.target_temp_high_f,
    )
    session.add(shipment)
    await session.commit()
    await session.refresh(shipment)

    rh = RouteHistory(
        shipment_id=shipment.id,
        timestamp=utcnow(),
        route_name="default_route",
        reason="",
        polyline_json=route["polyline"],
        distance_km=route["distance_km"],
        eta_minutes=route["eta_minutes"],
    )
    session.add(rh)
    await session.commit()

    return RouteSaveResponse(
        shipment_id=shipment.id,
        shipment_code=shipment.shipment_code,
        route=RoutePreviewResponse(**route),
    )

