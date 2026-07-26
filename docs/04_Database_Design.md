# RouteCare AI
# Database Design Document

Version: 1.0

Status: Draft

Database:
PostgreSQL

Extensions:
PostGIS

ORM:
SQLAlchemy

---

# 1. Database Design Principles

## 1.1 Multi-Tenant Architecture

Every organization-owned record must contain:

clinic_id


Purpose:

- Data isolation
- Security
- SaaS scalability


Example:


Patient belongs to Clinic A.

Clinic B cannot access that patient.


---

## 1.2 Soft Delete

Records should not be permanently deleted immediately.

Instead:

deleted_at


is used.


Benefits:

- Audit history
- Recovery
- Compliance


---

## 1.3 Auditability

Important actions must be tracked.


Examples:

- Schedule changes
- Patient updates
- Import actions
- User permission changes


---

# 2. Entity Relationship Overview

Clinic

|

|---- Users

|

|---- Therapists

|

|---- Patients

|

|---- Appointments

|

|---- Import History

|

|---- Audit Logs

|

|---- Optimization Results



---

# 3. Clinic Table


Purpose:

Stores healthcare organizations using RouteCare AI.


Table:

clinics


Fields:


id

UUID
Primary Key


name

VARCHAR


address

TEXT


phone

VARCHAR


email

VARCHAR


timezone

VARCHAR


subscription_plan

VARCHAR


created_at

TIMESTAMP


updated_at

TIMESTAMP


deleted_at

TIMESTAMP NULL


---

# 4. User Table


Purpose:

Stores all system users.


Table:

users


Fields:


id

UUID
Primary Key


clinic_id

UUID
Foreign Key

clinics.id


first_name

VARCHAR


last_name

VARCHAR


email

VARCHAR

Unique per clinic


password_hash

VARCHAR


role

ENUM:


SYSTEM_ADMIN

CLINIC_ADMIN

OFFICE_SCHEDULER

THERAPIST


is_active

BOOLEAN


last_login

TIMESTAMP


created_at

TIMESTAMP


updated_at

TIMESTAMP


---

# 5. Therapist Table


Purpose:

Stores therapist-specific information.


Table:

therapists


Fields:


id

UUID


clinic_id

UUID


user_id

UUID


license_type

VARCHAR


phone

VARCHAR


home_address

TEXT


home_latitude

DECIMAL


home_longitude

DECIMAL


max_daily_hours

INTEGER


max_drive_time_minutes

INTEGER


created_at

TIMESTAMP


updated_at

TIMESTAMP


---

# 6. Therapist Availability Table


Purpose:

Defines therapist working availability.


Table:

therapist_availability


Fields:


id

UUID


therapist_id

UUID


day_of_week

INTEGER


start_time

TIME


end_time

TIME


is_available

BOOLEAN


created_at

TIMESTAMP


---

Example:


Monday

8:00 AM - 5:00 PM


Tuesday

9:00 AM - 3:00 PM


---

# 7. Patient Table


Purpose:

Stores scheduling-related patient information.


Note:

This is NOT a clinical record system.


Table:

patients


Fields:


id

UUID


clinic_id

UUID


external_patient_id

VARCHAR

Original EMR ID if available


first_name

VARCHAR


last_name

VARCHAR


phone

VARCHAR


email

VARCHAR


address_line_1

VARCHAR


address_line_2

VARCHAR


city

VARCHAR


state

VARCHAR


zip_code

VARCHAR


latitude

DECIMAL


longitude

DECIMAL


visit_duration_minutes

INTEGER


priority_level

INTEGER


scheduling_notes

TEXT


source_system

VARCHAR


created_at

TIMESTAMP


updated_at

TIMESTAMP


deleted_at

TIMESTAMP


---

# 8. Patient Availability Table


Purpose:

Stores patient preferred visit windows.


Table:

patient_availability


Fields:


id

UUID


patient_id

UUID


day_of_week

INTEGER


start_time

TIME


end_time

TIME


preference_type

ENUM:


PREFERRED

AVAILABLE

NOT_AVAILABLE


created_at

TIMESTAMP


---

# 9. Appointment Table


Purpose:

Stores scheduled patient visits.


Table:

appointments


Fields:


id

UUID


clinic_id

UUID


patient_id

UUID


therapist_id

UUID


scheduled_date

DATE


start_time

TIME


