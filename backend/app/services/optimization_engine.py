"""
RouteCare AI - Pure schedule-optimization algorithms (Phase 6).

No DB session, no HTTP, no travel-time-provider calls anywhere in this
module - every function takes already-resolved plain data (durations,
allowed time windows, a travel-time lookup) and returns a ranked list
of proposals. This mirrors app.services.scheduling_validation's
architecture: the algorithm is a pure function, directly unit-testable
with hand-built inputs, while app.services.optimization_service (the
DB/orchestration layer) fetches real data, calls into here, and
persists the result. Nothing here ever mutates an appointment - these
functions only ever *compute a proposal*.

Two independent algorithms, matched to two different problem shapes:

- `optimize_day_schedule` (OptimizationMode.DAY_SCHEDULE_OPTIMIZATION):
  a genuine constraint-optimization problem - N *existing* appointments
  for one therapist on one day, decide the best order and timing within
  each appointment's allowed window to minimize total drive time. Solved
  with OR-Tools CP-SAT - see that function's docstring for the exact
  model. Existing appointments may be reordered/retimed but never added
  or removed; a moved-appointment count feeds the objective as a
  "preserve the existing schedule" soft constraint.

- `recommend_new_patient_slots` (OptimizationMode.NEW_PATIENT_PLACEMENT):
  a bounded insertion-point search, deliberately NOT run through the
  solver - this mode never disturbs any existing appointment (the
  hardest possible "preserve existing schedule" guarantee), so the
  problem reduces to evaluating a small, fixed number of candidate
  insertion points (before the first visit, between each consecutive
  pair, after the last) per candidate day and ranking them by marginal
  added travel time. A full CP-SAT model would be strictly more
  machinery for the same answer here.

Objective function (`optimize_day_schedule`), all weights configurable
via Settings (app.core.config) rather than hardcoded:

    minimize:  total_drive_minutes * SCALE
             + total_gap_minutes   * (OPTIMIZATION_GAP_WEIGHT * SCALE)
             + appointments_moved  * (OPTIMIZATION_CHANGE_PENALTY_WEIGHT * SCALE)

total_drive_minutes is the anchor at an implicit weight of 1.0, per the
task's explicit "primary objective is minimize travel/driving time."
Distance is reported (for the efficiency-metrics output) but not a
separate weighted term - it's tightly correlated with drive time from
the same routing calculation, and mixing minutes and miles in one
linear objective would need an arbitrary unit-conversion weight that
doesn't add real scheduling value.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from ortools.sat.python import cp_model

MINUTES_PER_DAY = 24 * 60
_UNREACHABLE_PENALTY_MINUTES = 10_000  # effectively forbids an arc without structurally banning it
_OBJECTIVE_SCALE = 100  # integer-scale the (possibly fractional) configurable weights for CP-SAT


def subtract_intervals(base: list[tuple[int, int]], remove: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Remove each interval in `remove` from the intervals in `base`, returning the remaining
    free sub-intervals. All intervals are [start, end) minute ranges."""
    result = list(base)
    for r_start, r_end in remove:
        next_result = []
        for b_start, b_end in result:
            if r_end <= b_start or r_start >= b_end:
                next_result.append((b_start, b_end))
                continue
            if r_start > b_start:
                next_result.append((b_start, r_start))
            if r_end < b_end:
                next_result.append((r_end, b_end))
        result = next_result
    return result


def intersect_intervals(a: list[tuple[int, int]], b: list[tuple[int, int]]) -> list[tuple[int, int]]:
    result = []
    for a_start, a_end in a:
        for b_start, b_end in b:
            lo, hi = max(a_start, b_start), min(a_end, b_end)
            if lo < hi:
                result.append((lo, hi))
    return result


