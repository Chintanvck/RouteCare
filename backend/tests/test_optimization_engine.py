"""
RouteCare AI - Pure schedule-optimization algorithm tests.

No database, no mocking, no network - app.services.optimization_engine
takes plain dataclasses and returns plain dataclasses, so every case
here is a direct, deterministic function call.
"""

import uuid
from datetime import date

from app.services.optimization_engine import (
    HOME_KEY,
    NEW_KEY,
    CandidateDay,
    ExistingVisit,
    ScheduledVisit,
    TravelLeg,
    compute_allowed_start_minutes,
    intersect_intervals,
    optimize_day_schedule,
    recommend_new_patient_slots,
    subtract_intervals,
)


def _visit(label: str, start_minute: int, duration: int = 45, allowed=((0, 16 * 60),)) -> ScheduledVisit:
    return ScheduledVisit(
        appointment_id=uuid.uuid4(),
        patient_id=uuid.uuid4(),
        label=label,
        duration_minutes=duration,
        original_start_minute=start_minute,
        allowed_start_minutes=list(allowed),
    )


def _full_matrix(n: int, leg_minutes_fn) -> list[list[TravelLeg | None]]:
    """Build an (n+1)x(n+1) matrix (node 0 = home) using leg_minutes_fn(a, b) -> float | None."""
    size = n + 1
    matrix: list[list[TravelLeg | None]] = [[None] * size for _ in range(size)]
    for a in range(size):
        for b in range(size):
            if a == b:
                continue
            minutes = leg_minutes_fn(a, b)
            matrix[a][b] = TravelLeg(minutes=minutes, miles=minutes / 3) if minutes is not None else None
    return matrix


# --------------------------------------------------------------------------
# Interval utilities
# --------------------------------------------------------------------------


def test_subtract_intervals_removes_break_from_middle():
    result = subtract_intervals([(480, 1020)], [(720, 750)])
    assert result == [(480, 720), (750, 1020)]


def test_subtract_intervals_no_overlap_unchanged():
    result = subtract_intervals([(480, 600)], [(700, 800)])
    assert result == [(480, 600)]


def test_intersect_intervals():
    result = intersect_intervals([(480, 600), (700, 800)], [(500, 750)])
    assert result == [(500, 600), (700, 750)]


def test_compute_allowed_start_minutes_no_working_hours_is_empty():
    assert (
        compute_allowed_start_minutes(
            working_windows=[], break_windows=[], patient_not_available=[], patient_permitted=[], duration_minutes=45
        )
        == []
    )


def test_compute_allowed_start_minutes_subtracts_break():
    result = compute_allowed_start_minutes(
        working_windows=[(480, 1020)],
        break_windows=[(720, 780)],
        patient_not_available=[],
        patient_permitted=[],
        duration_minutes=60,
    )
    # Morning block 480-720 -> latest start 660; afternoon block 780-1020 -> latest start 960
    assert result == [(480, 660), (780, 960)]


def test_compute_allowed_start_minutes_patient_not_available_blocks_window():
    result = compute_allowed_start_minutes(
        working_windows=[(480, 1020)],
        break_windows=[],
        patient_not_available=[(600, 700)],
        patient_permitted=[],
        duration_minutes=30,
    )
    assert result == [(480, 570), (700, 990)]


def test_compute_allowed_start_minutes_patient_permitted_restricts_to_union():
    result = compute_allowed_start_minutes(
        working_windows=[(480, 1020)],
        break_windows=[],
        patient_not_available=[],
        patient_permitted=[(540, 660)],
        duration_minutes=30,
    )
    assert result == [(540, 630)]


# --------------------------------------------------------------------------
# optimize_day_schedule
# --------------------------------------------------------------------------


def test_optimize_day_schedule_no_appointments():
    result = optimize_day_schedule(visits=[], travel_matrix=[[None]])
    assert result.solver_status == "OPTIMAL"
    assert result.visits == []
    assert result.total_drive_minutes == 0


def test_optimize_day_schedule_single_appointment_reports_home_leg():
    visits = [_visit("A", 9 * 60)]
    matrix = _full_matrix(1, lambda a, b: 15.0)
    result = optimize_day_schedule(visits=visits, travel_matrix=matrix)
    assert result.solver_status == "OPTIMAL"
    assert len(result.visits) == 1
    assert result.visits[0].start_minute == 9 * 60  # nothing to reorder
    assert result.total_drive_minutes == 15