end_time

TIME


duration_minutes

INTEGER


status

ENUM:


SCHEDULED

COMPLETED

CANCELLED

NO_SHOW


appointment_source

ENUM:


MANUAL

AI_RECOMMENDED


created_by

UUID


created_at

TIMESTAMP


updated_at

TIMESTAMP


---

# 10. Route Information Table


Purpose:

Stores travel information between appointments.


Table:

appointment_routes


Fields:


id

UUID


appointment_id

UUID


previous_location_lat

DECIMAL


previous_location_long

DECIMAL


distance_miles

DECIMAL


travel_time_minutes

INTEGER


route_provider

VARCHAR


created_at

TIMESTAMP


---

# 11. Schedule Optimization Table


Purpose:

Stores AI optimization requests and results.


Table:

optimization_requests


Fields:


id

UUID


clinic_id

UUID


therapist_id

UUID


requested_by

UUID


status

ENUM:


PENDING

PROCESSING

COMPLETED

FAILED


created_at

TIMESTAMP


completed_at

TIMESTAMP


---

# 12. Optimization Recommendation Table


Purpose:

Stores AI-generated schedule options.


Table:

optimization_recommendations


Fields:


id

UUID


optimization_request_id

UUID


rank

INTEGER


efficiency_score

DECIMAL


total_drive_minutes

INTEGER


total_distance_miles

DECIMAL


time_saved_minutes

INTEGER


miles_saved

DECIMAL


reason_codes

JSONB


recommendation_data

JSONB


created_at

TIMESTAMP


---

Example:


reason_codes:
[
"NEARBY_PATIENTS",
"REDUCED_DRIVING",
"PATIENT_AVAILABILITY"
]



---

# 13. Import History Table


Purpose:

Tracks patient imports.


Table:

imports


Fields:


id

UUID


clinic_id

UUID


uploaded_by

UUID


file_name

VARCHAR


source_system

VARCHAR


status

ENUM:


UPLOADED

PROCESSING

COMPLETED

FAILED


total_records

INTEGER


successful_records

INTEGER


failed_records

INTEGER


created_at

TIMESTAMP


completed_at

TIMESTAMP


---

# 14. Import Error Table


Purpose:

Stores failed import records.


Table:

import_errors


Fields:


id

UUID


import_id

UUID


row_number

INTEGER


field_name

VARCHAR


error_message

TEXT


created_at

TIMESTAMP


---

# 15. Duplicate Detection Table


Purpose:

Tracks possible duplicate patients.


Table:

patient_duplicates


Fields:


id

UUID


patient_id

UUID


possible_duplicate_id

UUID


confidence_score

DECIMAL


status

ENUM:


PENDING

MERGED

IGNORED


created_at

TIMESTAMP


---

# 16. Audit Log Table


Purpose:

Tracks important system actions.


Table:

audit_logs


Fields:


id

UUID


clinic_id

UUID


user_id

UUID


action

VARCHAR


entity_type

VARCHAR


entity_id

UUID


old_value

JSONB


new_value

JSONB


created_at

TIMESTAMP


---

Example:


Action:

UPDATE_APPOINTMENT


Old:

10:00 AM


New:

10:30 AM


---

# 17. Future EMR Integration Table


Purpose:

Prepare for future integrations.


Table:

external_integrations


Fields:


id

UUID


clinic_id

UUID


provider_name

VARCHAR


connection_status

VARCHAR


configuration

JSONB


created_at

TIMESTAMP


---

# 18. Database Indexing Strategy


Important indexes:


Patients:

- clinic_id
- zip_code
- latitude/longitude


Appointments:

- therapist_id
- scheduled_date
- clinic_id


Optimization:

- therapist_id
- created_at


---

# 19. Security Requirements


Database must enforce:


- Clinic-level data isolation
- Role-based access
- Encrypted sensitive fields
- Audit logging


---

# 20. Future Expansion


Database should support:


- Mobile applications
- EMR synchronization
- Machine learning models
- Patient preference learning
- Traffic prediction
- Advanced analytics


---

# Final Database Decisions


Database:

PostgreSQL


Geospatial:

PostGIS


ORM:

SQLAlchemy


Architecture:

Multi-tenant


Patient Data:

Scheduling-focused

Clinical data excluded initially


Optimization:

Stored separately from appointments


Audit:

Enabled from MVP