def compute_allowed_start_minutes(
    *,
    working_windows: list[tuple[int, int]],
    break_windows: list[tuple[int, int]],
    patient_not_available: list[tuple[int, int]],
    patient_permitted: list[tuple[int, int]],
    duration_minutes: int,
) -> list[tuple[int, int]]:
    """Valid START-time minute ranges (inclusive on both ends) such that an appointment of
    `duration_minutes` starting anywhere in a returned range fits fully within therapist working
    hours (minus breaks) and, if any patient availability is configured for the day, within it too
    - same semantics as app.services.scheduling_validation.check_therapist_working_hours/
    check_patient_availability, expressed as computable ranges instead of a single pass/fail.

    Empty `working_windows` means the therapist doesn't work this day at all - always returns []
    (never a start time). Empty `patient_permitted` means no PREFERRED/AVAILABLE rows are
    configured for the day - patient availability is unrestricted (only patient_not_available, if
    any, still applies), matching the flexible-by-default homecare scheduling model.
    """
    if not working_windows:
        return []

    free = subtract_intervals(working_windows, break_windows)
    if patient_not_available:
        free = subtract_intervals(free, patient_not_available)
    if patient_permitted:
        free = intersect_intervals(free, patient_permitted)

    ranges = []
    for start, end in free:
        latest_start = end - duration_minutes
        if latest_start >= start:
            ranges.append((start, latest_start))
    return ranges


@dataclass(frozen=True)
class TravelLeg:
    minutes: float
    miles: float


@dataclass(frozen=True)
class ScheduledVisit:
    """One existing appointment being considered for reordering. Only what the algorithm needs -
    never patient PII beyond an opaque id/display label the caller already resolved."""

    appointment_id: uuid.UUID
    patient_id: uuid.UUID
    label: str
    duration_minutes: int
    original_start_minute: int
    # Valid START-time ranges (inclusive), already the intersection of therapist working hours
    # (minus breaks) and patient availability for this specific day - see
    # app.services.optimization_service._compute_allowed_start_minutes.
    allowed_start_minutes: list[tuple[int, int]]


@dataclass(frozen=True)
class ProposedVisitTime:
    appointment_id: uuid.UUID
    patient_id: uuid.UUID
    label: str
    start_minute: int
    duration_minutes: int
    original_start_minute: int

    @property
    def moved(self) -> bool:
        return self.start_minute != self.original_start_minute


@dataclass(frozen=True)
class DayScheduleResult:
    solver_status: str  # "OPTIMAL" | "FEASIBLE" | "INFEASIBLE"
    visits: list[ProposedVisitTime]
    total_drive_minutes: int
    total_distance_miles: float
    gap_minutes: int
    appointments_moved: int
    efficiency_score: float
    time_saved_minutes: int | None
    miles_saved: float | None
    reason_codes: list[str] = field(default_factory=list)
    explanation: str = ""


def _efficiency_score(total_drive_minutes: float, visit_count: int) -> float:
    """Simple, explainable heuristic (not a validated industry metric): each average minute of
    driving per visit costs one point off a 100 baseline. Documented as a heuristic on purpose -
    matches docs/07_AI_Optimization_Engine.md's own illustrative (not formally derived) percentages."""
    if visit_count == 0:
        return 100.0
    per_visit = total_drive_minutes / visit_count
    return max(0.0, min(100.0, 100.0 - per_visit))


def _leg_minutes(travel_matrix: list[list[TravelLeg | None]], a: int, b: int) -> tuple[int, bool]:
    leg = travel_matrix[a][b]
    if leg is None:
        return _UNREACHABLE_PENALTY_MINUTES, True
    return round(leg.minutes), False


@dataclass(frozen=True)
class RouteLeg:
    """One traveled leg of a chronological route - see fixed_order_legs. `from_node`/`to_node`
    use the same node numbering as travel_matrix (0 = home/start location, i+1 = visits[i]), so a
    caller can distinguish a home-adjacent leg (either endpoint is 0) from a purely
    inter-appointment leg - e.g. Phase 8 analytics reports "total driving" including home legs but
    "average travel between appointments" excluding them, without a second traversal."""

    from_node: int
    to_node: int
    minutes: float
    miles: float


