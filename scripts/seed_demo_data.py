"""
RouteCare AI - Deterministic demo/seed data (Phase 10).

Creates one realistic (fictional) home-health clinic through the real
HTTP API - not by writing to the database directly - so every piece of
seeded data goes through the exact same validation/geocoding/audit
logic a real user's browser would trigger. This is deliberate: seeding
through the API is itself a small end-to-end smoke test of the create
paths.

Patient/therapist coordinates are supplied directly (never geocoded
live) specifically so this script is deterministic and never depends on
Nominatim being reachable - it only needs the backend (and, for the
optimization step, a running Celery worker) to be up.

Usage (with the dev stack already running - `docker compose up`, or a
locally-run `uvicorn`/worker):

    python scripts/seed_demo_data.py

Re-running this script creates a SECOND clinic (email addresses are
globally unique - see app/models/user.py) rather than resetting the
first one. Pass --suffix to seed another distinct demo clinic
side-by-side without colliding on email, e.g.:

    python scripts/seed_demo_data.py --suffix 2
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta

import httpx

DEFAULT_API_BASE_URL = "http://localhost:8000/api/v1"
DEMO_PASSWORD = "Str0ng!Passw0rd"


def _this_monday() -> date:
    """The Monday of the CURRENT week (per Python's date.weekday(), 0=Monday) - deliberately not
    "next" Monday. The dashboard's default view is period=this_week (see
    app/services/analytics_service.py), so seeding "next week" would leave a fresh demo clinic's
    dashboard showing all zeros until the following Monday - confusing for a pilot walkthrough.
    Some seeded days may land in the past relative to "today" if today isn't Monday - that's fine,
    nothing in appointment creation rejects a past date, and it makes the demo data look like a
    real clinic's week-in-progress rather than an empty future week."""
    today = date.today()
    return today - timedelta(days=today.weekday())


def _log(msg: str) -> None:
    print(f"[seed] {msg}")


def _require(resp: httpx.Response, what: str) -> dict:
    if resp.status_code >= 400:
        raise RuntimeError(f"{what} failed ({resp.status_code}): {resp.text[:500]}")
    return resp.json() if resp.content else {}


