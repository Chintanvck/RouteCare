"""
RouteCare AI - Analytics/efficiency dashboard schemas (Phase 8).

Every response model here is built directly by app.services.analytics_service
from computed aggregates, not from an ORM row via `model_validate` - there's
no AnalyticsSomething table, so this mirrors how app.schemas.optimization's
WhatIfResponse is already constructed by hand in optimization_service.py.

All `*_minutes`/`*_hours`/`*_miles`/`*_pct` fields are Optional only where a
denominator can legitimately be zero (e.g. a therapist with no configured
working hours this period) - per the task's explicit "do not display a
savings/utilization number unless it is backed by a valid comparison,"
None means "not enough data," never a misleading 0.
"""

import uuid
from datetime import date, datetime
from enum import Enum

from fastapi import Query
from pydantic import BaseModel


class AnalyticsPeriod(str, Enum):
    TODAY = "today"
    THIS_WEEK = "this_week"
    LAST_WEEK = "last_week"
    THIS_MONTH = "this_month"
    CUSTOM = "custom"


class DateRangeParams:
    """FastAPI dependency: `date_range: DateRangeParams = Depends()`, mirroring
    app.schemas.common.PaginationParams. `start_date`/`end_date` are only consulted when
    period=custom - see app.services.analytics_service.resolve_date_range."""

    def __init__(
        self,
        period: AnalyticsPeriod = Query(AnalyticsPeriod.THIS_WEEK, description="Preset date range."),
        start_date: date | None = Query(None, description="Custom range start (period=custom only)."),
        end_date: date | None = Query(None, description="Custom range end (period=custom only)."),
    ) -> None:
        self.period = period
        self.start_date = start_date
        self.end_date = end_date


class DateRange(BaseModel):
    period: AnalyticsPeriod
    start_date: date
    end_date: date


class DayCount(BaseModel):
    date: date
    count: int


class DayMinutes(BaseModel):
    date: date
    minutes: float


class AnalyticsOverview(BaseModel):
    date_range: DateRange
    total_appointments: int
    completed_appointments: int
    scheduled_appointments: int
    cancelled_appointments: int
    no_show_appointments: int
    therapist_count: int
    total_drive_minutes: float
    total_distance_miles: float
    average_utilization_pct: float | None
    optimization_runs: int
    recommendations_accepted: int
    estimated_time_saved_minutes: float | None
    estimated_miles_saved: float | None
    appointments_by_day: list[DayCount]
    drive_minutes_by_day: list[DayMinutes]


class TherapistAnalytics(BaseModel):
    therapist_id: uuid.UUID
    therapist_name: str
    appointments: int
    working_hours: float
    scheduled_hours: float
    utilization_pct: float | None
    drive_minutes: float
    distance_miles: float
    estimated_time_saved_minutes: float | None
    optimization_runs: int
    recommendations_accepted: int


class TherapistAnalyticsResponse(BaseModel):
    date_range: DateRange
    therapists: list[TherapistAnalytics]


class EfficiencyMetrics(BaseModel):
    date_range: DateRange
    therapist_id: uuid.UUID | None
    sample_size: int
    has_sufficient_data: bool
    average_travel_minutes_between_appointments: float | None
    average_gap_minutes: float | None
    appointments_per_working_hour: float | None
    schedule_occupied_pct: float | None
    total_drive_minutes: float
    total_distance_miles: float


class OptimizationSavingsByDay(BaseModel):
    date: date
    time_saved_minutes: float
    miles_saved: float


class AcceptedOptimizationExample(BaseModel):
    recommendation_id: uuid.UUID
    therapist_id: uuid.UUID
    therapist_name: str
    target_date: date
    mode: str
    before_drive_minutes: float
    after_drive_minutes: float
    time_saved_minutes: float
    miles_saved: float
    accepted_at: datetime


class OptimizationImpact(BaseModel):
    date_range: DateRange
    therapist_id: uuid.UUID | None
    recommendations_accepted: int
    recommendations_with_savings: int
    total_time_saved_minutes: float | None
    total_miles_saved: float | None
    percentage_improvement: float | None
    savings_by_day: list[OptimizationSavingsByDay]
    recent_examples: list[AcceptedOptimizationExample]
