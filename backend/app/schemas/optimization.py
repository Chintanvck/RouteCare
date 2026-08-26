"""
RouteCare AI - Schedule optimization request/response schemas.
"""

import uuid
from datetime import date, datetime, time
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.models.optimization import OptimizationMode, OptimizationStatus


class CreateOptimizationRequest(BaseModel):
    mode: OptimizationMode
    therapist_id: uuid.UUID
    # DAY_SCHEDULE_OPTIMIZATION: the day to re-order.
    # NEW_PATIENT_PLACEMENT: the start of the search window.
    # WEEK_SCHEDULE_OPTIMIZATION: any date in the target week (snapped to that week's Monday).
    target_date: date

    # NEW_PATIENT_PLACEMENT only.
    patient_id: uuid.UUID | None = None
    search_days: int | None = Field(default=None, gt=0, le=90)
    duration_minutes: int | None = Field(default=None, gt=0, le=480)

    @model_validator(mode="after")
    def _check_mode_fields(self) -> "CreateOptimizationRequest":
        if self.mode == OptimizationMode.NEW_PATIENT_PLACEMENT and self.patient_id is None:
            raise ValueError("patient_id is required when mode is NEW_PATIENT_PLACEMENT.")
        return self


class OptimizationRequestPublic(BaseModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    therapist_id: uuid.UUID
    requested_by: uuid.UUID
    mode: OptimizationMode
    status: OptimizationStatus
    target_date: date
    search_days: int | None
    new_patient_id: uuid.UUID | None
    new_appointment_duration_minutes: int | None
    error_message: str | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OptimizationRecommendationPublic(BaseModel):
    id: uuid.UUID
    optimization_request_id: uuid.UUID
    target_date: date
    rank: int
    efficiency_score: float
    total_drive_minutes: int
    total_distance_miles: float
    time_saved_minutes: int | None
    miles_saved: float | None
    marginal_drive_minutes: int | None
    marginal_distance_miles: float | None
    reason_codes: list[str]
    explanation: str
    recommendation_data: dict[str, Any]
    solver_status: str
    accepted_at: datetime | None
    rejected_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AcceptRecommendationResponse(BaseModel):
    recommendation: OptimizationRecommendationPublic
    appointment_ids: list[uuid.UUID]


class WhatIfScenarioType(str, Enum):
    MOVE = "MOVE"
    ADD = "ADD"
    REMOVE = "REMOVE"


class WhatIfRequest(BaseModel):
    scenario_type: WhatIfScenarioType

    # MOVE and REMOVE: which existing appointment.
    appointment_id: uuid.UUID | None = None
    # MOVE and ADD: the (hypothetical) date/time/duration. For MOVE, an omitted
    # new_duration_minutes keeps the appointment's current duration.
    new_scheduled_date: date | None = None
    new_start_time: time | None = None
    new_duration_minutes: int | None = Field(default=None, gt=0, le=480)
    # ADD only: who the hypothetical new appointment is for.
    patient_id: uuid.UUID | None = None
    therapist_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _check_scenario_fields(self) -> "WhatIfRequest":
        if self.scenario_type in (WhatIfScenarioType.MOVE, WhatIfScenarioType.REMOVE) and self.appointment_id is None:
            raise ValueError("appointment_id is required for MOVE and REMOVE scenarios.")
        if self.scenario_type in (WhatIfScenarioType.MOVE, WhatIfScenarioType.ADD):
            if self.new_scheduled_date is None or self.new_start_time is None:
                raise ValueError("new_scheduled_date and new_start_time are required for MOVE and ADD scenarios.")
        if self.scenario_type == WhatIfScenarioType.ADD:
            if self.patient_id is None or self.therapist_id is None or self.new_duration_minutes is None:
                raise ValueError("patient_id, therapist_id, and new_duration_minutes are required for ADD scenarios.")
        return self


class WhatIfDayImpact(BaseModel):
    """Travel-time/distance for one calendar day affected by a hypothetical change - a same-day
    move or a remove affects one day; a cross-day move or an add affects one day each."""

    target_date: date
    current_drive_minutes: float
    proposed_drive_minutes: float
    current_distance_miles: float
    proposed_distance_miles: float


class WhatIfResponse(BaseModel):
    feasible: bool
    conflicts: list[str]
    days: list[WhatIfDayImpact]
    total_time_impact_minutes: float | None
    total_distance_impact_miles: float | None
    affected_appointment_ids: list[uuid.UUID]


class WhatIfApplyResponse(BaseModel):
    applied: bool
    appointment_id: uuid.UUID | None
    message: str
