# RouteCare AI
# API Design Document

Version: 1.0

Status: Draft

Backend Framework:
FastAPI

API Style:
REST API

Data Format:
JSON

Authentication:
JWT Bearer Token

---

# 1. API Design Principles

## 1.1 REST Architecture

Resources are represented as endpoints.

Example:

Patients:

GET /patients

Create patient:

POST /patients


---

## 1.2 Authentication

Protected endpoints require:

Authorization header


Example:

Authorization:
Bearer {JWT_TOKEN}


---

## 1.3 Multi-Tenant Security

Every request must validate:

- User identity
- User role
- Clinic ownership


A user can only access resources belonging to their clinic.

---

# 2. API Base URL


Development:

http://localhost:8000/api/v1


Production:

https://api.routecare.ai/api/v1


---

# 3. Authentication APIs


# POST /auth/register


Purpose:

Create a new clinic account.


Request:


{
 "clinic_name": "ABC Therapy",
 "first_name": "John",
 "last_name": "Smith",
 "email": "john@example.com",
 "password": "password"
}


Response:


{
 "message": "Account created successfully",
 "user_id": "uuid"
}


---

# POST /auth/login


Purpose:

Authenticate user.


Request:


{
 "email": "john@example.com",
 "password": "password"
}


Response:


{
 "access_token": "jwt_token",
 "token_type": "bearer",
 "user": {
    "id": "uuid",
    "role": "CLINIC_ADMIN"
 }
}


---

# POST /auth/logout


Purpose:

Logout user.


Response:


{
 "message": "Logged out successfully"
}


---

# GET /auth/me


Purpose:

Get current logged-in user.


Response:


{
 "id": "uuid",
 "name": "John Smith",
 "role": "CLINIC_ADMIN",
 "clinic_id": "uuid"
}


---

# 4. Clinic APIs


# GET /clinics/profile


Purpose:

Retrieve clinic information.


---

# PUT /clinics/profile


Purpose:

Update clinic information.


Request:


{
"name": "Updated Clinic Name",
"phone": "555-555-5555"
}


---

# 5. User Management APIs


## GET /users


Purpose:

List clinic users.


Permission:

CLINIC_ADMIN


Response:


[
 {
  "id":"uuid",
  "name":"Sarah",
  "role":"THERAPIST"
 }
]


---

## POST /users


Purpose:

Create new user.


Permission:

CLINIC_ADMIN


---

## PUT /users/{user_id}


Purpose:

Update user.


---

## DELETE /users/{user_id}


Purpose:

Deactivate user.


---

# 6. Therapist APIs


# GET /therapists


Purpose:

List therapists.


Response:


[
{
"id":"uuid",
"name":"Sarah Johnson",
"availability":"available"
}
]


---

# POST /therapists


Purpose:

Create therapist profile.


---

# GET /therapists/{id}


Purpose:

Get therapist details.


---

# PUT /therapists/{id}


Purpose:

Update therapist settings.


---

# GET /therapists/{id}/availability


Purpose:

Retrieve therapist availability.


Response:


{
"Monday":
[
{
"start":"09:00",
"end":"17:00"
}
]
}


---

# PUT /therapists/{id}/availability


Purpose:

Update working hours.


---

# 7. Patient APIs


# GET /patients


Purpose:

Retrieve patients.


Filters:


?page=1

?search=name

?zip_code=07030


---

# POST /patients


Purpose:

Create patient manually.


Request:


{
"first_name":"Mary",
"last_name":"Smith",
"address":"123 Main St",
"visit_duration":45
}


---

# GET /patients/{id}


Purpose:

Retrieve patient.


---

# PUT /patients/{id}


Purpose:

Update patient.


---

# DELETE /patients/{id}


Purpose:

Soft delete patient.


---

# 8. Patient Import APIs


# POST /imports/upload


Purpose:

Upload Excel file.


Request:

Multipart form-data


file:
patients.xlsx


Response:


{
"import_id":"uuid",
"status":"UPLOADED"
}


---

# GET /imports/{id}


Purpose:

View import progress.


Response:


{
"status":"PROCESSING",
"total_records":500,
"completed":250
}


---

# POST /imports/{id}/mapping


Purpose:

Save Excel column mapping.


Request:


