-- RouteCare AI - Postgres initialization
-- Runs automatically on first container startup (via docker-entrypoint-initdb.d)
-- Enables PostGIS so patient/therapist coordinates and distance queries work
-- as soon as models are introduced in later phases.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";