def fixed_order_legs(
    visits: list[ScheduledVisit], travel_matrix: list[list[TravelLeg | None]]
) -> list[RouteLeg]:
    """The leg-by-leg breakdown of `visits` taken in their *original_start_minute* order - i.e.
    without any reordering. A leg whose matrix cell is None (unreachable/uncalculated) is simply
    omitted, matching fixed_order_metrics' existing "skip it" behavior. Node 0 in travel_matrix is
    always home/start location; visit i is node i+1."""
    order = sorted(range(len(visits)), key=lambda i: visits[i].original_start_minute)
    legs: list[RouteLeg] = []
    prev_node = 0
    for i in order:
        leg = travel_matrix[prev_node][i + 1]
        if leg is not None:
            legs.append(RouteLeg(from_node=prev_node, to_node=i + 1, minutes=leg.minutes, miles=leg.miles))
        prev_node = i + 1
    return legs


def fixed_order_metrics(
    visits: list[ScheduledVisit], travel_matrix: list[list[TravelLeg | None]]
) -> tuple[float, float]:
    """Total (drive_minutes, distance_miles) of `visits` taken in their *original_start_minute*
    order - i.e. without any reordering. Used both as the DAY_SCHEDULE_OPTIMIZATION baseline for
    time_saved_minutes/miles_saved, and directly by the What-If evaluation (which never re-orders
    anything, only asks "what does this day cost as currently/hypothetically scheduled").
    Node 0 in travel_matrix is always home/start location; visit i is node i+1."""
    legs = fixed_order_legs(visits, travel_matrix)
    return sum(leg.minutes for leg in legs), sum(leg.miles for leg in legs)


def _baseline_drive_minutes(visits: list[ScheduledVisit], travel_matrix: list[list[TravelLeg | None]]) -> float:
    return fixed_order_metrics(visits, travel_matrix)[0]


def _baseline_distance_miles(visits: list[ScheduledVisit], travel_matrix: list[list[TravelLeg | None]]) -> float:
    return fixed_order_metrics(visits, travel_matrix)[1]


