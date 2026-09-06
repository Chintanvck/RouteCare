"""
RouteCare AI - Schedule optimization orchestration (Phase 6, extended Phase 7).

This is the DB/IO layer above the pure app.services.optimization_engine:
fetches therapists/appointments/availability, builds travel-time
matrices via app.services.travel_time_service, calls the pure engine,
and persists OptimizationRequest/OptimizationRecommendation rows. It
never computes a schedule itself - see optimization_engine.py for the
actual algorithms.

`run_optimization` is the background-task entrypoint (dispatched via
app.workers.optimization_tasks, mirroring import_service's pattern of
being directly callable with a plain `db: Session` for both Celery and
tests). It always leaves the request in COMPLETED or FAILED status:
COMPLETED with an INFEASIBLE-flagged recommendation means "the optimizer
ran successfully and determined no feasible schedule exists" (a normal,
expected outcome - never silently hidden); FAILED means the optimizer
could not even run (missing geocoding data, an unexpected error) and is
never used for "ran fine, found nothing better."

WEEK_SCHEDULE_OPTIMIZATION (Phase 7) does not duplicate the day-reorder
algorithm - `_compute_day_schedule_recommendation` is the single
implementation, called once for a plain DAY_SCHEDULE_OPTIMIZATION
request and 7 times (Monday..Sunday) for a weekly one. A per-day error
(e.g. one day's patient isn't geocoded) never fails the whole week -
see `_run_week_schedule_optimization`.

Accepting a recommendation never trusts that the world hasn't changed
since it was generated - see `accept_recommendation` and its two
mode-specific helpers for exactly what gets re-validated and why.
Acceptance state (Phase 7) lives per-recommendation (`accepted_at`/
`rejected_at`), not as a single slot on the request - see
app.models.optimization's docstring for why.

What-If (Phase 7) supports three scenario types - MOVE, ADD, REMOVE -
and both a read-only `evaluate_what_if` and a real `apply_what_if` that
commits the change. Every apply re-validates against the *live*
database via the same appointment_service functions everything else
uses, so staleness is caught for free: nothing is ever applied from a
cached/precomputed check.
"""

import uuid
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy.orm import Query, Session, joinedload

from app.core.config import settings
from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.core.logging_config import app_logger
from app.models.appointment import Appointment, AppointmentStatus
from app.models.optimization import (
    OptimizationMode,
    OptimizationRecommendation,
    OptimizationRequest,
    OptimizationStatus,
)
from app.models.patient import Patient
from app.models.patient_availability import PatientAvailability, PatientAvailabilityPreference
from app.models.therapist import Therapist
from app.models.therapist_availability import TherapistAvailability
from app.models.user import User
from app.schemas.appointment import AppointmentCreate, AppointmentUpdate
from app.schemas.optimization import (
    CreateOptimizationRequest,
    WhatIfDayImpact,
    WhatIfRequest,
    WhatIfResponse,
    WhatIfScenarioType,
)
from app.services import appointment_service, audit_service, patient_service, therapist_service
from app.services import optimization_engine as engine
from app.services.scheduling_validation import TimeRange, check_patient_availability, check_therapist_working_hours
from app.services.travel_time_service import LocationPoint, get_travel_time_matrix

_HOME_KEY = engine.HOME_KEY
_NEW_KEY = engine.NEW_KEY


class _OptimizationInputError(Exception):
    """Raised for explainable reasons the optimizer can't run at all (missing geocoding, no
    working days, too many appointments) - caught by run_optimization and stored as a clear
    FAILED error_message (single-day/new-patient modes) or an ERROR-flagged day (weekly mode),
    never an unhandled 500."""


def _not_found() -> NotFoundError:
    return NotFoundError("Optimization request was not found.", code="OPTIMIZATION_REQUEST_NOT_FOUND")