class Seeder:
    def __init__(self, base_url: str, suffix: str) -> None:
        self.client = httpx.Client(base_url=base_url, timeout=30.0)
        self.suffix = suffix
        self.week_start = _this_monday()

    def email(self, local_part: str) -> str:
        return f"{local_part}{self.suffix}@routecare-demo.example.com"

    # ---- clinic + admin ----

    def create_clinic_and_admin(self) -> None:
        _log(f"Registering clinic 'Sunrise Home Health{self.suffix}' ...")
        resp = self.client.post(
            "/auth/register",
            json={
                "clinic_name": f"Sunrise Home Health{self.suffix}",
                "first_name": "Dana",
                "last_name": "Admin",
                "email": self.email("dana.admin"),
                "password": DEMO_PASSWORD,
            },
        )
        _require(resp, "clinic registration")

        login = _require(
            self.client.post("/auth/login", json={"email": self.email("dana.admin"), "password": DEMO_PASSWORD}),
            "admin login",
        )
        self.client.headers["Authorization"] = f"Bearer {login['access_token']}"
        _log(f"Logged in as {self.email('dana.admin')}")

    # ---- therapists ----

    def create_therapists(self) -> list[dict]:
        _log("Creating therapists ...")
        specs = [
            # (first, last, email local-part, home lat, home lng)
            ("Terry", "Nguyen", "terry.therapist", 40.7440, -74.0324),  # Hoboken-ish
            ("Sam", "Okafor", "sam.scheduler", 40.6892, -74.0445),  # Jersey City-ish
            ("Priya", "Rao", "priya.parttime", 40.7831, -73.9712),  # Manhattan-ish, farther out
        ]
        therapists = []
        for first, last, local, lat, lng in specs:
            resp = self.client.post(
                "/therapists",
                json={
                    "first_name": first,
                    "last_name": last,
                    "email": self.email(local),
                    "password": DEMO_PASSWORD,
                    "home_latitude": lat,
                    "home_longitude": lng,
                    "max_daily_hours": 8,
                },
            )
            therapist = _require(resp, f"create therapist {first}")
            therapists.append(therapist)
            _log(f"  {first} {last} ({therapist['id']})")

        # Terry and Sam: Mon-Fri 9-5. Priya: part-time Tue/Thu 10-3 (deliberately different
        # availability shape, so the demo shows the optimizer/dashboard handling a non-uniform
        # schedule, not just three identical therapists).
        full_time_rules = [
            {"day_of_week": d, "start_time": "09:00:00", "end_time": "17:00:00", "is_available": True}
            for d in range(5)
        ] + [
            {"day_of_week": d, "start_time": "12:00:00", "end_time": "12:30:00", "is_available": False}
            for d in range(5)
        ]
        part_time_rules = [
            {"day_of_week": d, "start_time": "10:00:00", "end_time": "15:00:00", "is_available": True}
            for d in (1, 3)
        ]
        self.client.put(f"/therapists/{therapists[0]['id']}/availability", json={"rules": full_time_rules})
        self.client.put(f"/therapists/{therapists[1]['id']}/availability", json={"rules": full_time_rules})
        self.client.put(f"/therapists/{therapists[2]['id']}/availability", json={"rules": part_time_rules})
        _log("  Availability set (Terry/Sam Mon-Fri 9-5 w/ lunch break, Priya Tue/Thu 10-3)")
        return therapists

    # ---- patients ----

    def create_patients(self) -> list[dict]:
        _log("Creating patients ...")
        # A mix of addresses near Terry's home cluster and far away (near Priya's), so the
        # optimizer/travel-time/analytics all have real variation to work with - not every visit
        # a five-minute drive from home.
        specs = [
            ("Alice", "Johnson", "1 Newark St", "Hoboken", "NJ", "07030", 40.7420, -74.0310, 45),
            ("Ben", "Martinez", "50 Willow Ave", "Hoboken", "NJ", "07030", 40.7465, -74.0280, 60),
            ("Carla", "Diaz", "200 Grove St", "Jersey City", "NJ", "07302", 40.7196, -74.0431, 45),
            ("Derek", "Kim", "10 Exchange Pl", "Jersey City", "NJ", "07302", 40.7163, -74.0335, 30),
            ("Elena", "Petrov", "500 5th Ave", "New York", "NY", "10110", 40.7546, -73.9829, 60),  # far from Terry
            ("Frank", "OBrien", "1 Times Sq", "New York", "NY", "10036", 40.7580, -73.9855, 45),  # far, near Priya
            ("Grace", "Adeyemi", "300 Bergen Ave", "Jersey City", "NJ", "07304", 40.7057, -74.0764, 45),
            ("Hassan", "Ali", "1500 Hudson St", "Hoboken", "NJ", "07030", 40.7500, -74.0270, 30),
        ]
        patients = []
        for first, last, addr, city, state, zip_code, lat, lng, duration in specs:
            resp = self.client.post(
                "/patients",
                json={
                    "first_name": first,
                    "last_name": last,
                    "address_line_1": addr,
                    "city": city,
                    "state": state,
                    "zip_code": zip_code,
                    "latitude": lat,
                    "longitude": lng,
                    "visit_duration_minutes": duration,
                },
            )
            patient = _require(resp, f"create patient {first}")
            patients.append(patient)
        _log(f"  Created {len(patients)} patients")

        # One patient with a real availability constraint, so scheduling/optimization has to
        # respect a patient-side rule too, not just therapist hours.
        elena = patients[4]
        self.client.put(
            f"/patients/{elena['id']}/availability",
            json={"rules": [{"day_of_week": 1, "start_time": "13:00:00", "end_time": "17:00:00", "preference_type": "PREFERRED"}]},
        )
        _log(f"  Set a Tuesday-afternoon-only preference for {elena['first_name']} {elena['last_name']}")
        return patients

    # ---- appointments ----

    def create_appointments(self, therapists: list[dict], patients: list[dict]) -> list[dict]:
        _log(f"Creating appointments for the week of {self.week_start} ...")
        terry, sam, _priya = therapists
        alice, ben, carla, derek, elena, frank, grace, hassan = patients

        # Monday: Terry's day is deliberately laid out in a non-optimal geographic order
        # (near, far, near) so DAY_SCHEDULE_OPTIMIZATION has a genuine improvement to find.
        appointments = []
        monday = self.week_start
        for patient, start_time in [(alice, "09:00:00"), (frank, "11:00:00"), (hassan, "14:00:00")]:
            appointments.append(self._book(terry, patient, monday, start_time))

        # Tuesday: Terry again, plus Elena (who's only available Tue PM per her preference above).
        tuesday = self.week_start + timedelta(days=1)
        appointments.append(self._book(terry, ben, tuesday, "09:00:00"))
        appointments.append(self._book(terry, elena, tuesday, "13:30:00"))

        # Wednesday: Sam's day, Jersey City patients.
        wednesday = self.week_start + timedelta(days=2)
        appointments.append(self._book(sam, carla, wednesday, "09:00:00"))
        appointments.append(self._book(sam, derek, wednesday, "10:30:00"))
        appointments.append(self._book(sam, grace, wednesday, "13:00:00"))

        # Thursday: intentionally light (only one appointment) so the dashboard/analytics
        # empty-state and low-utilization numbers both have something real to show.
        thursday = self.week_start + timedelta(days=3)
        appointments.append(self._book(sam, carla, thursday, "09:00:00"))

        # Friday: nothing scheduled at all - a genuinely idle day, same reasoning.
        _log(f"  Booked {len(appointments)} appointments across Mon-Thu; Friday intentionally left open")

        # Demonstrate conflict detection: attempting to double-book Terry's Monday 9:00 slot
        # must be rejected, not silently accepted or silently bumping the existing visit.
        conflict_resp = self.client.post(
            "/appointments",
            json={
                "patient_id": grace["id"],
                "therapist_id": terry["id"],
                "scheduled_date": str(monday),
                "start_time": "09:15:00",
                "duration_minutes": 30,
            },
        )
        if conflict_resp.status_code < 400:
            raise RuntimeError("Expected a scheduling conflict to be rejected, but it was accepted.")
        _log(f"  Confirmed conflict detection: double-booking Terry's Monday 9am slot was correctly rejected ({conflict_resp.status_code})")

        return appointments

    def _book(self, therapist: dict, patient: dict, day: date, start_time: str) -> dict:
        resp = self.client.post(
            "/appointments",
            json={
                "patient_id": patient["id"],
                "therapist_id": therapist["id"],
                "scheduled_date": str(day),
                "start_time": start_time,
                "duration_minutes": patient.get("visit_duration_minutes") or 45,
            },
        )
        return _require(resp, f"book {patient['first_name']} with {therapist['first_name']} on {day}")

    # ---- optimization ----

    def run_and_accept_one_optimization(self, therapists: list[dict]) -> None:
        terry = therapists[0]
        monday = self.week_start
        _log(f"Running DAY_SCHEDULE_OPTIMIZATION for Terry on {monday} ...")
        create = _require(
            self.client.post(
                "/optimization/requests",
                json={"mode": "DAY_SCHEDULE_OPTIMIZATION", "therapist_id": terry["id"], "target_date": str(monday)},
            ),
            "create optimization request",
        )

        request_id = create["id"]
        for _ in range(30):
            status = _require(self.client.get(f"/optimization/requests/{request_id}"), "poll optimization request")
            if status["status"] in ("COMPLETED", "FAILED"):
                break
            time.sleep(1)
        else:
            _log("  Optimization did not finish in time - is a Celery worker running? Skipping acceptance.")
            return

        if status["status"] == "FAILED":
            _log(f"  Optimization failed: {status.get('error_message')} - skipping acceptance.")
            return

        recs = _require(
            self.client.get(f"/optimization/requests/{request_id}/recommendations"), "list recommendations"
        )
        if not recs or recs[0]["solver_status"] == "INFEASIBLE":
            _log("  No actionable recommendation was found - skipping acceptance.")
            return

        rec = recs[0]
        _log(
            f"  Recommendation: {rec['explanation']} "
            f"(drive time now {rec['total_drive_minutes']}m, saved {rec.get('time_saved_minutes')}m)"
        )
        accept = self.client.post(f"/optimization/requests/{request_id}/recommendations/{rec['id']}/accept")
        if accept.status_code >= 400:
            _log(f"  Could not accept recommendation ({accept.status_code}): {accept.text[:300]}")
        else:
            _log("  Accepted - the dashboard/analytics now have a real accepted optimization to show.")

    def summary(self) -> None:
        print()
        _log("Demo data ready. Log in at the frontend with:")
        _log(f"  email:    {self.email('dana.admin')}")
        _log(f"  password: {DEMO_PASSWORD}")
        _log(f"Week seeded: {self.week_start} (Monday) - {self.week_start + timedelta(days=6)} (Sunday)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-base-url", default=DEFAULT_API_BASE_URL, help="Backend API base URL")
    parser.add_argument(
        "--suffix", default="", help="Appended to demo email addresses/clinic name to seed a second, distinct demo clinic"
    )
    args = parser.parse_args()

    seeder = Seeder(args.api_base_url, args.suffix)
    try:
        seeder.create_clinic_and_admin()
        therapists = seeder.create_therapists()
        patients = seeder.create_patients()
        seeder.create_appointments(therapists, patients)
        seeder.run_and_accept_one_optimization(therapists)
    except RuntimeError as exc:
        print(f"\n[seed] ERROR: {exc}", file=sys.stderr)
        return 1
    except httpx.ConnectError as exc:
        print(f"\n[seed] Could not reach the API at {args.api_base_url} - is the backend running? ({exc})", file=sys.stderr)
        return 1

    seeder.summary()
    return 0


if __name__ == "__main__":
    sys.exit(main())