def test_optimize_day_schedule_single_appointment_no_longer_fits_window_is_infeasible():
    # The appointment's own scheduled time (9:00) falls outside its now-narrower allowed window -
    # e.g. the therapist's working hours shrank after this appointment was created. A single
    # appointment is not automatically "optimal" just because there's nothing to reorder around it.
    visit = _visit("A", 9 * 60, allowed=((13 * 60, 15 * 60),))
    matrix = _full_matrix(1, lambda a, b: 15.0)
    result = optimize_day_schedule(visits=[visit], travel_matrix=matrix)
    assert result.solver_status == "INFEASIBLE"
    assert result.visits == []


def test_optimize_day_schedule_reorders_to_minimize_travel():
    # Home is near B; A and C are near each other but far from home/B - poor original order
    # (A, B, C chronologically) should be improved by visiting B first, then grouping A and C.
    a = _visit("A", 9 * 60)
    b = _visit("B", 10 * 60)
    c = _visit("C", 11 * 60)

    def leg(u: int, v: int) -> float:
        table = {
            (0, 1): 30,
            (1, 0): 30,
            (0, 2): 5,
            (2, 0): 5,
            (0, 3): 28,
            (3, 0): 28,
            (1, 2): 27,
            (2, 1): 27,
            (1, 3): 3,
            (3, 1): 3,
            (2, 3): 26,
            (3, 2): 26,
        }
        return table[(u, v)]

    matrix = _full_matrix(3, leg)
    result = optimize_day_schedule(visits=[a, b, c], travel_matrix=matrix, max_solve_seconds=5.0)

    assert result.solver_status == "OPTIMAL"
    assert result.total_drive_minutes == 34  # home->B(5) + B->C(26) + C->A(3)
    assert result.time_saved_minutes == 49  # baseline (home->A->B->C) = 30+27+26 = 83
    assert result.appointments_moved == 2
    order = [v.label for v in result.visits]
    assert order == ["B", "C", "A"]


def test_optimize_day_schedule_respects_appointment_no_overlap():
    a = _visit("A", 9 * 60, duration=60, allowed=((9 * 60, 9 * 60),))  # pinned exactly at 9:00
    b = _visit("B", 9 * 60 + 30, duration=60, allowed=((0, 16 * 60),))
    matrix = _full_matrix(2, lambda u, v: 5.0)

    result = optimize_day_schedule(visits=[a, b], travel_matrix=matrix, max_solve_seconds=5.0)

    assert result.solver_status in ("OPTIMAL", "FEASIBLE")
    by_label = {v.label: v for v in result.visits}
    a_start, a_end = by_label["A"].start_minute, by_label["A"].start_minute + 60
    b_start, b_end = by_label["B"].start_minute, by_label["B"].start_minute + 60
    assert not (a_start < b_end and b_start < a_end)  # never overlapping


def test_optimize_day_schedule_respects_allowed_start_minutes_domain():
    # B can only start in the afternoon - the solver must never place it in the morning.
    a = _visit("A", 9 * 60, allowed=((0, 16 * 60),))
    b = _visit("B", 10 * 60, allowed=((13 * 60, 15 * 60),))
    matrix = _full_matrix(2, lambda u, v: 5.0)

    result = optimize_day_schedule(visits=[a, b], travel_matrix=matrix, max_solve_seconds=5.0)

    by_label = {v.label: v for v in result.visits}
    assert 13 * 60 <= by_label["B"].start_minute <= 15 * 60


def test_optimize_day_schedule_infeasible_when_no_valid_domain():
    # A's only allowed window is a single instant with a 60-minute duration - can never fit.
    a = _visit("A", 9 * 60, duration=60, allowed=((9 * 60, 9 * 60),))
    b = _visit("B", 10 * 60, duration=60, allowed=((9 * 60, 9 * 60),))  # same impossible instant
    matrix = _full_matrix(2, lambda u, v: 5.0)

    result = optimize_day_schedule(visits=[a, b], travel_matrix=matrix, max_solve_seconds=5.0)

    assert result.solver_status == "INFEASIBLE"
    assert result.visits == []
    assert "NO_FEASIBLE_SCHEDULE" in result.reason_codes