def optimize_day_schedule(
    *,
    visits: list[ScheduledVisit],
    travel_matrix: list[list[TravelLeg | None]],
    max_solve_seconds: float = 10.0,
    gap_weight: float = 0.1,
    change_penalty_weight: float = 2.0,
) -> DayScheduleResult:
    """Re-order/re-time `visits` (all belonging to one therapist, one day) to minimize total drive
    time. `travel_matrix` is (N+1) x (N+1): index 0 is the therapist's home/start location, index
    i+1 is `visits[i]`. Returns solver_status="INFEASIBLE" (empty visits) if no ordering satisfies
    every appointment's allowed_start_minutes and the required inter-visit travel time - this is a
    hard-constraint model, never silently violated to produce an answer.
    """
    n = len(visits)
    if n == 0:
        return DayScheduleResult(
            solver_status="OPTIMAL",
            visits=[],
            total_drive_minutes=0,
            total_distance_miles=0.0,
            gap_minutes=0,
            appointments_moved=0,
            efficiency_score=100.0,
            time_saved_minutes=0,
            miles_saved=0.0,
            reason_codes=["NO_APPOINTMENTS"],
            explanation="There are no appointments to optimize for this day.",
        )

    if n == 1:
        v = visits[0]
        if not any(lo <= v.original_start_minute <= hi for lo, hi in v.allowed_start_minutes):
            return DayScheduleResult(
                solver_status="INFEASIBLE",
                visits=[],
                total_drive_minutes=0,
                total_distance_miles=0.0,
                gap_minutes=0,
                appointments_moved=0,
                efficiency_score=0.0,
                time_saved_minutes=None,
                miles_saved=None,
                reason_codes=["NO_FEASIBLE_SCHEDULE"],
                explanation=(
                    f"{v.label}'s appointment no longer fits therapist availability or patient "
                    "availability for this day."
                ),
            )
        leg = travel_matrix[0][1]
        drive = round(leg.minutes) if leg is not None else 0
        miles = round(leg.miles, 2) if leg is not None else 0.0
        single_visit = ProposedVisitTime(
            appointment_id=v.appointment_id,
            patient_id=v.patient_id,
            label=v.label,
            start_minute=v.original_start_minute,
            duration_minutes=v.duration_minutes,
            original_start_minute=v.original_start_minute,
        )
        return DayScheduleResult(
            solver_status="OPTIMAL",
            visits=[single_visit],
            total_drive_minutes=drive,
            total_distance_miles=miles,
            gap_minutes=0,
            appointments_moved=0,
            efficiency_score=_efficiency_score(drive, 1),
            time_saved_minutes=0,
            miles_saved=0.0,
            reason_codes=["SINGLE_APPOINTMENT"],
            explanation=f"Only one appointment ({v.label}) is scheduled this day - there is nothing to reorder.",
        )

    # Pre-check: a visit with zero reachable connections (to home or any other visit, in either
    # direction) can never be placed in any route - report this distinctly and immediately,
    # instead of asking the solver to discover the same thing the hard way.
    for i, v in enumerate(visits):
        node = i + 1
        if not any(
            travel_matrix[node][other] is not None or travel_matrix[other][node] is not None
            for other in range(n + 1)
            if other != node
        ):
            return DayScheduleResult(
                solver_status="INFEASIBLE",
                visits=[],
                total_drive_minutes=0,
                total_distance_miles=0.0,
                gap_minutes=0,
                appointments_moved=0,
                efficiency_score=0.0,
                time_saved_minutes=None,
                miles_saved=None,
                reason_codes=["UNREACHABLE_LOCATION"],
                explanation=f"{v.label}'s location is not reachable by driving route from the therapist's "
                f"starting location or any other appointment this day.",
            )

    model = cp_model.CpModel()

    perm = [model.NewIntVar(0, n - 1, f"perm_{k}") for k in range(n)]
    model.AddAllDifferent(perm)

    start_vars = []
    end_vars = []
    for i, v in enumerate(visits):
        domain = cp_model.Domain.FromIntervals([(lo, hi) for lo, hi in v.allowed_start_minutes])
        s = model.NewIntVarFromDomain(domain, f"start_{i}")
        e = model.NewIntVar(0, MINUTES_PER_DAY, f"end_{i}")
        model.Add(e == s + v.duration_minutes)
        start_vars.append(s)
        end_vars.append(e)

    pos_start = [model.NewIntVar(0, MINUTES_PER_DAY, f"pos_start_{k}") for k in range(n)]
    pos_end = [model.NewIntVar(0, MINUTES_PER_DAY, f"pos_end_{k}") for k in range(n)]
    for k in range(n):
        model.AddElement(perm[k], start_vars, pos_start[k])
        model.AddElement(perm[k], end_vars, pos_end[k])

    # Flattened (n+1) x (n+1) travel-minutes lookup table (node 0 = home, node i+1 = visits[i]).
    flat_minutes: list[int] = []
    unreachable_flat_index: set[int] = set()
    for a in range(n + 1):
        for b in range(n + 1):
            minutes, unreachable = _leg_minutes(travel_matrix, a, b)
            flat_minutes.append(minutes)
            if unreachable:
                unreachable_flat_index.add(a * (n + 1) + b)

    travel_vars = []
    for k in range(1, n):
        idx = model.NewIntVar(0, (n + 1) * (n + 1) - 1, f"flatidx_{k}")
        model.Add(idx == (perm[k - 1] + 1) * (n + 1) + (perm[k] + 1))
        for bad_index in unreachable_flat_index:
            model.Add(idx != bad_index)  # never route through an unreachable pair
        travel_var = model.NewIntVar(0, MINUTES_PER_DAY, f"travel_{k}")
        model.AddElement(idx, flat_minutes, travel_var)
        travel_vars.append(travel_var)
        # Hard constraint: enough time must exist to travel from the previous stop to this one.
        model.Add(pos_start[k] >= pos_end[k - 1] + travel_var)

    home_idx = model.NewIntVar(0, (n + 1) * (n + 1) - 1, "home_flatidx")
    model.Add(home_idx == (perm[0] + 1))  # a=0 (home): flat index is just b = perm[0]+1
    for bad_index in unreachable_flat_index:
        model.Add(home_idx != bad_index)
    home_travel_var = model.NewIntVar(0, MINUTES_PER_DAY, "home_travel")
    model.AddElement(home_idx, flat_minutes, home_travel_var)

    total_travel_expr = home_travel_var + sum(travel_vars)

    gap_vars = []
    for k in range(1, n):
        gap = model.NewIntVar(0, MINUTES_PER_DAY, f"gap_{k}")
        model.Add(gap == pos_start[k] - pos_end[k - 1] - travel_vars[k - 1])
        gap_vars.append(gap)
    total_gap_expr = sum(gap_vars) if gap_vars else 0

    moved_bools = []
    for i, v in enumerate(visits):
        moved = model.NewBoolVar(f"moved_{i}")
        model.Add(start_vars[i] != v.original_start_minute).OnlyEnforceIf(moved)
        model.Add(start_vars[i] == v.original_start_minute).OnlyEnforceIf(moved.Not())
        moved_bools.append(moved)
    total_moved_expr = sum(moved_bools)

    gap_w = round(gap_weight * _OBJECTIVE_SCALE)
    change_w = round(change_penalty_weight * _OBJECTIVE_SCALE)
    model.Minimize(total_travel_expr * _OBJECTIVE_SCALE + total_gap_expr * gap_w + total_moved_expr * change_w)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_solve_seconds

    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return DayScheduleResult(
            solver_status="INFEASIBLE",
            visits=[],
            total_drive_minutes=0,
            total_distance_miles=0.0,
            gap_minutes=0,
            appointments_moved=0,
            efficiency_score=0.0,
            time_saved_minutes=None,
            miles_saved=None,
            reason_codes=["NO_FEASIBLE_SCHEDULE"],
            explanation=(
                "No schedule exists that satisfies therapist availability, patient availability, "
                "and travel-time constraints for this day."
            ),
        )

    order = [solver.Value(p) for p in perm]
    proposed = [
        ProposedVisitTime(
            appointment_id=visits[i].appointment_id,
            patient_id=visits[i].patient_id,
            label=visits[i].label,
            start_minute=solver.Value(start_vars[i]),
            duration_minutes=visits[i].duration_minutes,
            original_start_minute=visits[i].original_start_minute,
        )
        for i in order
    ]

    total_drive = solver.Value(total_travel_expr)
    total_gap = solver.Value(total_gap_expr) if gap_vars else 0
    moved_count = sum(1 for v in proposed if v.moved)

    # Distance isn't in the objective, so recompute it directly from the chosen order.
    total_miles = 0.0
    prev_node = 0
    for i in order:
        leg = travel_matrix[prev_node][i + 1]
        total_miles += leg.miles if leg is not None else 0.0
        prev_node = i + 1

    baseline_drive = _baseline_drive_minutes(visits, travel_matrix)
    baseline_miles = _baseline_distance_miles(visits, travel_matrix)
    time_saved = round(baseline_drive - total_drive)
    miles_saved = round(baseline_miles - total_miles, 2)

    reason_codes = []
    if moved_count == 0:
        reason_codes.append("ALREADY_OPTIMAL")
    else:
        reason_codes.append("REDUCED_DRIVING" if time_saved > 0 else "MINIMAL_SCHEDULE_CHANGE")
    if total_gap < 30 * max(1, n - 1):
        reason_codes.append("REDUCED_IDLE_TIME")

    solver_status_name = "OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE"

    if moved_count == 0:
        explanation = (
            f"The current order already minimizes driving for this day: {round(total_drive)} minutes "
            f"of total travel across {n} appointments."
        )
    else:
        savings_clause = f", saving an estimated {time_saved} minutes of driving" if time_saved > 0 else ""
        explanation = (
            f"Reordering {moved_count} of {n} appointments reduces total estimated driving to "
            f"{round(total_drive)} minutes{savings_clause} by grouping nearby visits and reducing backtracking."
        )

    return DayScheduleResult(
        solver_status=solver_status_name,
        visits=proposed,
        total_drive_minutes=round(total_drive),
        total_distance_miles=round(total_miles, 2),
        gap_minutes=round(total_gap),
        appointments_moved=moved_count,
        efficiency_score=_efficiency_score(total_drive, n),
        time_saved_minutes=time_saved,
        miles_saved=miles_saved,
        reason_codes=reason_codes,
        explanation=explanation,
    )