def _time_to_minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def _minutes_to_time(minute_of_day: int) -> time:
    return time(hour=minute_of_day // 60, minute=minute_of_day % 60)


def _require_coords(latitude: float | None, longitude: float | None) -> tuple[float, float]:
    """Callers only reach this after already confirming the coordinates are set (an ungeocoded
    patient/therapist has already been rejected earlier in the same function) - the assert makes
    that guarantee explicit for both mypy and a future reader, rather than a silent float(None)."""
    assert latitude is not None and longitude is not None
    return float(latitude), float(longitude)


def _add_minutes(start_time: time, duration_minutes: int) -> time | None:
    """Same "None if it crosses midnight" contract as appointment_service._compute_end_time -
    duplicated rather than imported since it's a two-line calculation and this module otherwise
    has no reason to depend on appointment_service's private helpers."""
    total = start_time.hour * 60 + start_time.minute + duration_minutes
    if total >= engine.MINUTES_PER_DAY:
        return None
    return _minutes_to_time(total)


def _start_of_week(d: date) -> date:
    return d - timedelta(days=d.weekday())


def create_request(
    db: Session, *, clinic_id: uuid.UUID, requested_by: uuid.UUID, data: CreateOptimizationRequest
) -> OptimizationRequest:
    therapist = therapist_service.get_therapist(db, clinic_id=clinic_id, therapist_id=data.therapist_id)

    new_patient_id = None
    duration_minutes = None
    search_days = None
    if data.mode == OptimizationMode.NEW_PATIENT_PLACEMENT:
        patient = patient_service.get_patient(db, clinic_id=clinic_id, patient_id=data.patient_id)  # type: ignore[arg-type]
        new_patient_id = patient.id
        duration_minutes = data.duration_minutes or patient.visit_duration_minutes
        if duration_minutes is None:
            raise BusinessRuleError(
                "A visit duration is required - set one on the patient or provide duration_minutes.",
                code="DURATION_REQUIRED",
            )
        search_days = data.search_days or settings.OPTIMIZATION_DEFAULT_SEARCH_DAYS

    request = OptimizationRequest(
        clinic_id=clinic_id,
        therapist_id=therapist.id,
        requested_by=requested_by,
        mode=data.mode,
        status=OptimizationStatus.PENDING,
        target_date=data.target_date,
        search_days=search_days,
        new_patient_id=new_patient_id,
        new_appointment_duration_minutes=duration_minutes,
    )
    db.add(request)
    db.commit()
    db.refresh(request)
    return request


def _base_request_query(db: Session, *, clinic_id: uuid.UUID) -> Query:
    return db.query(OptimizationRequest).filter(OptimizationRequest.clinic_id == clinic_id)


def get_request(
    db: Session, *, clinic_id: uuid.UUID, request_id: uuid.UUID, restrict_to_therapist_id: uuid.UUID | None = None
) -> OptimizationRequest:
    request = _base_request_query(db, clinic_id=clinic_id).filter(OptimizationRequest.id == request_id).first()
    if request is None:
        raise _not_found()
    if restrict_to_therapist_id is not None and request.therapist_id != restrict_to_therapist_id:
        raise _not_found()
    return request


def list_recommendations(
    db: Session, *, clinic_id: uuid.UUID, request_id: uuid.UUID, restrict_to_therapist_id: uuid.UUID | None = None
) -> list[OptimizationRecommendation]:
    get_request(db, clinic_id=clinic_id, request_id=request_id, restrict_to_therapist_id=restrict_to_therapist_id)
    return (
        db.query(OptimizationRecommendation)
        .filter(OptimizationRecommendation.optimization_request_id == request_id)
        .order_by(OptimizationRecommendation.target_date.asc(), OptimizationRecommendation.rank.asc())
        .all()
    )


def _infeasible_recommendation(
    target_date: date, reason_code: str, explanation: str, *, solver_status: str = "INFEASIBLE"
) -> dict:
    return {
        "target_date": target_date,
        "efficiency_score": 0.0,
        "total_drive_minutes": 0,
        "total_distance_miles": 0.0,
        "time_saved_minutes": None,
        "miles_saved": None,
        "marginal_drive_minutes": None,
        "marginal_distance_miles": None,
        "reason_codes": [reason_code],
        "explanation": explanation,
        "recommendation_data": {},
        "solver_status": solver_status,
    }


def _therapist_day_windows(db: Session, *, therapist_id: uuid.UUID, day_of_week: int) -> tuple[list, list]:
    rows = (
        db.query(TherapistAvailability)
        .filter(TherapistAvailability.therapist_id == therapist_id, TherapistAvailability.day_of_week == day_of_week)
        .all()
    )
    working = [(_time_to_minutes(r.start_time), _time_to_minutes(r.end_time)) for r in rows if r.is_available]
    breaks = [(_time_to_minutes(r.start_time), _time_to_minutes(r.end_time)) for r in rows if not r.is_available]
    return working, breaks


def _patient_day_windows(db: Session, *, patient_id: uuid.UUID, day_of_week: int) -> tuple[list, list]:
    rows = (
        db.query(PatientAvailability)
        .filter(PatientAvailability.patient_id == patient_id, PatientAvailability.day_of_week == day_of_week)
        .all()
    )
    not_available = [
        (_time_to_minutes(r.start_time), _time_to_minutes(r.end_time))
        for r in rows
        if r.preference_type == PatientAvailabilityPreference.NOT_AVAILABLE
    ]
    permitted = [
        (_time_to_minutes(r.start_time), _time_to_minutes(r.end_time))
        for r in rows
        if r.preference_type != PatientAvailabilityPreference.NOT_AVAILABLE
    ]
    return not_available, permitted


def _patient_day_windows_batch(
    db: Session, *, patient_ids: list[uuid.UUID], day_of_week: int
) -> dict[uuid.UUID, tuple[list, list]]:
    """Same shape as _patient_day_windows, for every patient in `patient_ids` at once - one query
    instead of one per patient (Phase 10 perf fix: _compute_day_schedule_recommendation used to call
    _patient_day_windows once per appointment in a loop, an N+1 query pattern on the optimizer's
    main hot path, bounded but real at OPTIMIZATION_MAX_APPOINTMENTS_PER_DAY). A patient with no
    rows for this day_of_week simply isn't a key in the result - callers should default to ([], [])
    via `.get(patient_id, ([], []))`, matching _patient_day_windows' own "no rows means
    unrestricted" contract."""
    if not patient_ids:
        return {}
    rows = (
        db.query(PatientAvailability)
        .filter(PatientAvailability.patient_id.in_(patient_ids), PatientAvailability.day_of_week == day_of_week)
        .all()
    )
    result: dict[uuid.UUID, tuple[list, list]] = {}
    for row in rows:
        not_available, permitted = result.setdefault(row.patient_id, ([], []))
        window = (_time_to_minutes(row.start_time), _time_to_minutes(row.end_time))
        if row.preference_type == PatientAvailabilityPreference.NOT_AVAILABLE:
            not_available.append(window)
        else:
            permitted.append(window)
    return result


def build_travel_matrix(
    *, clinic_id: uuid.UUID, therapist: Therapist, patient_points: list[LocationPoint]
) -> list[list[engine.TravelLeg | None]]:
    """(N+1)x(N+1) matrix: node 0 = therapist home (if geocoded), node i+1 = patient_points[i].
    If the therapist has no geocoded home, home-adjacent legs are reported as zero-cost (not
    unreachable) - "starting location when available" per the task, not a hard requirement.

    Public (not `_`-prefixed) because app.services.analytics_service (Phase 8) reuses this exact
    matrix-building logic for its own driving-time calculations - one implementation of "how to
    build a therapist's travel matrix," never a second one that could drift out of sync."""
    n = len(patient_points)
    size = n + 1

    if therapist.home_latitude is not None and therapist.home_longitude is not None:
        home_available = True
        home_lat, home_lng = _require_coords(therapist.home_latitude, therapist.home_longitude)
        all_points = [LocationPoint(latitude=home_lat, longitude=home_lng)] + patient_points
    else:
        home_available = False
        all_points = patient_points

    if len(all_points) >= 2:
        raw = get_travel_time_matrix(clinic_id=clinic_id, points=all_points)
    else:
        raw = [[None]]

    matrix: list[list[engine.TravelLeg | None]] = [[None] * size for _ in range(size)]
    for i in range(size):
        for j in range(size):
            if i == j:
                continue
            if not home_available and (i == 0 or j == 0):
                matrix[i][j] = engine.TravelLeg(minutes=0.0, miles=0.0)
                continue
            ri, rj = (i, j) if home_available else (i - 1, j - 1)
            cell = raw[ri][rj]
            matrix[i][j] = engine.TravelLeg(minutes=cell.duration_minutes, miles=cell.distance_miles) if cell else None
    return matrix


def _compute_day_schedule_recommendation(
    db: Session, *, clinic_id: uuid.UUID, therapist_id: uuid.UUID, target_date: date
) -> dict:
    """The single implementation of "re-order one therapist's one day" - called once for a plain
    DAY_SCHEDULE_OPTIMIZATION request, and once per day (Monday..Sunday) for
    WEEK_SCHEDULE_OPTIMIZATION. Raises _OptimizationInputError for problems that prevent even
    attempting this day (too many appointments, an ungeocoded patient) - the caller decides
    whether that fails the whole request (single-day) or just this one day (weekly)."""
    therapist = db.get(Therapist, therapist_id)
    if therapist is None:
        raise _OptimizationInputError("The therapist for this request could not be found.")

    day_of_week = target_date.weekday()

    appointments = (
        db.query(Appointment)
        .filter(
            Appointment.clinic_id == clinic_id,
            Appointment.therapist_id == therapist_id,
            Appointment.scheduled_date == target_date,
            Appointment.status == AppointmentStatus.SCHEDULED,
        )
        .options(joinedload(Appointment.patient))
        .order_by(Appointment.start_time.asc())
        .all()
    )

    if not appointments:
        return _infeasible_recommendation(
            target_date,
            "NO_APPOINTMENTS",
            "There are no appointments scheduled for this day to optimize.",
            solver_status="OPTIMAL",
        )

    if len(appointments) > settings.OPTIMIZATION_MAX_APPOINTMENTS_PER_DAY:
        raise _OptimizationInputError(
            f"This day has {len(appointments)} appointments, more than the "
            f"{settings.OPTIMIZATION_MAX_APPOINTMENTS_PER_DAY} this optimizer supports at once."
        )

    ungeocoded = sorted(
        {a.patient.full_name for a in appointments if a.patient.latitude is None or a.patient.longitude is None}
    )
    if ungeocoded:
        raise _OptimizationInputError(f"The following patients have not been geocoded yet: {', '.join(ungeocoded)}.")

    working_windows, break_windows = _therapist_day_windows(db, therapist_id=therapist.id, day_of_week=day_of_week)
    patient_windows = _patient_day_windows_batch(
        db, patient_ids=[a.patient_id for a in appointments], day_of_week=day_of_week
    )

    visits = []
    for appt in appointments:
        not_available, permitted = patient_windows.get(appt.patient_id, ([], []))
        allowed = engine.compute_allowed_start_minutes(
            working_windows=working_windows,
            break_windows=break_windows,
            patient_not_available=not_available,
            patient_permitted=permitted,
            duration_minutes=appt.duration_minutes,
        )
        visits.append(
            engine.ScheduledVisit(
                appointment_id=appt.id,
                patient_id=appt.patient_id,
                label=appt.patient.full_name,
                duration_minutes=appt.duration_minutes,
                original_start_minute=_time_to_minutes(appt.start_time),
                allowed_start_minutes=allowed,
            )
        )

    patient_points = [LocationPoint(*_require_coords(a.patient.latitude, a.patient.longitude)) for a in appointments]
    travel_matrix = build_travel_matrix(clinic_id=clinic_id, therapist=therapist, patient_points=patient_points)

    result = engine.optimize_day_schedule(
        visits=visits,
        travel_matrix=travel_matrix,
        max_solve_seconds=settings.OPTIMIZATION_MAX_SOLVE_SECONDS,
        gap_weight=settings.OPTIMIZATION_GAP_WEIGHT,
        change_penalty_weight=settings.OPTIMIZATION_CHANGE_PENALTY_WEIGHT,
    )

    if result.solver_status == "INFEASIBLE":
        reason = result.reason_codes[0] if result.reason_codes else "NO_FEASIBLE_SCHEDULE"
        return _infeasible_recommendation(target_date, reason, result.explanation)

    recommendation_data = {
        "appointments": [
            {
                "appointment_id": str(v.appointment_id),
                "new_scheduled_date": target_date.isoformat(),
                "new_start_time": _minutes_to_time(v.start_minute).isoformat(),
            }
            for v in result.visits
            if v.moved
        ]
    }

    return {
        "target_date": target_date,
        "efficiency_score": result.efficiency_score,
        "total_drive_minutes": result.total_drive_minutes,
        "total_distance_miles": result.total_distance_miles,
        "time_saved_minutes": result.time_saved_minutes,
        "miles_saved": result.miles_saved,
        "marginal_drive_minutes": None,
        "marginal_distance_miles": None,
        "reason_codes": result.reason_codes,
        "explanation": result.explanation,
        "recommendation_data": recommendation_data,
        "solver_status": result.solver_status,
    }


def _run_day_schedule_optimization(db: Session, request: OptimizationRequest) -> list[dict]:
    return [
        _compute_day_schedule_recommendation(
            db, clinic_id=request.clinic_id, therapist_id=request.therapist_id, target_date=request.target_date
        )
    ]


def _run_week_schedule_optimization(db: Session, request: OptimizationRequest) -> list[dict]:
    """Orchestrates _compute_day_schedule_recommendation once per day of the week containing
    request.target_date (snapped to that week's Monday) - no separate weekly algorithm. A day
    that can't even be attempted (_OptimizationInputError) becomes an ERROR-flagged entry for that
    one day rather than failing the whole week; Redis already caches travel-time results per
    clinic+coordinate pair (Phase 5), so patients seen on multiple days this week are only ever
    routed to the provider once."""
    week_start = _start_of_week(request.target_date)
    results = []
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        try:
            results.append(
                _compute_day_schedule_recommendation(
                    db, clinic_id=request.clinic_id, therapist_id=request.therapist_id, target_date=day
                )
            )
        except _OptimizationInputError as exc:
            results.append(_infeasible_recommendation(day, "OPTIMIZATION_ERROR", str(exc), solver_status="ERROR"))
    return results


def _run_new_patient_placement(db: Session, request: OptimizationRequest) -> list[dict]:
    therapist = db.get(Therapist, request.therapist_id)
    patient = db.get(Patient, request.new_patient_id)
    if therapist is None or patient is None:
        raise _OptimizationInputError("The therapist or patient for this request could not be found.")

    # Both are always set for NEW_PATIENT_PLACEMENT requests - enforced in create_request().
    assert request.new_appointment_duration_minutes is not None
    duration_minutes = request.new_appointment_duration_minutes
    search_days = request.search_days or settings.OPTIMIZATION_DEFAULT_SEARCH_DAYS

    if patient.latitude is None or patient.longitude is None:
        raise _OptimizationInputError(f"{patient.full_name} has not been geocoded yet.")

    candidate_dates = [request.target_date + timedelta(days=i) for i in range(search_days)]

    appointments = (
        db.query(Appointment)
        .filter(
            Appointment.clinic_id == request.clinic_id,
            Appointment.therapist_id == therapist.id,
            Appointment.scheduled_date.in_(candidate_dates),
            Appointment.status == AppointmentStatus.SCHEDULED,
        )
        .options(joinedload(Appointment.patient))
        .order_by(Appointment.scheduled_date.asc(), Appointment.start_time.asc())
        .all()
    )
    by_date: dict[date, list[Appointment]] = {}
    for a in appointments:
        by_date.setdefault(a.scheduled_date, []).append(a)

    point_keys: list[str] = []
    points: list[LocationPoint] = []
    if therapist.home_latitude is not None and therapist.home_longitude is not None:
        home_available = True
        point_keys.append(_HOME_KEY)
        points.append(LocationPoint(*_require_coords(therapist.home_latitude, therapist.home_longitude)))
    else:
        home_available = False
    point_keys.append(_NEW_KEY)
    points.append(LocationPoint(*_require_coords(patient.latitude, patient.longitude)))
    for a in appointments:
        if a.patient.latitude is not None and a.patient.longitude is not None:
            point_keys.append(str(a.id))
            points.append(LocationPoint(*_require_coords(a.patient.latitude, a.patient.longitude)))

    pair_cache: dict[tuple[str, str], engine.TravelLeg | None] = {}
    if len(points) >= 2:
        raw_matrix = get_travel_time_matrix(clinic_id=request.clinic_id, points=points)
        for i, ki in enumerate(point_keys):
            for j, kj in enumerate(point_keys):
                if i == j:
                    continue
                cell = raw_matrix[i][j]
                pair_cache[(ki, kj)] = (
                    engine.TravelLeg(minutes=cell.duration_minutes, miles=cell.distance_miles) if cell else None
                )

    def travel_lookup(a: str, b: str) -> engine.TravelLeg | None:
        if a == b:
            return engine.TravelLeg(minutes=0.0, miles=0.0)
        if not home_available and (a == _HOME_KEY or b == _HOME_KEY):
            return engine.TravelLeg(minutes=0.0, miles=0.0)
        return pair_cache.get((a, b))

    availability_cache: dict[int, tuple[list, list]] = {}
    candidate_days = []
    existing_visits_by_date: dict[date, list[engine.ExistingVisit]] = {}
    for target_date in candidate_dates:
        day_of_week = target_date.weekday()
        if day_of_week not in availability_cache:
            availability_cache[day_of_week] = _therapist_day_windows(
                db, therapist_id=therapist.id, day_of_week=day_of_week
            )
        working_windows, break_windows = availability_cache[day_of_week]
        if not working_windows:
            continue

        not_available, permitted = _patient_day_windows(db, patient_id=patient.id, day_of_week=day_of_week)
        allowed = engine.compute_allowed_start_minutes(
            working_windows=working_windows,
            break_windows=break_windows,
            patient_not_available=not_available,
            patient_permitted=permitted,
            duration_minutes=duration_minutes,
        )
        if not allowed:
            continue

        day_appointments = by_date.get(target_date, [])
        existing_visits = [
            engine.ExistingVisit(
                appointment_id=a.id,
                label=a.patient.full_name,
                start_minute=_time_to_minutes(a.start_time),
                end_minute=_time_to_minutes(a.end_time),
            )
            for a in day_appointments
        ]
        existing_visits_by_date[target_date] = existing_visits
        candidate_days.append(
            engine.CandidateDay(target_date=target_date, allowed_start_minutes=allowed, existing_visits=existing_visits)
        )

    if not candidate_days:
        return [
            _infeasible_recommendation(
                request.target_date,
                "NO_FEASIBLE_SLOT",
                f"The therapist has no working days within the next {search_days} days that fit "
                "this patient's availability.",
            )
        ]

    recommendations = engine.recommend_new_patient_slots(
        duration_minutes=duration_minutes, candidate_days=candidate_days, travel_lookup=travel_lookup, top_n=3
    )

    if not recommendations:
        return [
            _infeasible_recommendation(
                request.target_date,
                "NO_FEASIBLE_SLOT",
                "No feasible appointment slot was found for this patient within the search window, "
                "given therapist/patient availability and travel time.",
            )
        ]

    results = []
    for rec in recommendations:
        day_total_minutes, day_total_miles = _day_total_with_insertion(
            existing_visits=existing_visits_by_date.get(rec.target_date, []),
            travel_lookup=travel_lookup,
            new_start_minute=rec.start_minute,
            new_duration_minutes=rec.duration_minutes,
        )
        results.append(
            {
                "target_date": rec.target_date,
                "efficiency_score": rec.efficiency_score,
                # The day's full total AFTER inserting this visit - consistent with what
                # total_drive_minutes/total_distance_miles mean for every other mode.
                "total_drive_minutes": round(day_total_minutes),
                "total_distance_miles": round(day_total_miles, 2),
                "time_saved_minutes": None,
                "miles_saved": None,
                # The portion of the above specifically attributable to this new visit.
                "marginal_drive_minutes": round(rec.added_travel_minutes),
                "marginal_distance_miles": rec.added_distance_miles,
                "reason_codes": rec.reason_codes,
                "explanation": rec.explanation,
                "recommendation_data": {
                    "patient_id": str(patient.id),
                    "therapist_id": str(therapist.id),
                    "scheduled_date": rec.target_date.isoformat(),
                    "start_time": _minutes_to_time(rec.start_minute).isoformat(),
                    "duration_minutes": rec.duration_minutes,
                },
                "solver_status": "FEASIBLE",
            }
        )
    return results


def _day_total_with_insertion(
    *,
    existing_visits: list[engine.ExistingVisit],
    travel_lookup: engine.TravelLookup,
    new_start_minute: int,
    new_duration_minutes: int,
) -> tuple[float, float]:
    """Total (drive_minutes, distance_miles) for one day's existing visits plus one new
    hypothetical visit, all taken in chronological order (never re-optimized) - reuses
    engine.fixed_order_metrics, the same function DAY_SCHEDULE_OPTIMIZATION's time_saved_minutes
    baseline and What-If both use, rather than a new summation routine."""
    keys = [_HOME_KEY] + [str(v.appointment_id) for v in existing_visits] + [_NEW_KEY]
    size = len(keys)
    matrix: list[list[engine.TravelLeg | None]] = [[None] * size for _ in range(size)]
    for i in range(size):
        for j in range(size):
            if i != j:
                matrix[i][j] = travel_lookup(keys[i], keys[j])

    visits = [
        engine.ScheduledVisit(
            appointment_id=v.appointment_id,
            patient_id=uuid.uuid4(),
            label=v.label,
            duration_minutes=v.end_minute - v.start_minute,
            original_start_minute=v.start_minute,
            allowed_start_minutes=[],
        )
        for v in existing_visits
    ] + [
        engine.ScheduledVisit(
            appointment_id=uuid.uuid4(),
            patient_id=uuid.uuid4(),
            label="new",
            duration_minutes=new_duration_minutes,
            original_start_minute=new_start_minute,
            allowed_start_minutes=[],
        )
    ]
    return engine.fixed_order_metrics(visits, matrix)


def run_optimization(db: Session, request_id: uuid.UUID) -> None:
    request = db.query(OptimizationRequest).filter(OptimizationRequest.id == request_id).first()
    if request is None:
        return

    # A redelivered/duplicate Celery message for a request this (or another) worker already
    # started or finished must never recompute and insert a second set of recommendation rows -
    # PENDING is the only status a fresh run is ever allowed to start from.
    if request.status != OptimizationStatus.PENDING:
        app_logger.warning(
            "optimization_run_skipped_not_pending",
            extra={"optimization_request_id": str(request_id), "status": request.status.value},
        )
        return

    request.status = OptimizationStatus.PROCESSING
    db.commit()

    try:
        if request.mode == OptimizationMode.DAY_SCHEDULE_OPTIMIZATION:
            recommendations_data = _run_day_schedule_optimization(db, request)
        elif request.mode == OptimizationMode.WEEK_SCHEDULE_OPTIMIZATION:
            recommendations_data = _run_week_schedule_optimization(db, request)
        else:
            recommendations_data = _run_new_patient_placement(db, request)
    except _OptimizationInputError as exc:
        request.status = OptimizationStatus.FAILED
        request.error_message = str(exc)
        request.completed_at = datetime.now(timezone.utc)
        db.commit()
        return
    except Exception:  # noqa: BLE001 - a background job must never crash silently or leak a stack trace to the client
        app_logger.exception("optimization_run_failed", extra={"optimization_request_id": str(request_id)})
        request.status = OptimizationStatus.FAILED
        request.error_message = "An unexpected error occurred while optimizing this schedule."
        request.completed_at = datetime.now(timezone.utc)
        db.commit()
        return

    # Rank resets per target_date - each day (or the single day/search-window) has its own
    # independent 1..N ranking, not a global rank across the whole request.
    rank_by_date: dict[date, int] = {}
    for rec in recommendations_data:
        rank_by_date[rec["target_date"]] = rank_by_date.get(rec["target_date"], 0) + 1
        db.add(
            OptimizationRecommendation(
                optimization_request_id=request.id,
                target_date=rec["target_date"],
                rank=rank_by_date[rec["target_date"]],
                efficiency_score=rec["efficiency_score"],
                total_drive_minutes=rec["total_drive_minutes"],
                total_distance_miles=rec["total_distance_miles"],
                time_saved_minutes=rec["time_saved_minutes"],
                miles_saved=rec["miles_saved"],
                marginal_drive_minutes=rec["marginal_drive_minutes"],
                marginal_distance_miles=rec["marginal_distance_miles"],
                reason_codes=rec["reason_codes"],
                explanation=rec["explanation"],
                recommendation_data=rec["recommendation_data"],
                solver_status=rec["solver_status"],
            )
        )

    request.status = OptimizationStatus.COMPLETED
    request.completed_at = datetime.now(timezone.utc)
    db.commit()


def _accept_day_schedule(
    db: Session, *, clinic_id: uuid.UUID, recommendation: OptimizationRecommendation
) -> list[uuid.UUID]:
    changes = recommendation.recommendation_data.get("appointments", [])
    if not changes:
        return []  # "already optimal" recommendation - a valid no-op accept

    change_map: dict[uuid.UUID, tuple[date, time]] = {
        uuid.UUID(c["appointment_id"]): (
            date.fromisoformat(c["new_scheduled_date"]),
            time.fromisoformat(c["new_start_time"]),
        )
        for c in changes
    }

    first_id = next(iter(change_map))
    anchor = appointment_service.get_appointment(db, clinic_id=clinic_id, appointment_id=first_id)
    target_date = anchor.scheduled_date

    current_appointments = (
        db.query(Appointment)
        .filter(
            Appointment.clinic_id == clinic_id,
            Appointment.therapist_id == anchor.therapist_id,
            Appointment.scheduled_date == target_date,
            Appointment.status == AppointmentStatus.SCHEDULED,
        )
        .all()
    )
    current_ids = {a.id for a in current_appointments}
    if not change_map.keys() <= current_ids:
        raise BusinessRuleError(
            "The schedule has changed since this recommendation was generated. Please re-run optimization.",
            code="STALE_RECOMMENDATION",
        )

    # Compute the FINAL proposed (start, end) for every appointment that day at once (changed ones
    # get their new time, unchanged ones keep their current time), then check the whole day for
    # overlaps together. Re-validating one changed appointment at a time against the *current* DB
    # state would produce false conflicts whenever two appointments are effectively swapping
    # slots - each would still see the other's pre-move (soon-to-be-vacated) time as "existing."
    proposed_ranges: dict[uuid.UUID, tuple[time, time]] = {}
    for appt in current_appointments:
        if appt.id in change_map:
            _, new_start = change_map[appt.id]
            new_end = _add_minutes(new_start, appt.duration_minutes)
            if new_end is None:
                raise BusinessRuleError(
                    "The schedule has changed since this recommendation was generated. Please re-run optimization.",
                    code="STALE_RECOMMENDATION",
                )
            proposed_ranges[appt.id] = (new_start, new_end)
        else:
            proposed_ranges[appt.id] = (appt.start_time, appt.end_time)

    ids_ordered = list(proposed_ranges.keys())
    for i in range(len(ids_ordered)):
        s1, e1 = proposed_ranges[ids_ordered[i]]
        for j in range(i + 1, len(ids_ordered)):
            s2, e2 = proposed_ranges[ids_ordered[j]]
            if s1 < e2 and s2 < e1:
                raise BusinessRuleError(
                    "The schedule has changed since this recommendation was generated. Please re-run optimization.",
                    code="STALE_RECOMMENDATION",
                )

    appointments_by_id = {a.id: a for a in current_appointments}
    for appointment_id, (new_date, new_start) in change_map.items():
        appt = appointments_by_id[appointment_id]
        new_end = proposed_ranges[appointment_id][1]
        day_of_week = new_date.weekday()

        working_rows = (
            db.query(TherapistAvailability)
            .filter(
                TherapistAvailability.therapist_id == appt.therapist_id,
                TherapistAvailability.day_of_week == day_of_week,
            )
            .all()
        )
        working_rules = [TimeRange(r.start_time, r.end_time) for r in working_rows if r.is_available]
        breaks = [TimeRange(r.start_time, r.end_time) for r in working_rows if not r.is_available]
        errors = check_therapist_working_hours(working_rules, breaks, new_start, new_end)

        pa_rows = (
            db.query(PatientAvailability)
            .filter(PatientAvailability.patient_id == appt.patient_id, PatientAvailability.day_of_week == day_of_week)
            .all()
        )
        pa_rules = [(TimeRange(r.start_time, r.end_time), r.preference_type) for r in pa_rows]
        errors += check_patient_availability(pa_rules, new_start, new_end)

        if errors:
            raise BusinessRuleError(
                "The schedule has changed since this recommendation was generated. Please re-run optimization.",
                code="STALE_RECOMMENDATION",
                details={"errors": errors},
            )

    appointment_ids = []
    for appointment_id, (new_date, new_start) in change_map.items():
        appt = appointments_by_id[appointment_id]
        appt.scheduled_date = new_date
        appt.start_time = new_start
        appt.end_time = proposed_ranges[appointment_id][1]
        appointment_ids.append(appt.id)

    db.commit()
    return appointment_ids


def _accept_new_patient_placement(
    db: Session, *, clinic_id: uuid.UUID, created_by: uuid.UUID, recommendation: OptimizationRecommendation
) -> list[uuid.UUID]:
    data = recommendation.recommendation_data
    payload = AppointmentCreate(
        patient_id=uuid.UUID(data["patient_id"]),
        therapist_id=uuid.UUID(data["therapist_id"]),
        scheduled_date=date.fromisoformat(data["scheduled_date"]),
        start_time=time.fromisoformat(data["start_time"]),
        duration_minutes=data["duration_minutes"],
    )
    try:
        appointment = appointment_service.create_appointment(
            db, clinic_id=clinic_id, created_by=created_by, data=payload
        )
    except BusinessRuleError as exc:
        raise BusinessRuleError(
            "The schedule has changed since this recommendation was generated. Please re-run "
            f"optimization. ({exc.message})",
            code="STALE_RECOMMENDATION",
            details=exc.details,
        ) from exc
    return [appointment.id]


def accept_recommendation(
    db: Session,
    *,
    clinic_id: uuid.UUID,
    request_id: uuid.UUID,
    recommendation_id: uuid.UUID,
    current_user: User,
    restrict_to_therapist_id: uuid.UUID | None = None,
) -> tuple[OptimizationRecommendation, list[uuid.UUID]]:
    request = get_request(
        db, clinic_id=clinic_id, request_id=request_id, restrict_to_therapist_id=restrict_to_therapist_id
    )

    if request.status != OptimizationStatus.COMPLETED:
        raise BusinessRuleError("This optimization request has not completed yet.", code="OPTIMIZATION_NOT_COMPLETED")

    recommendation = (
        db.query(OptimizationRecommendation)
        .filter(
            OptimizationRecommendation.id == recommendation_id,
            OptimizationRecommendation.optimization_request_id == request.id,
        )
        .first()
    )
    if recommendation is None:
        raise NotFoundError("Recommendation was not found.", code="RECOMMENDATION_NOT_FOUND")
    if recommendation.accepted_at is not None:
        raise ConflictError("This recommendation has already been accepted.", code="RECOMMENDATION_ALREADY_ACCEPTED")
    if recommendation.solver_status in ("INFEASIBLE", "ERROR") or not recommendation.recommendation_data:
        raise BusinessRuleError("This recommendation has no schedule to apply.", code="RECOMMENDATION_NOT_ACTIONABLE")

    # NEW_PATIENT_PLACEMENT's up to 3 ranked alternatives all propose scheduling the *same* new
    # patient - accepting one must block the others. DAY_SCHEDULE_OPTIMIZATION and
    # WEEK_SCHEDULE_OPTIMIZATION never have competing recommendations for the same date by
    # construction (exactly one per date), so no such check is needed for them.
    if request.mode == OptimizationMode.NEW_PATIENT_PLACEMENT:
        sibling_accepted = (
            db.query(OptimizationRecommendation)
            .filter(
                OptimizationRecommendation.optimization_request_id == request.id,
                OptimizationRecommendation.id != recommendation.id,
                OptimizationRecommendation.accepted_at.isnot(None),
            )
            .first()
        )
        if sibling_accepted is not None:
            raise ConflictError(
                "Another recommendation for this new patient has already been accepted.",
                code="RECOMMENDATION_ALREADY_ACCEPTED",
            )

    if request.mode == OptimizationMode.NEW_PATIENT_PLACEMENT:
        appointment_ids = _accept_new_patient_placement(
            db, clinic_id=clinic_id, created_by=current_user.id, recommendation=recommendation
        )
    else:
        appointment_ids = _accept_day_schedule(db, clinic_id=clinic_id, recommendation=recommendation)

    recommendation.accepted_at = datetime.now(timezone.utc)
    recommendation.rejected_at = None  # accepting supersedes an earlier change-of-mind rejection
    audit_service.record(
        db,
        clinic_id=clinic_id,
        user_id=current_user.id,
        action="OPTIMIZATION_RECOMMENDATION_ACCEPTED",
        entity_type="OPTIMIZATION_RECOMMENDATION",
        entity_id=recommendation.id,
        new_value={"mode": request.mode.value, "appointments_changed": len(appointment_ids)},
    )
    db.commit()
    db.refresh(recommendation)
    return recommendation, appointment_ids


def reject_recommendation(
    db: Session,
    *,
    clinic_id: uuid.UUID,
    request_id: uuid.UUID,
    recommendation_id: uuid.UUID,
    restrict_to_therapist_id: uuid.UUID | None = None,
) -> OptimizationRecommendation:
    get_request(db, clinic_id=clinic_id, request_id=request_id, restrict_to_therapist_id=restrict_to_therapist_id)

    recommendation = (
        db.query(OptimizationRecommendation)
        .filter(
            OptimizationRecommendation.id == recommendation_id,
            OptimizationRecommendation.optimization_request_id == request_id,
        )
        .first()
    )
    if recommendation is None:
        raise NotFoundError("Recommendation was not found.", code="RECOMMENDATION_NOT_FOUND")
    if recommendation.accepted_at is not None:
        raise ConflictError("An accepted recommendation cannot be rejected.", code="RECOMMENDATION_ALREADY_ACCEPTED")

    recommendation.rejected_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(recommendation)
    return recommendation


def _day_metrics(
    db: Session,
    *,
    clinic_id: uuid.UUID,
    therapist_id: uuid.UUID,
    target_date: date,
    exclude_appointment_id: uuid.UUID | None = None,
    extra_visit: tuple[uuid.UUID, uuid.UUID, str, int, time] | None = None,
    override_start_time: dict[uuid.UUID, time] | None = None,
) -> tuple[float, float]:
    """Total (drive_minutes, distance_miles) for `therapist_id`'s SCHEDULED appointments on
    `target_date`, taken in chronological order (never re-optimized) - the metric What-If uses for
    both the "current" and "hypothetical" side of a comparison.

    `exclude_appointment_id` drops one appointment (e.g. the one being moved/removed);
    `extra_visit` = (appointment_id, patient_id, label, duration_minutes, start_time) adds one
    hypothetical visit not actually in the DB; `override_start_time` changes one existing
    appointment's time in this calculation only, never in the database.
    """
    query = db.query(Appointment).filter(
        Appointment.clinic_id == clinic_id,
        Appointment.therapist_id == therapist_id,
        Appointment.scheduled_date == target_date,
        Appointment.status == AppointmentStatus.SCHEDULED,
    )
    if exclude_appointment_id is not None:
        query = query.filter(Appointment.id != exclude_appointment_id)
    appointments = query.options(joinedload(Appointment.patient)).all()

    geocoded = [a for a in appointments if a.patient.latitude is not None and a.patient.longitude is not None]

    visits = [
        engine.ScheduledVisit(
            appointment_id=a.id,
            patient_id=a.patient_id,
            label=a.patient.full_name,
            duration_minutes=a.duration_minutes,
            original_start_minute=_time_to_minutes((override_start_time or {}).get(a.id, a.start_time)),
            allowed_start_minutes=[],
        )
        for a in geocoded
    ]
    patient_points = [LocationPoint(*_require_coords(a.patient.latitude, a.patient.longitude)) for a in geocoded]

    if extra_visit is not None:
        appointment_id, patient_id, label, duration_minutes, start_time = extra_visit
        patient = db.get(Patient, patient_id)
        if patient is not None and patient.latitude is not None and patient.longitude is not None:
            visits.append(
                engine.ScheduledVisit(
                    appointment_id=appointment_id,
                    patient_id=patient_id,
                    label=label,
                    duration_minutes=duration_minutes,
                    original_start_minute=_time_to_minutes(start_time),
                    allowed_start_minutes=[],
                )
            )
            patient_points.append(LocationPoint(*_require_coords(patient.latitude, patient.longitude)))

    if not visits:
        return 0.0, 0.0

    therapist = db.get(Therapist, therapist_id)
    assert therapist is not None  # already validated by the caller before _day_metrics is ever invoked
    travel_matrix = build_travel_matrix(clinic_id=clinic_id, therapist=therapist, patient_points=patient_points)
    return engine.fixed_order_metrics(visits, travel_matrix)


def _what_if_conflicts(
    db: Session, *, clinic_id: uuid.UUID, data: WhatIfRequest, restrict_to_therapist_id: uuid.UUID | None
) -> tuple[list[str], Appointment | None]:
    """Feasibility check shared by evaluate_what_if and apply_what_if, so a scenario evaluate says
    is feasible can never turn out infeasible at apply time just because the checks drifted apart.
    Returns (conflicts, the existing appointment involved - None for ADD)."""
    if data.scenario_type in (WhatIfScenarioType.REMOVE, WhatIfScenarioType.MOVE):
        assert data.appointment_id is not None  # enforced by WhatIfRequest's own validator
        appointment = appointment_service.get_appointment(
            db,
            clinic_id=clinic_id,
            appointment_id=data.appointment_id,
            restrict_to_therapist_id=restrict_to_therapist_id,
        )

    if data.scenario_type == WhatIfScenarioType.REMOVE:
        return [], appointment

    if data.scenario_type == WhatIfScenarioType.MOVE:
        conflicts = appointment_service.validate_appointment(
            db,
            clinic_id=clinic_id,
            therapist_id=appointment.therapist_id,
            patient_id=appointment.patient_id,
            scheduled_date=data.new_scheduled_date,  # type: ignore[arg-type]
            start_time=data.new_start_time,  # type: ignore[arg-type]
            duration_minutes=data.new_duration_minutes or appointment.duration_minutes,
            exclude_appointment_id=appointment.id,
        )
        return conflicts, appointment

    # ADD
    if restrict_to_therapist_id is not None and data.therapist_id != restrict_to_therapist_id:
        return ["Therapists can only test adding appointments to their own schedule."], None
    conflicts = appointment_service.validate_appointment(
        db,
        clinic_id=clinic_id,
        therapist_id=data.therapist_id,  # type: ignore[arg-type]
        patient_id=data.patient_id,  # type: ignore[arg-type]
        scheduled_date=data.new_scheduled_date,  # type: ignore[arg-type]
        start_time=data.new_start_time,  # type: ignore[arg-type]
        duration_minutes=data.new_duration_minutes,  # type: ignore[arg-type]
    )
    return conflicts, None


def evaluate_what_if(
    db: Session, *, clinic_id: uuid.UUID, data: WhatIfRequest, restrict_to_therapist_id: uuid.UUID | None = None
) -> WhatIfResponse:
    """Stateless - never writes to the database. Reuses the exact same hard-constraint validation
    create/update/cancel would run, so a scenario marked feasible here is guaranteed to actually
    succeed if applied immediately after (barring a real race with another change)."""
    conflicts, appointment = _what_if_conflicts(
        db, clinic_id=clinic_id, data=data, restrict_to_therapist_id=restrict_to_therapist_id
    )
    feasible = not conflicts

    days: list[WhatIfDayImpact] = []
    affected_ids: list[uuid.UUID] = []

    if feasible and data.scenario_type == WhatIfScenarioType.REMOVE:
        assert appointment is not None
        affected_ids = [appointment.id]
        current_minutes, current_miles = _day_metrics(
            db, clinic_id=clinic_id, therapist_id=appointment.therapist_id, target_date=appointment.scheduled_date
        )
        proposed_minutes, proposed_miles = _day_metrics(
            db,
            clinic_id=clinic_id,
            therapist_id=appointment.therapist_id,
            target_date=appointment.scheduled_date,
            exclude_appointment_id=appointment.id,
        )
        days.append(
            WhatIfDayImpact(
                target_date=appointment.scheduled_date,
                current_drive_minutes=round(current_minutes, 1),
                proposed_drive_minutes=round(proposed_minutes, 1),
                current_distance_miles=round(current_miles, 2),
                proposed_distance_miles=round(proposed_miles, 2),
            )
        )

    elif feasible and data.scenario_type == WhatIfScenarioType.ADD:
        patient = patient_service.get_patient(db, clinic_id=clinic_id, patient_id=data.patient_id)  # type: ignore[arg-type]
        current_minutes, current_miles = _day_metrics(
            db, clinic_id=clinic_id, therapist_id=data.therapist_id, target_date=data.new_scheduled_date  # type: ignore[arg-type]
        )
        proposed_minutes, proposed_miles = _day_metrics(
            db,
            clinic_id=clinic_id,
            therapist_id=data.therapist_id,  # type: ignore[arg-type]
            target_date=data.new_scheduled_date,  # type: ignore[arg-type]
            extra_visit=(
                uuid.uuid4(),
                patient.id,
                patient.full_name,
                data.new_duration_minutes,  # type: ignore[arg-type]
                data.new_start_time,  # type: ignore[arg-type]
            ),
        )
        days.append(
            WhatIfDayImpact(
                target_date=data.new_scheduled_date,  # type: ignore[arg-type]
                current_drive_minutes=round(current_minutes, 1),
                proposed_drive_minutes=round(proposed_minutes, 1),
                current_distance_miles=round(current_miles, 2),
                proposed_distance_miles=round(proposed_miles, 2),
            )
        )

    elif feasible and data.scenario_type == WhatIfScenarioType.MOVE:
        assert appointment is not None
        affected_ids = [appointment.id]
        if data.new_scheduled_date == appointment.scheduled_date:
            current_minutes, current_miles = _day_metrics(
                db, clinic_id=clinic_id, therapist_id=appointment.therapist_id, target_date=appointment.scheduled_date
            )
            proposed_minutes, proposed_miles = _day_metrics(
                db,
                clinic_id=clinic_id,
                therapist_id=appointment.therapist_id,
                target_date=appointment.scheduled_date,
                override_start_time={appointment.id: data.new_start_time},  # type: ignore[dict-item]
            )
            days.append(
                WhatIfDayImpact(
                    target_date=appointment.scheduled_date,
                    current_drive_minutes=round(current_minutes, 1),
                    proposed_drive_minutes=round(proposed_minutes, 1),
                    current_distance_miles=round(current_miles, 2),
                    proposed_distance_miles=round(proposed_miles, 2),
                )
            )
        else:
            origin_current_minutes, origin_current_miles = _day_metrics(
                db, clinic_id=clinic_id, therapist_id=appointment.therapist_id, target_date=appointment.scheduled_date
            )
            origin_proposed_minutes, origin_proposed_miles = _day_metrics(
                db,
                clinic_id=clinic_id,
                therapist_id=appointment.therapist_id,
                target_date=appointment.scheduled_date,
                exclude_appointment_id=appointment.id,
            )
            days.append(
                WhatIfDayImpact(
                    target_date=appointment.scheduled_date,
                    current_drive_minutes=round(origin_current_minutes, 1),
                    proposed_drive_minutes=round(origin_proposed_minutes, 1),
                    current_distance_miles=round(origin_current_miles, 2),
                    proposed_distance_miles=round(origin_proposed_miles, 2),
                )
            )

            dest_current_minutes, dest_current_miles = _day_metrics(
                db, clinic_id=clinic_id, therapist_id=appointment.therapist_id, target_date=data.new_scheduled_date  # type: ignore[arg-type]
            )
            dest_proposed_minutes, dest_proposed_miles = _day_metrics(
                db,
                clinic_id=clinic_id,
                therapist_id=appointment.therapist_id,
                target_date=data.new_scheduled_date,  # type: ignore[arg-type]
                extra_visit=(
                    appointment.id,
                    appointment.patient_id,
                    appointment.patient.full_name,
                    data.new_duration_minutes or appointment.duration_minutes,
                    data.new_start_time,  # type: ignore[arg-type]
                ),
            )
            days.append(
                WhatIfDayImpact(
                    target_date=data.new_scheduled_date,  # type: ignore[arg-type]
                    current_drive_minutes=round(dest_current_minutes, 1),
                    proposed_drive_minutes=round(dest_proposed_minutes, 1),
                    current_distance_miles=round(dest_current_miles, 2),
                    proposed_distance_miles=round(dest_proposed_miles, 2),
                )
            )

    total_time_impact = (
        round(sum(d.proposed_drive_minutes - d.current_drive_minutes for d in days), 1) if days else None
    )
    total_distance_impact = (
        round(sum(d.proposed_distance_miles - d.current_distance_miles for d in days), 2) if days else None
    )

    return WhatIfResponse(
        feasible=feasible,
        conflicts=conflicts,
        days=days,
        total_time_impact_minutes=total_time_impact,
        total_distance_impact_miles=total_distance_impact,
        affected_appointment_ids=affected_ids,
    )


def apply_what_if(
    db: Session,
    *,
    clinic_id: uuid.UUID,
    created_by: uuid.UUID,
    data: WhatIfRequest,
    restrict_to_therapist_id: uuid.UUID | None = None,
) -> tuple[bool, uuid.UUID | None, str]:
    """Revalidates against the live database (never a cached What-If result) and, if still
    feasible, applies the change transactionally via the same appointment_service functions
    every other mutation path uses. Returns (applied, appointment_id, message)."""
    conflicts, appointment = _what_if_conflicts(
        db, clinic_id=clinic_id, data=data, restrict_to_therapist_id=restrict_to_therapist_id
    )
    if conflicts:
        return False, None, "The schedule has changed since this scenario was calculated. " + " ".join(conflicts)

    if data.scenario_type == WhatIfScenarioType.REMOVE:
        assert appointment is not None
        appointment_service.cancel_appointment(
            db,
            clinic_id=clinic_id,
            appointment_id=appointment.id,
            restrict_to_therapist_id=restrict_to_therapist_id,
            actor_user_id=created_by,
        )
        return True, appointment.id, "Appointment cancelled."

    if data.scenario_type == WhatIfScenarioType.MOVE:
        assert appointment is not None
        current_user = db.get(User, created_by)
        assert current_user is not None
        try:
            update_fields: dict = {"scheduled_date": data.new_scheduled_date, "start_time": data.new_start_time}
            if data.new_duration_minutes is not None:
                update_fields["duration_minutes"] = data.new_duration_minutes
            updated = appointment_service.update_appointment(
                db,
                clinic_id=clinic_id,
                appointment_id=appointment.id,
                data=AppointmentUpdate(**update_fields),
                current_user=current_user,
                restrict_to_therapist_id=restrict_to_therapist_id,
            )
        except BusinessRuleError as exc:
            return False, None, f"The schedule has changed since this scenario was calculated. ({exc.message})"
        return True, updated.id, "Appointment rescheduled."

    # ADD
    try:
        payload = AppointmentCreate(
            patient_id=data.patient_id,  # type: ignore[arg-type]
            therapist_id=data.therapist_id,  # type: ignore[arg-type]
            scheduled_date=data.new_scheduled_date,  # type: ignore[arg-type]
            start_time=data.new_start_time,  # type: ignore[arg-type]
            duration_minutes=data.new_duration_minutes,  # type: ignore[arg-type]
        )
        created = appointment_service.create_appointment(db, clinic_id=clinic_id, created_by=created_by, data=payload)
    except BusinessRuleError as exc:
        return False, None, f"The schedule has changed since this scenario was calculated. ({exc.message})"
    return True, created.id, "Appointment created."
