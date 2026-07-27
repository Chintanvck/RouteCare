"""
RouteCare AI - Role-based access control primitives.

Defines the four platform roles. The actual FastAPI dependencies that
enforce these permissions on endpoints (e.g. `require_role(...)`,
clinic-isolation checks) are implemented in Phase 1 alongside
authentication. This module only defines the shared vocabulary so
later modules have a single source of truth for role names.
"""

from enum import Enum


class UserRole(str, Enum):
    SYSTEM_ADMIN = "SYSTEM_ADMIN"
    CLINIC_ADMIN = "CLINIC_ADMIN"
    OFFICE_SCHEDULER = "OFFICE_SCHEDULER"
    THERAPIST = "THERAPIST"