@dataclass(frozen=True)
class ExistingVisit:
    """One already-scheduled appointment on a candidate day - used only to find insertion points.
    Never modified by recommend_new_patient_slots (a hard guarantee for this mode: existing
    appointments are always fully preserved)."""

    appointment_id: uuid.UUID
    label: str
    start_minute: int
    end_minute: int


@dataclass(frozen=True)
class CandidateDay:
    target_date: date
    allowed_start_minutes: list[tuple[int, int]]
    existing_visits: list[ExistingVisit]  # must be pre-sorted by start_minute


@dataclass(frozen=True)
class NewPatientRecommendation:
    target_date: date
    start_minute: int
    duration_minutes: int
    added_travel_minutes: float
    added_distance_miles: float
    efficiency_score: float
    position_description: str
    reason_codes: list[str]
    explanation: str


TravelLookup = Callable[[str, str], TravelLeg | None]
HOME_KEY = "HOME"
NEW_KEY = "NEW"


def _feasible_start_in_gap(
    *,
    gap_start: int,
    gap_end: int,
    duration_minutes: int,
    travel_in: int,
    travel_out: int,
    allowed_start_minutes: list[tuple[int, int]],
) -> int | None:
    """Earliest feasible start time for the new appointment within [gap_start, gap_end], leaving
    enough time to travel in from the previous stop and out to the next one. Returns None if no
    such start exists. Picking the earliest feasible start (rather than any/latest) leaves the most
    schedule slack - a simple, deterministic, documented policy."""
    lo = gap_start + travel_in
    hi = gap_end - travel_out - duration_minutes
    if hi < lo:
        return None

    best: int | None = None
    for range_lo, range_hi in allowed_start_minutes:
        start = max(lo, range_lo)
        end = min(hi, range_hi)
        if start <= end:
            if best is None or start < best:
                best = start
    return best