def test_optimize_day_schedule_infeasible_when_travel_time_does_not_fit():
    # Both appointments must start within a narrow fixed window with no slack, but 60 minutes of
    # travel is required between them - no ordering can satisfy this.
    a = _visit("A", 9 * 60, duration=30, allowed=((9 * 60, 9 * 60),))
    b = _visit("B", 9 * 60 + 30, duration=30, allowed=((9 * 60 + 30, 9 * 60 + 30),))
    matrix = _full_matrix(2, lambda u, v: 60.0)

    result = optimize_day_schedule(visits=[a, b], travel_matrix=matrix, max_solve_seconds=5.0)

    assert result.solver_status == "INFEASIBLE"


def test_optimize_day_schedule_fully_isolated_location_reported_distinctly():
    # B has no reachable connection to home or any other visit at all - caught immediately,
    # before ever invoking the solver.
    a = _visit("A", 9 * 60)
    b = _visit("B", 10 * 60)
    c = _visit("C", 11 * 60)
    matrix = _full_matrix(3, lambda u, v: 5.0 if 2 not in (u, v) else None)  # node 2 = B, fully cut off

    result = optimize_day_schedule(visits=[a, b, c], travel_matrix=matrix, max_solve_seconds=5.0)

    assert result.solver_status == "INFEASIBLE"
    assert "UNREACHABLE_LOCATION" in result.reason_codes
    assert "B" in result.explanation


def test_optimize_day_schedule_unreachable_pair_forces_infeasible():
    # A and B aren't individually isolated (both reach home fine), but with only two visits the
    # route must go home->A->B or home->B->A, and both require the A<->B leg - genuinely
    # infeasible, just not via the "isolated node" pre-check.
    a = _visit("A", 9 * 60)
    b = _visit("B", 10 * 60)
    matrix = _full_matrix(2, lambda u, v: 5.0)
    matrix[1][2] = None
    matrix[2][1] = None

    result = optimize_day_schedule(visits=[a, b], travel_matrix=matrix, max_solve_seconds=5.0)

    assert result.solver_status == "INFEASIBLE"
    assert result.visits == []


def test_optimize_day_schedule_already_optimal_reports_zero_moves():
    a = _visit("A", 9 * 60)
    b = _visit("B", 10 * 60)
    matrix = _full_matrix(2, lambda u, v: 5.0)  # symmetric, no benefit to reordering

    result = optimize_day_schedule(visits=[a, b], travel_matrix=matrix, max_solve_seconds=5.0)

    assert result.appointments_moved == 0
    assert "ALREADY_OPTIMAL" in result.reason_codes


def test_optimize_day_schedule_change_penalty_discourages_pointless_reshuffling():
    # A very high change penalty should keep the original order even if a reorder saves a
    # negligible amount of travel time.
    a = _visit("A", 9 * 60)
    b = _visit("B", 10 * 60)
    c = _visit("C", 11 * 60)
    matrix = _full_matrix(3, lambda u, v: 10.0 if (u, v) != (0, 1) else 11.0)  # trivial 1-min asymmetry

    result = optimize_day_schedule(
        visits=[a, b, c], travel_matrix=matrix, max_solve_seconds=5.0, change_penalty_weight=1000.0
    )

    assert result.appointments_moved == 0


# --------------------------------------------------------------------------
# recommend_new_patient_slots
# --------------------------------------------------------------------------


def _lookup_from_table(table: dict) -> callable:
    def lookup(a: str, b: str):
        return table.get(frozenset([a, b]))

    return lookup


def test_recommend_new_patient_slots_ranks_by_marginal_travel():
    aid, bid = uuid.uuid4(), uuid.uuid4()
    day = CandidateDay(
        target_date=date(2026, 8, 25),
        allowed_start_minutes=[(8 * 60, 17 * 60)],
        existing_visits=[
            ExistingVisit(aid, "A", 9 * 60, 9 * 60 + 45),
            ExistingVisit(bid, "B", 11 * 60, 11 * 60 + 45),
        ],
    )
    table = {
        frozenset([HOME_KEY, str(aid)]): TravelLeg(15, 7),
        frozenset([HOME_KEY, str(bid)]): TravelLeg(20, 9),
        frozenset([HOME_KEY, NEW_KEY]): TravelLeg(50, 25),  # far from home - first slot is worst
        frozenset([str(aid), str(bid)]): TravelLeg(30, 15),
        frozenset([str(aid), NEW_KEY]): TravelLeg(2, 1),
        frozenset([str(bid), NEW_KEY]): TravelLeg(2, 1),
    }
    recs = recommend_new_patient_slots(
        duration_minutes=45, candidate_days=[day], travel_lookup=_lookup_from_table(table), top_n=3
    )

    assert len(recs) == 3
    # Between A and B should be the cheapest (2+2-30, clamped to 0), better than first (50) or last.
    assert recs[0].position_description == "fits between two existing appointments"
    assert recs[0].added_travel_minutes == 0.0
    # Worst-ranked should be the far-from-home first slot.
    assert recs[-1].position_description == "first appointment of the day"


