"""
RouteCare AI - Maps & travel-time request/response schemas.

`LocationRef` is the one shape both /maps endpoints accept for an
origin/destination/matrix point - exactly one of a patient id, a
therapist id, or a raw latitude+longitude pair. Resolving a
patient_id/therapist_id to coordinates (and enforcing clinic
ownership - see app.modules.maps.router._resolve_point) happens at the
API layer; app.services.travel_time_service only ever deals in plain
coordinates, never IDs.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.patient import PatientPublic
from app.schemas.therapist import TherapistPublic


class LocationRef(BaseModel):
    patient_id: uuid.UUID | None = None
    therapist_id: uuid.UUID | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def _check_exactly_one_source(self) -> "LocationRef":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together.")
        sources = [self.patient_id is not None, self.therapist_id is not None, self.latitude is not None]
        if sum(sources) != 1:
            raise ValueError("Provide exactly one of patient_id, therapist_id, or latitude+longitude.")
        return self


class ResolvedPoint(BaseModel):
    type: Literal["patient", "therapist", "coordinates"]
    id: uuid.UUID | None
    label: str
    latitude: float
    longitude: float


class TravelTimeRequest(BaseModel):
    origin: LocationRef
    destination: LocationRef


class TravelTimeResponse(BaseModel):
    reachable: bool
    distance_miles: float | None
    duration_minutes: float | None
    calculated_at: datetime | None
    cached: bool


class TravelTimeMatrixRequest(BaseModel):
    points: list[LocationRef] = Field(min_length=2)


class MatrixCell(BaseModel):
    reachable: bool
    distance_miles: float | None
    duration_minutes: float | None
    cached: bool


class TravelTimeMatrixResponse(BaseModel):
    points: list[ResolvedPoint]
    matrix: list[list[MatrixCell | None]]
    calculated_at: datetime


class PatientGeocodeResponse(BaseModel):
    success: bool
    normalized_address: str | None
    patient: PatientPublic


class TherapistGeocodeResponse(BaseModel):
    success: bool
    normalized_address: str | None
    therapist: TherapistPublic