def _new_patient_efficiency_score(added_travel_minutes: float) -> float:
    return max(0.0, min(100.0, 100.0 - added_travel_minutes))


def recommend_new_patient_slots(
    *,
    duration_minutes: int,
    candidate_days: list[CandidateDay],
    travel_lookup: TravelLookup,
    top_n: int = 3,
) -> list[NewPatientRecommendation]:
    """Rank candidate (day, time) slots for a new, not-yet-scheduled patient by ascending marginal
    added travel time. Never disturbs any existing appointment - only evaluates inserting the new
    one before the first, between each consecutive pair, or after the last visit of each day (or
    anywhere in the day's allowed window, if there are no existing visits at all)."""
    candidates: list[NewPatientRecommendation] = []

    for day in candidate_days:
        visits = day.existing_visits
        insertion_points: list[tuple[str, str | None, int, int]] = []  # (prev_key, next_key, gap_start, gap_end)

        if not visits:
            insertion_points.append((HOME_KEY, None, 0, MINUTES_PER_DAY))
        else:
            insertion_points.append((HOME_KEY, str(visits[0].appointment_id), 0, visits[0].start_minute))
            for i in range(len(visits) - 1):
                insertion_points.append(
                    (
                        str(visits[i].appointment_id),
                        str(visits[i + 1].appointment_id),
                        visits[i].end_minute,
                        visits[i + 1].start_minute,
                    )
                )
            insertion_points.append((str(visits[-1].appointment_id), None, visits[-1].end_minute, MINUTES_PER_DAY))

        for prev_key, next_key, gap_start, gap_end in insertion_points:
            travel_in_leg = travel_lookup(prev_key, NEW_KEY)
            if travel_in_leg is None:
                continue
            travel_out_leg = travel_lookup(NEW_KEY, next_key) if next_key else None
            if next_key and travel_out_leg is None:
                continue
            replaced_leg = travel_lookup(prev_key, next_key) if next_key else None
            if next_key and replaced_leg is None:
                continue

            travel_in = round(travel_in_leg.minutes)
            travel_out = round(travel_out_leg.minutes) if travel_out_leg else 0
            replaced_minutes = replaced_leg.minutes if replaced_leg else 0.0

            start = _feasible_start_in_gap(
                gap_start=gap_start,
                gap_end=gap_end,
                duration_minutes=duration_minutes,
                travel_in=travel_in,
                travel_out=travel_out,
                allowed_start_minutes=day.allowed_start_minutes,
            )
            if start is None:
                continue

            added_travel = (
                travel_in_leg.minutes + (travel_out_leg.minutes if travel_out_leg else 0.0) - replaced_minutes
            )
            added_distance = (
                travel_in_leg.miles
                + (travel_out_leg.miles if travel_out_leg else 0.0)
                - (replaced_leg.miles if replaced_leg else 0.0)
            )
            added_travel = max(0.0, added_travel)
            added_distance = max(0.0, added_distance)

            reason_codes = []
            if prev_key != HOME_KEY and next_key:
                position_description = "fits between two existing appointments"
                reason_codes.append("FITS_BETWEEN_APPOINTMENTS")
            elif prev_key == HOME_KEY and next_key:
                position_description = "first appointment of the day"
                reason_codes.append("FIRST_APPOINTMENT_OF_DAY")
            elif not next_key and prev_key != HOME_KEY:
                position_description = "last appointment of the day"
                reason_codes.append("LAST_APPOINTMENT_OF_DAY")
            else:
                position_description = "only appointment scheduled that day"
                reason_codes.append("ONLY_APPOINTMENT")
            if added_travel <= 10:
                reason_codes.append("NEARBY_PATIENTS")

            explanation = (
                f"Scheduling on {_format_weekday_date(day.target_date)} at "
                f"{_format_minute(start)} adds approximately {round(added_travel)} minutes of "
                f"driving and {position_description}."
            )

            candidates.append(
                NewPatientRecommendation(
                    target_date=day.target_date,
                    start_minute=start,
                    duration_minutes=duration_minutes,
                    added_travel_minutes=round(added_travel, 1),
                    added_distance_miles=round(added_distance, 2),
                    efficiency_score=_new_patient_efficiency_score(added_travel),
                    position_description=position_description,
                    reason_codes=reason_codes,
                    explanation=explanation,
                )
            )

    candidates.sort(key=lambda c: (c.added_travel_minutes, c.target_date, c.start_minute))
    return candidates[:top_n]


def _format_minute(minute_of_day: int) -> str:
    hour, minute = divmod(minute_of_day, 60)
    period = "AM" if hour < 12 else "PM"
    display_hour = hour % 12 or 12
    return f"{display_hour}:{minute:02d} {period}"


def _format_weekday_date(d: date) -> str:
    # "%-d" (no leading zero) is a Linux-only glibc strftime extension - breaks on Windows, same
    # issue app.services.scheduling_validation._format_time works around.
    return f"{d.strftime('%A, %B')} {d.day}"