{
"name_column":"Patient Name",
"address_column":"Address",
"phone_column":"Phone"
}


---

# GET /imports/{id}/errors


Purpose:

View import errors.


---

# 9. Appointment APIs


# GET /appointments


Purpose:

Retrieve appointments.


Filters:


?date=2026-07-01

?therapist_id=uuid


---

# POST /appointments


Purpose:

Create appointment.


Request:


{
"patient_id":"uuid",
"therapist_id":"uuid",
"date":"2026-07-20",
"time":"10:00",
"duration":45
}


---

# GET /appointments/{id}


Purpose:

Retrieve appointment.


---

# PUT /appointments/{id}


Purpose:

Update appointment.


---

# DELETE /appointments/{id}


Purpose:

Cancel appointment.


---

# 10. Scheduling APIs


# GET /schedule/day


Purpose:

Retrieve daily schedule.


Request:


date=2026-07-20


Response:


{
"therapist":"Sarah",
"appointments":[]
}


---

# GET /schedule/week


Purpose:

Retrieve weekly schedule.


---

# POST /schedule/check-conflicts


Purpose:

Validate schedule.


Request:


{
"therapist_id":"uuid",
"date":"2026-07-20",
"time":"14:00"
}


Response:


{
"conflict":false
}


---

# 11. AI Optimization APIs


# POST /optimization/request


Purpose:

Start optimization.


Request:


{
"therapist_id":"uuid",
"date":"2026-07-20",
"mode":"DAY_OPTIMIZATION"
}


Response:


{
"optimization_id":"uuid",
"status":"PROCESSING"
}


---

# GET /optimization/{id}/status


Purpose:

Check optimization progress.


---

# GET /optimization/{id}/recommendations


Purpose:

Retrieve AI recommendations.


Response:


{
"recommendations":[
{
"rank":1,
"score":96,
"time_saved":24,
"miles_saved":8.5,
"reason":[
"NEARBY_PATIENTS",
"REDUCED_DRIVING"
]
}
]
}


---

# POST /optimization/{id}/accept


Purpose:

Accept recommendation.


Request:


{
"recommendation_id":"uuid"
}


Result:

Updates appointments.


---

# POST /optimization/{id}/reject


Purpose:

Reject recommendation.


---

# 12. What-If Sandbox APIs


# POST /sandbox/create


Purpose:

Create temporary schedule.


---

# POST /sandbox/{id}/move-appointment


Purpose:

Move appointment in sandbox.


Request:


{
"appointment_id":"uuid",
"new_time":"14:30"
}


---

# GET /sandbox/{id}/analysis


Purpose:

Calculate impact.


Response:


{
"before_drive_minutes":120,
"after_drive_minutes":90,
"savings":30
}


---

# POST /sandbox/{id}/save


Purpose:

Apply sandbox changes.


---

# DELETE /sandbox/{id}


Purpose:

Discard sandbox.


---

# 13. Route and Map APIs


# GET /routes/day


Purpose:

Generate daily route.


Request:


therapist_id

date


Response:


{
"stops":[
{
"patient":"Mary",
"order":1,
"travel_minutes":15
}
]
}


---

# GET /distance


Purpose:

Calculate distance.


Request:


from_location

to_location


Response:


{
"miles":5.2,
"time_minutes":12
}


---

# 14. Analytics APIs


# GET /analytics/dashboard


Purpose:

Retrieve clinic metrics.


Response:


{
"patients_seen":120,
"miles_saved":300,
"time_saved_minutes":900,
"efficiency_score":94
}


---

# 15. Audit APIs


# GET /audit/logs


Purpose:

Retrieve system activity.


Permission:

CLINIC_ADMIN


---

# 16. API Error Standards


All errors follow:


{
"error":{
 "code":"INVALID_ADDRESS",
 "message":"Patient address could not be verified"
}
}


---

# 17. HTTP Status Codes


200

Successful request


201

Created


400

Invalid request


401

Unauthorized


403

Permission denied


404

Not found


500

Server error


---

# Final API Architecture Decisions


Framework:

FastAPI


Authentication:

JWT


Format:

REST + JSON


Versioning:

/api/v1


Security:

RBAC + clinic isolation


Optimization:

Asynchronous processing


File uploads:

Multipart API