def test_recommend_new_patient_slots_respects_patient_and_therapist_windows():
    day = CandidateDay(
        target_date=date(2026, 8, 25),
        allowed_start_minutes=[(13 * 60, 14 * 60)],  # only a 1-hour afternoon window is allowed
        existing_visits=[],
    )
    table = {frozenset([HOME_KEY, NEW_KEY]): TravelLeg(10, 5)}
    recs = recommend_new_patient_slots(
        duration_minutes=45, candidate_days=[day], travel_lookup=_lookup_from_table(table)
    )

    assert len(recs) == 1
    assert 13 * 60 <= recs[0].start_minute <= 14 * 60 - 45


def test_recommend_new_patient_slots_skips_day_with_no_room():
    # allowed_start_minutes must already be a valid START-time range (per compute_allowed_start_minutes'
    # contract) - a 30-minute working window can never produce a valid start range for a 45-minute
    # visit, so it correctly comes out empty here.
    allowed = compute_allowed_start_minutes(
        working_windows=[(9 * 60, 9 * 60 + 30)],
        break_windows=[],
        patient_not_available=[],
        patient_permitted=[],
        duration_minutes=45,
    )
    assert allowed == []
    day = CandidateDay(target_date=date(2026, 8, 25), allowed_start_minutes=allowed, existing_visits=[])
    table = {frozenset([HOME_KEY, NEW_KEY]): TravelLeg(10, 5)}
    recs = recommend_new_patient_slots(
        duration_minutes=45, candidate_days=[day], travel_lookup=_lookup_from_table(table)
    )
    assert recs == []


def test_recommend_new_patient_slots_skips_unreachable_insertion_point():
    aid = uuid.uuid4()
    day = CandidateDay(
        target_date=date(2026, 8, 25),
        allowed_start_minutes=[(8 * 60, 17 * 60)],
        existing_visits=[ExistingVisit(aid, "A", 9 * 60, 9 * 60 + 45)],
    )
    # No travel data at all to/from the new patient - every insertion point must be skipped.
    recs = recommend_new_patient_slots(duration_minutes=45, candidate_days=[day], travel_lookup=lambda a, b: None)
    assert recs == []


def test_recommend_new_patient_slots_across_multiple_days_returns_top_n_overall():
    day1 = CandidateDay(date(2026, 8, 25), [(8 * 60, 17 * 60)], [])
    day2 = CandidateDay(date(2026, 8, 26), [(8 * 60, 17 * 60)], [])
    table = {
        frozenset([HOME_KEY, NEW_KEY]): TravelLeg(10, 5),
    }
    recs = recommend_new_patient_slots(
        duration_minutes=45, candidate_days=[day1, day2], travel_lookup=_lookup_from_table(table), top_n=3
    )
    # Both days offer an identical, single "anywhere in the day" candidate - both should appear.
    assert len(recs) == 2
    assert {r.target_date for r in recs} == {date(2026, 8, 25), date(2026, 8, 26)}


def test_recommend_new_patient_slots_geographic_grouping_reason_code():
    aid = uuid.uuid4()
    day = CandidateDay(
        target_date=date(2026, 8, 25),
        allowed_start_minutes=[(8 * 60, 17 * 60)],
        existing_visits=[ExistingVisit(aid, "A", 9 * 60, 9 * 60 + 45)],
    )
    table = {
        frozenset([HOME_KEY, str(aid)]): TravelLeg(15, 7),
        frozenset([HOME_KEY, NEW_KEY]): TravelLeg(3, 1),  # very close to home - low added travel
        frozenset([str(aid), NEW_KEY]): TravelLeg(3, 1),
    }
    recs = recommend_new_patient_slots(
        duration_minutes=45, candidate_days=[day], travel_lookup=_lookup_from_table(table)
    )
    assert "NEARBY_PATIENTS" in recs[0].reason_codes
