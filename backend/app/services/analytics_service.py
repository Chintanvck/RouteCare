"""
RouteCare AI - Operational analytics/efficiency dashboard (Phase 8).

Deliberately computes everything from tables that already exist
(appointments, therapist_availability, optimization_requests/
recommendations, clinics) rather than adding new ones - see this
module's own docstrings below for exactly which existing service/engine
pieces are reused, matching the task's explicit "reuse existing
services... do not rewrite working functionality."

Driving time/distance is not stored anywhere in the schema (Phase 5/6
never persisted it - travel time is a Redis-cached, coordinate-keyed
lookup computed on demand). This module derives it the same way the
optimizer and What-If already do: build each therapist's *actual*
chronological route for a day from geocoded appointment locations and
run it through app.services.travel_time_service +
app.services.optimization_engine.fixed_order_legs - never a second,
independent driving-time algorithm. app.services.optimization_service's
build_travel_matrix (made public for exactly this reuse) builds the
same (N+1)x(N+1) home-anchored matrix shape the optimizer itself solves
against.

Every metric here is filtered by clinic_id first (tenant isolation) and,
for THERAPIST-role callers, by an additional restrict_to_therapist_id
the router resolves - identical pattern to
app.modules.optimization.router's _own_therapist_id_if_therapist.

Only SCHEDULED/COMPLETED/NO_SHOW appointments count toward driving,
scheduled-hours, and volume metrics that represent "did or will occupy
the calendar" - a CANCELLED appointment never happened and never
required driving, so including it would overstate every efficiency
number. Appointment *status counts* in the overview report CANCELLED
and NO_SHOW explicitly instead, so nothing is silently hidden.

Optimization "savings" only ever come from ACCEPTED recommendations with
a real time_saved_minutes/miles_saved (i.e. DAY_SCHEDULE_OPTIMIZATION or
WEEK_SCHEDULE_OPTIMIZATION, which have an actual before/after
comparison) - NEW_PATIENT_PLACEMENT recommendations report a marginal
cost, not a saving, and rejected recommendations/What-If evaluations are
never persisted with accepted_at set at all, so both are excluded for
free by filtering on `accepted_at IS NOT NULL AND time_saved_minutes IS
NOT NULL` rather than needing a special case.

Custom date ranges are capped at 92 days (~3 months) - not because
longer ranges are unsupported by the queries above, but because the
driving-time calculation below runs one travel-time-matrix lookup per
(therapist, calendar day) with appointments; a multi-year range across a
large clinic could mean thousands of synchronous lookups inside a single
HTTP request. This is the "queries become expensive" case the task
anticipated - the fix here is a sane cap on an operational dashboard's
input, not a new caching layer or aggregation table (out of scope per
the task's explicit "do not prematurely introduce a data warehouse").
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import NotFoundError, ValidationError
from app.models.appointment import Appointment, AppointmentStatus
from app.models.clinic import Clinic
from app.models.optimization import OptimizationRecommendation, OptimizationRequest
from app.models.therapist import Therapist
from app.models.therapist_availability import TherapistAvailability
from app.models.user import User
from app.schemas.analytics import (
    AcceptedOptimizationExample,
    AnalyticsOverview,
    AnalyticsPeriod,
    DateRange,
    DayCount,
    DayMinutes,
    EfficiencyMetrics,
    OptimizationImpact,
    OptimizationSavingsByDay,
    TherapistAnalytics,
    TherapistAnalyticsResponse,
)
from app.services import optimization_engine as engine
from app.services.optimization_service import build_travel_matrix
from app.services.travel_time_service import LocationPoint

MAX_CUSTOM_RANGE_DAYS = 92
_DRIVE_STATUSES = (AppointmentStatus.SCHEDULED, AppointmentStatus.COMPLETED, AppointmentStatus.NO_SHOW)


def _time_to_minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def _clinic_timezone(db: Session, *, clinic_id: uuid.UUID) -> ZoneInfo:
    clinic = db.get(Clinic, clinic_id)
    tz_name = clinic.timezone if clinic is not None else "UTC"
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def resolve_date_range(
    db: Session,
    *,
    clinic_id: uuid.UUID,
    period: AnalyticsPeriod,
    start_date: date | None,
    end_date: date | None,
) -> DateRange:
    """Resolves a period preset (or custom bounds) to concrete [start_date, end_date] (inclusive),
    evaluated against "today" in the clinic's own timezone - see app/models/clinic.py and
    app/models/appointment.py's docstrings: scheduled_date is already wall-clock time in the
    clinic's timezone, so "this week" must be computed in that same timezone, not UTC or the
    server's local time."""
    tz = _clinic_timezone(db, clinic_id=clinic_id)
    today = datetime.now(tz).date()

    if period == AnalyticsPeriod.CUSTOM:
        if start_date is None or end_date is None:
            raise ValidationError(
                "start_date and end_date are both required when period=custom.", code="CUSTOM_RANGE_REQUIRES_DATES"
            )
        if start_date > end_date:
            raise ValidationError("start_date must not be after end_date.", code="INVALID_DATE_RANGE")
        if (end_date - start_date).days + 1 > MAX_CUSTOM_RANGE_DAYS:
            raise ValidationError(
                f"Custom date ranges are limited to {MAX_CUSTOM_RANGE_DAYS} days.", code="DATE_RANGE_TOO_LARGE"
            )
        resolved_start, resolved_end = start_date, end_date
    elif period == AnalyticsPeriod.TODAY:
        resolved_start, resolved_end = today, today
    elif period == AnalyticsPeriod.THIS_WEEK:
        resolved_start = today - timedelta(days=today.weekday())
        resolved_end = resolved_start + timedelta(days=6)
    elif period == AnalyticsPeriod.LAST_WEEK:
        this_week_start = today - timedelta(days=today.weekday())
        resolved_start = this_week_start - timedelta(days=7)
        resolved_end = resolved_start + timedelta(days=6)
    elif period == AnalyticsPeriod.THIS_MONTH:
        resolved_start = today.replace(day=1)
        next_month = (
            resolved_start.replace(year=resolved_start.year + 1, month=1)
            if resolved_start.month == 12
            else resolved_start.replace(month=resolved_start.month + 1)
        )
        resolved_end = next_month - timedelta(days=1)
    else:
        raise ValidationError("Unsupported analytics period.", code="INVALID_PERIOD")

    return DateRange(period=period, start_date=resolved_start, end_date=resolved_end)


