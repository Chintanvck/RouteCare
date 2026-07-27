"""
RouteCare AI - Database connectivity check.

Small standalone utility for Phase 0 verification. Run this after
`docker compose up` to confirm the backend can reach Postgres and that
the PostGIS extension is active, before any real models exist.

Usage:
    python scripts/check_db_connection.py
"""

import os
import sys

from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://routecare:routecare_dev_password@localhost:5432/routecare_ai",
)


def main() -> int:
    print(f"Connecting to: {DATABASE_URL}")
    try:
        engine = create_engine(DATABASE_URL)
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version();")).scalar()
            print(f"Connected. Postgres version: {version}")

            postgis = conn.execute(
                text("SELECT PostGIS_Version();")
            ).scalar()
            print(f"PostGIS extension active. Version: {postgis}")
    except Exception as exc:  # noqa: BLE001
        print(f"Database connection failed: {exc}")
        return 1

    print("Database check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())