def _local_range_to_utc_bounds(date_range: DateRange, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """[start_date, end_date] is inclusive in clinic-local calendar days; converts that to a
    half-open UTC datetime range for filtering TIMESTAMPTZ columns (OptimizationRequest.created_at,
    OptimizationRecommendation.accepted_at) consistently with the same clinic timezone used for
    resolve_date_range."""
    start_dt = datetime.combine(date_range.start_date, time.min, tzinfo=tz)
    end_dt = datetime.combine(date_range.end_date + timedelta(days=1), time.min, tzinfo=tz)
    return start_dt.astimezone(timezone.utc), end_dt.astimezone(timezone.utc)


def _weekday_occurrences(date_range: DateRange) -> dict[int, int]:
    """How many times each day_of_week (0=Monday..6=Sunday) occurs within the range - used to turn
    a therapist's recurring weekly availability into a "working hours available this period" total."""
    counts = {i: 0 for i in range(7)}
    current = date_range.start_date
    while current <= date_range.end_date:
        counts[current.weekday()] += 1
        current += timedelta(days=1)
    return counts


def _active_therapists(db: Session, *, clinic_id: uuid.UUID, therapist_id: uuid.UUID | None) -> list[Therapist]:
    query = (
        db.query(Therapist)
        .join(User, Therapist.user_id == User.id)
        .filter(Therapist.clinic_id == clinic_id, User.is_active.is_(True))
        .options(joinedload(Therapist.user))
    )
    if therapist_id is not None:
        query = query.filter(Therapist.id == therapist_id)
    return query.all()


def _working_minutes_by_weekday(db: Session, *, clinic_id: uuid.UUID) -> dict[uuid.UUID, dict[int, int]]:
    """therapist_id -> {day_of_week: total available minutes} from recurring weekly availability
    (is_available=True rows only - break rows are handled separately, see _break_windows_by_weekday).
    One query for the whole clinic; the per-therapist/per-day grouping happens in Python since the
    row count here is small (a handful of rows per therapist) - not worth a second round trip per
    therapist."""
    rows = (
        db.query(TherapistAvailability)
        .join(Therapist, TherapistAvailability.therapist_id == Therapist.id)
        .filter(Therapist.clinic_id == clinic_id, TherapistAvailability.is_available.is_(True))
        .all()
    )
    result: dict[uuid.UUID, dict[int, int]] = {}
    for row in rows:
        per_day = result.setdefault(row.therapist_id, {i: 0 for i in range(7)})
        per_day[row.day_of_week] += _time_to_minutes(row.end_time) - _time_to_minutes(row.start_time)
    return result


def _break_windows_by_weekday(db: Session, *, clinic_id: uuid.UUID) -> dict[tuple[uuid.UUID, int], list[tuple[int, int]]]:
    """(therapist_id, day_of_week) -> list of (start_minute, end_minute) break windows
    (is_available=False rows) - used only to avoid double-counting a known, intentional break as an
    "inefficient" gap between appointments (see _effective_gap_minutes)."""
    rows = (
        db.query(TherapistAvailability)
        .join(Therapist, TherapistAvailability.therapist_id == Therapist.id)
        .filter(Therapist.clinic_id == clinic_id, TherapistAvailability.is_available.is_(False))
        .all()
    )
    result: dict[tuple[uuid.UUID, int], list[tuple[int, int]]] = defaultdict(list)
    for row in rows:
        result[(row.therapist_id, row.day_of_week)].append((_time_to_minutes(row.start_time), _time_to_minutes(row.end_time)))
    return result


def _working_hours_for_range(
    working_minutes_by_weekday: dict[int, int] | None, weekday_occurrences: dict[int, int]
) -> float:
    if not working_minutes_by_weekday:
        return 0.0
    total_minutes = sum(working_minutes_by_weekday.get(dow, 0) * count for dow, count in weekday_occurrences.items())
    return round(total_minutes / 60, 2)


@dataclass
class _TherapistDayAppointments:
    appointment_count: int = 0
    scheduled_minutes: int = 0
    drive_minutes: float = 0.0
    distance_miles: float = 0.0
    inter_appointment_leg_minutes: list[float] = field(default_factory=list)
    gap_intervals: list[tuple[int, int]] = field(default_factory=list)  # (start_minute, end_minute), chronological


def _compute_day_appointment_metrics(
    db: Session, *, clinic_id: uuid.UUID, date_range: DateRange, therapist_id: uuid.UUID | None
) -> dict[tuple[uuid.UUID, date], _TherapistDayAppointments]:
    """The single data-gathering pass every driving/gap/volume-by-day metric in this module builds
    on: one query for every SCHEDULED/COMPLETED/NO_SHOW appointment in range, grouped by
    (therapist_id, scheduled_date), with an actual chronological driving route computed per group
    via the same travel-time-matrix machinery the optimizer uses. Appointments whose patient isn't
    geocoded still count toward appointment_count/scheduled_minutes but contribute no travel leg
    (their location is simply unknown, not zero-distance)."""
    query = (
        db.query(Appointment)
        .filter(
            Appointment.clinic_id == clinic_id,
            Appointment.scheduled_date >= date_range.start_date,
            Appointment.scheduled_date <= date_range.end_date,
            Appointment.status.in_(_DRIVE_STATUSES),
        )
        .options(joinedload(Appointment.patient), joinedload(Appointment.therapist).joinedload(Therapist.user))
    )
    if therapist_id is not None:
        query = query.filter(Appointment.therapist_id == therapist_id)
    appointments = query.order_by(Appointment.therapist_id, Appointment.scheduled_date, Appointment.start_time).all()

    groups: dict[tuple[uuid.UUID, date], list[Appointment]] = defaultdict(list)
    for appt in appointments:
        groups[(appt.therapist_id, appt.scheduled_date)].append(appt)

    results: dict[tuple[uuid.UUID, date], _TherapistDayAppointments] = {}
    for (t_id, day), day_appointments in groups.items():
        day_appointments.sort(key=lambda a: a.start_time)
        metrics = _TherapistDayAppointments(
            appointment_count=len(day_appointments),
            scheduled_minutes=sum(a.duration_minutes for a in day_appointments),
        )

        for prev, nxt in zip(day_appointments, day_appointments[1:]):
            gap_start = _time_to_minutes(prev.end_time)
            gap_end = _time_to_minutes(nxt.start_time)
            if gap_end > gap_start:
                metrics.gap_intervals.append((gap_start, gap_end))

        geocoded = [a for a in day_appointments if a.patient.latitude is not None and a.patient.longitude is not None]
        if geocoded:
            therapist = geocoded[0].therapist
            visits = [
                engine.ScheduledVisit(
                    appointment_id=a.id,
                    patient_id=a.patient_id,
                    label=a.patient.full_name,
                    duration_minutes=a.duration_minutes,
                    original_start_minute=_time_to_minutes(a.start_time),
                    allowed_start_minutes=[],
                )
                for a in geocoded
            ]
            points = [LocationPoint(float(a.patient.latitude), float(a.patient.longitude)) for a in geocoded]
            travel_matrix = build_travel_matrix(clinic_id=clinic_id, therapist=therapist, patient_points=points)
            legs = engine.fixed_order_legs(visits, travel_matrix)
            metrics.drive_minutes = sum(leg.minutes for leg in legs)
            metrics.distance_miles = sum(leg.miles for leg in legs)
            metrics.inter_appointment_leg_minutes = [
                leg.minutes for leg in legs if leg.from_node != 0 and leg.to_node != 0
            ]

        results[(t_id, day)] = metrics

    return results


def _optimization_activity_by_therapist(
    db: Session, *, clinic_id: uuid.UUID, date_range: DateRange, tz: ZoneInfo, therapist_id: uuid.UUID | None
) -> dict[uuid.UUID, dict[str, float]]:
    """therapist_id -> {"runs": N, "accepted": N, "time_saved_minutes": total} for optimization
    activity within the range. "Runs" are counted by OptimizationRequest.created_at (when the
    optimization was requested); "accepted"/savings by OptimizationRecommendation.accepted_at (when
    it was actually applied) - both bounded by the same clinic-local range, converted to UTC once."""
    utc_start, utc_end = _local_range_to_utc_bounds(date_range, tz)

    runs_query = db.query(OptimizationRequest.therapist_id, func.count(OptimizationRequest.id)).filter(
        OptimizationRequest.clinic_id == clinic_id,
        OptimizationRequest.created_at >= utc_start,
        OptimizationRequest.created_at < utc_end,
    )
    if therapist_id is not None:
        runs_query = runs_query.filter(OptimizationRequest.therapist_id == therapist_id)
    runs_by_therapist = dict(runs_query.group_by(OptimizationRequest.therapist_id).all())

    accepted_query = (
        db.query(
            OptimizationRequest.therapist_id,
            func.count(OptimizationRecommendation.id),
            func.sum(OptimizationRecommendation.time_saved_minutes),
        )
        .join(OptimizationRequest, OptimizationRecommendation.optimization_request_id == OptimizationRequest.id)
        .filter(
            OptimizationRequest.clinic_id == clinic_id,
            OptimizationRecommendation.accepted_at.isnot(None),
            OptimizationRecommendation.accepted_at >= utc_start,
            OptimizationRecommendation.accepted_at < utc_end,
        )
    )
    if therapist_id is not None:
        accepted_query = accepted_query.filter(OptimizationRequest.therapist_id == therapist_id)
    accepted_rows = accepted_query.group_by(OptimizationRequest.therapist_id).all()

    result: dict[uuid.UUID, dict[str, float]] = defaultdict(lambda: {"runs": 0, "accepted": 0, "time_saved_minutes": 0.0})
    for t_id, count in runs_by_therapist.items():
        result[t_id]["runs"] = count
    for t_id, accepted_count, time_saved_sum in accepted_rows:
        result[t_id]["accepted"] = accepted_count
        result[t_id]["time_saved_minutes"] = float(time_saved_sum or 0.0)
    return result


def compute_therapist_metrics(
    db: Session, *, clinic_id: uuid.UUID, date_range: DateRange, therapist_id: uuid.UUID | None = None
) -> TherapistAnalyticsResponse:
    """Per-therapist breakdown for the given range. With therapist_id=None, includes every active
    therapist in the clinic (even ones with zero appointments this period, so an idle therapist is
    visible as 0%% utilization rather than silently absent from the list)."""
    if therapist_id is not None:
        exists = db.query(Therapist.id).filter(Therapist.clinic_id == clinic_id, Therapist.id == therapist_id).first()
        if exists is None:
            raise NotFoundError("Therapist was not found.", code="THERAPIST_NOT_FOUND")

    therapists = _active_therapists(db, clinic_id=clinic_id, therapist_id=therapist_id)
    tz = _clinic_timezone(db, clinic_id=clinic_id)
    day_metrics = _compute_day_appointment_metrics(
        db, clinic_id=clinic_id, date_range=date_range, therapist_id=therapist_id
    )
    working_minutes = _working_minutes_by_weekday(db, clinic_id=clinic_id)
    weekday_occurrences = _weekday_occurrences(date_range)
    activity = _optimization_activity_by_therapist(
        db, clinic_id=clinic_id, date_range=date_range, tz=tz, therapist_id=therapist_id
    )

    rows: list[TherapistAnalytics] = []
    for therapist in therapists:
        own_days = [m for (t_id, _day), m in day_metrics.items() if t_id == therapist.id]
        appointments = sum(m.appointment_count for m in own_days)
        scheduled_hours = round(sum(m.scheduled_minutes for m in own_days) / 60, 2)
        drive_minutes = round(sum(m.drive_minutes for m in own_days), 1)
        distance_miles = round(sum(m.distance_miles for m in own_days), 2)
        working_hours = _working_hours_for_range(working_minutes.get(therapist.id), weekday_occurrences)
        utilization_pct = round(scheduled_hours / working_hours * 100, 1) if working_hours > 0 else None
        own_activity = activity.get(therapist.id, {"runs": 0, "accepted": 0, "time_saved_minutes": 0.0})

        rows.append(
            TherapistAnalytics(
                therapist_id=therapist.id,
                therapist_name=f"{therapist.first_name} {therapist.last_name}",
                appointments=appointments,
                working_hours=working_hours,
                scheduled_hours=scheduled_hours,
                utilization_pct=utilization_pct,
                drive_minutes=drive_minutes,
                distance_miles=distance_miles,
                estimated_time_saved_minutes=(
                    round(own_activity["time_saved_minutes"], 1) if own_activity["accepted"] else None
                ),
                optimization_runs=int(own_activity["runs"]),
                recommendations_accepted=int(own_activity["accepted"]),
            )
        )

    rows.sort(key=lambda r: r.therapist_name)
    return TherapistAnalyticsResponse(date_range=date_range, therapists=rows)


def compute_overview(
    db: Session, *, clinic_id: uuid.UUID, date_range: DateRange, therapist_id: uuid.UUID | None = None
) -> AnalyticsOverview:
    """Clinic-wide (or, for a THERAPIST-role caller, one therapist's) snapshot for the range. Built
    on top of compute_therapist_metrics rather than re-deriving working-hours/utilization a second
    time, plus its own appointment-status breakdown and day-by-day series (which need day-level
    granularity compute_therapist_metrics doesn't expose)."""
    therapist_metrics = compute_therapist_metrics(db, clinic_id=clinic_id, date_range=date_range, therapist_id=therapist_id)

    status_query = db.query(Appointment.status, func.count(Appointment.id)).filter(
        Appointment.clinic_id == clinic_id,
        Appointment.scheduled_date >= date_range.start_date,
        Appointment.scheduled_date <= date_range.end_date,
    )
    if therapist_id is not None:
        status_query = status_query.filter(Appointment.therapist_id == therapist_id)
    status_counts = {status: 0 for status in AppointmentStatus}
    for status_value, count in status_query.group_by(Appointment.status).all():
        status_counts[AppointmentStatus(status_value)] = count

    day_metrics = _compute_day_appointment_metrics(
        db, clinic_id=clinic_id, date_range=date_range, therapist_id=therapist_id
    )
    appointments_by_day: dict[date, int] = defaultdict(int)
    drive_minutes_by_day: dict[date, float] = defaultdict(float)
    for (_t_id, day), metrics in day_metrics.items():
        appointments_by_day[day] += metrics.appointment_count
        drive_minutes_by_day[day] += metrics.drive_minutes

    utilizations = [t.utilization_pct for t in therapist_metrics.therapists if t.utilization_pct is not None]
    time_saved_values = [t.estimated_time_saved_minutes for t in therapist_metrics.therapists if t.estimated_time_saved_minutes]
    recommendations_accepted = sum(t.recommendations_accepted for t in therapist_metrics.therapists)

    return AnalyticsOverview(
        date_range=date_range,
        total_appointments=sum(status_counts.values()),
        completed_appointments=status_counts[AppointmentStatus.COMPLETED],
        scheduled_appointments=status_counts[AppointmentStatus.SCHEDULED],
        cancelled_appointments=status_counts[AppointmentStatus.CANCELLED],
        no_show_appointments=status_counts[AppointmentStatus.NO_SHOW],
        therapist_count=len(therapist_metrics.therapists),
        total_drive_minutes=round(sum(t.drive_minutes for t in therapist_metrics.therapists), 1),
        total_distance_miles=round(sum(t.distance_miles for t in therapist_metrics.therapists), 2),
        average_utilization_pct=round(sum(utilizations) / len(utilizations), 1) if utilizations else None,
        optimization_runs=sum(t.optimization_runs for t in therapist_metrics.therapists),
        recommendations_accepted=recommendations_accepted,
        estimated_time_saved_minutes=round(sum(time_saved_values), 1) if time_saved_values else None,
        estimated_miles_saved=_estimated_miles_saved(db, clinic_id=clinic_id, date_range=date_range, therapist_id=therapist_id),
        appointments_by_day=[DayCount(date=d, count=c) for d, c in sorted(appointments_by_day.items())],
        drive_minutes_by_day=[DayMinutes(date=d, minutes=round(m, 1)) for d, m in sorted(drive_minutes_by_day.items())],
    )


def _estimated_miles_saved(
    db: Session, *, clinic_id: uuid.UUID, date_range: DateRange, therapist_id: uuid.UUID | None
) -> float | None:
    tz = _clinic_timezone(db, clinic_id=clinic_id)
    utc_start, utc_end = _local_range_to_utc_bounds(date_range, tz)
    query = (
        db.query(func.sum(OptimizationRecommendation.miles_saved))
        .join(OptimizationRequest, OptimizationRecommendation.optimization_request_id == OptimizationRequest.id)
        .filter(
            OptimizationRequest.clinic_id == clinic_id,
            OptimizationRecommendation.accepted_at.isnot(None),
            OptimizationRecommendation.accepted_at >= utc_start,
            OptimizationRecommendation.accepted_at < utc_end,
            OptimizationRecommendation.miles_saved.isnot(None),
        )
    )
    if therapist_id is not None:
        query = query.filter(OptimizationRequest.therapist_id == therapist_id)
    total = query.scalar()
    return round(float(total), 2) if total is not None else None


def _effective_gap_minutes(
    gap_intervals_by_therapist_day: list[tuple[uuid.UUID, date, int, int]],
    break_windows: dict[tuple[uuid.UUID, int], list[tuple[int, int]]],
) -> list[float]:
    """Raw gap-between-appointments minutes, minus whatever portion of that gap overlaps a
    therapist's declared recurring break for that weekday - per the task's explicit "do not
    classify unpaid breaks as inefficient schedule gaps unless the system knows the gap was
    unintended." A gap the system has no break record for is left as-is (assumed unintended idle
    time), since that's the only information actually available."""
    effective: list[float] = []
    for t_id, day, gap_start, gap_end in gap_intervals_by_therapist_day:
        breaks = break_windows.get((t_id, day.weekday()), [])
        overlap = sum(max(0, min(gap_end, b_end) - max(gap_start, b_start)) for b_start, b_end in breaks)
        effective.append(max(0.0, (gap_end - gap_start) - overlap))
    return effective


def compute_efficiency(
    db: Session, *, clinic_id: uuid.UUID, date_range: DateRange, therapist_id: uuid.UUID | None = None
) -> EfficiencyMetrics:
    """Schedule-quality metrics, clinic-wide or for one therapist. `sample_size` is the number of
    therapist-days with at least one appointment considered - the frontend uses
    has_sufficient_data (sample_size >= a small floor) to decide whether to render a chart at all,
    per the task's explicit "avoid charts for metrics with too little data / show empty states."
    """
    if therapist_id is not None:
        exists = db.query(Therapist.id).filter(Therapist.clinic_id == clinic_id, Therapist.id == therapist_id).first()
        if exists is None:
            raise NotFoundError("Therapist was not found.", code="THERAPIST_NOT_FOUND")

    day_metrics = _compute_day_appointment_metrics(
        db, clinic_id=clinic_id, date_range=date_range, therapist_id=therapist_id
    )
    break_windows = _break_windows_by_weekday(db, clinic_id=clinic_id)

    sample_size = len(day_metrics)
    total_appointments = sum(m.appointment_count for m in day_metrics.values())
    total_scheduled_minutes = sum(m.scheduled_minutes for m in day_metrics.values())
    total_drive_minutes = round(sum(m.drive_minutes for m in day_metrics.values()), 1)
    total_distance_miles = round(sum(m.distance_miles for m in day_metrics.values()), 2)

    inter_leg_minutes = [minutes for m in day_metrics.values() for minutes in m.inter_appointment_leg_minutes]
    gap_intervals = [
        (t_id, day, gap_start, gap_end)
        for (t_id, day), m in day_metrics.items()
        for gap_start, gap_end in m.gap_intervals
    ]
    effective_gaps = _effective_gap_minutes(gap_intervals, break_windows)

    working_minutes = _working_minutes_by_weekday(db, clinic_id=clinic_id)
    weekday_occurrences = _weekday_occurrences(date_range)
    if therapist_id is not None:
        total_working_hours = _working_hours_for_range(working_minutes.get(therapist_id), weekday_occurrences)
    else:
        therapists = _active_therapists(db, clinic_id=clinic_id, therapist_id=None)
        total_working_hours = sum(
            _working_hours_for_range(working_minutes.get(t.id), weekday_occurrences) for t in therapists
        )

    return EfficiencyMetrics(
        date_range=date_range,
        therapist_id=therapist_id,
        sample_size=sample_size,
        has_sufficient_data=sample_size >= 3,
        average_travel_minutes_between_appointments=(
            round(sum(inter_leg_minutes) / len(inter_leg_minutes), 1) if inter_leg_minutes else None
        ),
        average_gap_minutes=round(sum(effective_gaps) / len(effective_gaps), 1) if effective_gaps else None,
        appointments_per_working_hour=(
            round(total_appointments / total_working_hours, 2) if total_working_hours > 0 else None
        ),
        schedule_occupied_pct=(
            round(total_scheduled_minutes / (total_working_hours * 60) * 100, 1) if total_working_hours > 0 else None
        ),
        total_drive_minutes=total_drive_minutes,
        total_distance_miles=total_distance_miles,
    )


def compute_optimization_impact(
    db: Session, *, clinic_id: uuid.UUID, date_range: DateRange, therapist_id: uuid.UUID | None = None
) -> OptimizationImpact:
    """Impact of ACCEPTED optimization recommendations only. Filtering on
    `accepted_at IS NOT NULL` already excludes rejected recommendations (rejected_at set,
    accepted_at null) and What-If evaluations (never persisted at all - see
    app.services.optimization_service.evaluate_what_if's docstring). Filtering further on
    `time_saved_minutes IS NOT NULL` restricts the actual savings numbers to
    DAY_SCHEDULE_OPTIMIZATION/WEEK_SCHEDULE_OPTIMIZATION recommendations, which have a genuine
    before/after comparison - NEW_PATIENT_PLACEMENT recommendations report a marginal insertion
    cost, not a saving, so they're counted in `recommendations_accepted` (activity) but never in
    the savings totals."""
    if therapist_id is not None:
        exists = db.query(Therapist.id).filter(Therapist.clinic_id == clinic_id, Therapist.id == therapist_id).first()
        if exists is None:
            raise NotFoundError("Therapist was not found.", code="THERAPIST_NOT_FOUND")

    tz = _clinic_timezone(db, clinic_id=clinic_id)
    utc_start, utc_end = _local_range_to_utc_bounds(date_range, tz)

    base_query = (
        db.query(OptimizationRecommendation, OptimizationRequest)
        .join(OptimizationRequest, OptimizationRecommendation.optimization_request_id == OptimizationRequest.id)
        .filter(
            OptimizationRequest.clinic_id == clinic_id,
            OptimizationRecommendation.accepted_at.isnot(None),
            OptimizationRecommendation.accepted_at >= utc_start,
            OptimizationRecommendation.accepted_at < utc_end,
        )
    )
    if therapist_id is not None:
        base_query = base_query.filter(OptimizationRequest.therapist_id == therapist_id)
    all_accepted = base_query.order_by(OptimizationRecommendation.accepted_at.desc()).all()

    with_savings = [
        (rec, req) for rec, req in all_accepted if rec.time_saved_minutes is not None and rec.miles_saved is not None
    ]

    total_time_saved = sum(rec.time_saved_minutes for rec, _req in with_savings)
    total_miles_saved = sum(float(rec.miles_saved) for rec, _req in with_savings)
    total_before_minutes = sum(rec.total_drive_minutes + rec.time_saved_minutes for rec, _req in with_savings)

    savings_by_day_map: dict[date, dict[str, float]] = defaultdict(lambda: {"minutes": 0.0, "miles": 0.0})
    for rec, _req in with_savings:
        local_date = rec.accepted_at.astimezone(tz).date()
        savings_by_day_map[local_date]["minutes"] += rec.time_saved_minutes
        savings_by_day_map[local_date]["miles"] += float(rec.miles_saved)

    therapist_ids = {req.therapist_id for _rec, req in with_savings[:10]}
    name_map: dict[uuid.UUID, str] = {}
    if therapist_ids:
        therapists = (
            db.query(Therapist)
            .join(User, Therapist.user_id == User.id)
            .filter(Therapist.id.in_(therapist_ids))
            .options(joinedload(Therapist.user))
            .all()
        )
        name_map = {t.id: f"{t.first_name} {t.last_name}" for t in therapists}

    recent_examples = [
        AcceptedOptimizationExample(
            recommendation_id=rec.id,
            therapist_id=req.therapist_id,
            therapist_name=name_map.get(req.therapist_id, "Unknown therapist"),
            target_date=rec.target_date,
            mode=req.mode.value if hasattr(req.mode, "value") else req.mode,
            before_drive_minutes=round(rec.total_drive_minutes + rec.time_saved_minutes, 1),
            after_drive_minutes=round(rec.total_drive_minutes, 1),
            time_saved_minutes=round(rec.time_saved_minutes, 1),
            miles_saved=round(float(rec.miles_saved), 2),
            accepted_at=rec.accepted_at,
        )
        for rec, req in with_savings[:10]
    ]

    return OptimizationImpact(
        date_range=date_range,
        therapist_id=therapist_id,
        recommendations_accepted=len(all_accepted),
        recommendations_with_savings=len(with_savings),
        total_time_saved_minutes=round(total_time_saved, 1) if with_savings else None,
        total_miles_saved=round(total_miles_saved, 2) if with_savings else None,
        percentage_improvement=(
            round(total_time_saved / total_before_minutes * 100, 1) if total_before_minutes > 0 else None
        ),
        savings_by_day=[
            OptimizationSavingsByDay(date=d, time_saved_minutes=round(v["minutes"], 1), miles_saved=round(v["miles"], 2))
            for d, v in sorted(savings_by_day_map.items())
        ],
        recent_examples=recent_examples,
    )
