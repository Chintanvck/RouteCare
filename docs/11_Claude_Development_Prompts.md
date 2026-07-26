# RouteCare AI
# Claude Development Prompt Guide

Version: 1.0


Purpose:

This document contains prompts used with Claude to build RouteCare AI.

Claude should follow all previous architecture documents:

- Vision Document
- Product Requirements
- User Stories
- System Architecture
- Database Design
- API Design
- UI/UX Guidelines
- AI Optimization Engine
- Import System
- Security Requirements
- Development Roadmap


---

# 1. Global Instruction Prompt

Use this prompt at the beginning of every Claude session.


PROMPT:


You are a senior full-stack software engineer building RouteCare AI.

RouteCare AI is a SaaS platform that helps home healthcare therapists optimize patient schedules to reduce unnecessary driving time.

Follow these requirements:


Architecture:

Frontend:
- Next.js
- React
- TypeScript
- Tailwind CSS
- shadcn/ui


Backend:
- Python
- FastAPI
- SQLAlchemy


Database:
- PostgreSQL
- PostGIS


Authentication:
- JWT
- Role-based access control


Optimization:
- Google OR-Tools


Maps:
- OpenStreetMap
- Nominatim
- OSRM


Background Tasks:
- Celery
- Redis


Development principles:

1. Build incrementally.
2. Do not skip architecture decisions.
3. Do not create unnecessary complexity.
4. Keep code production-ready.
5. Explain important technical decisions.
6. Write clean modular code.
7. Add error handling.
8. Add tests for important functionality.
9. Never allow AI recommendations to automatically change schedules.
10. Maintain human approval workflow.


Before writing code:
- Explain your approach.
- Identify affected files.
- Confirm assumptions.

---

# 2. Project Initialization Prompt


Use this first.


PROMPT:


Create the initial RouteCare AI project structure.


Requirements:


Create:


routecare-ai/


frontend/

backend/

database/

docs/

docker/


Frontend:


Setup:

- Next.js
- TypeScript
- Tailwind CSS
- shadcn/ui


Backend:


Setup:

- FastAPI
- SQLAlchemy
- Alembic migrations
- PostgreSQL connection


Infrastructure:


Create:

- docker-compose.yml
- environment configuration
- README


Do not implement business features yet.

Only create a clean foundation.


---

# 3. Database Implementation Prompt


PROMPT:


Implement the RouteCare AI database architecture.


Use:

- PostgreSQL
- PostGIS
- SQLAlchemy


Create models for:


- Clinics
- Users
- Therapists
- Therapist Availability
- Patients
- Patient Availability
- Appointments
- Appointment Routes
- Optimization Requests
- Optimization Recommendations
- Imports
- Import Errors
- Duplicate Patients
- Audit Logs


Requirements:


- Use UUID primary keys
- Add timestamps
- Add soft delete where appropriate
- Add clinic_id for multi-tenant isolation
- Create relationships
- Add database indexes


Generate:

- SQLAlchemy models
- Alembic migration
- Database initialization script


---

# 4. Authentication Prompt


PROMPT:


Implement authentication and authorization.


Requirements:


Implement:


- User registration
- Login
- Logout
- JWT authentication
- Password hashing using bcrypt


Roles:


- SYSTEM_ADMIN
- CLINIC_ADMIN
- OFFICE_SCHEDULER
- THERAPIST


Implement permission middleware.


Rules:


Therapist:
- Can view own schedule
- Can view assigned patients


Scheduler:
- Can manage patients
- Can manage appointments


Clinic Admin:
- Full clinic access


Ensure all queries enforce clinic isolation.


Add tests.


---

# 5. Patient Management Prompt


PROMPT:


Implement patient management module.


Backend:


Create:


CRUD APIs:


GET /patients

POST /patients

GET /patients/{id}

PUT /patients/{id}

DELETE /patients/{id}


Features:


- Search patients
- Filter patients
- Validate addresses
- Store latitude and longitude


Frontend:


Create:


- Patient list page
- Patient profile page
- Add/edit patient forms


Follow UI guidelines.


---

# 6. Excel Import Prompt


PROMPT:


Implement the TheraOffice Excel import workflow.


Requirements:


Support:


- XLSX upload
- CSV support preparation


Workflow:


Upload

↓

Analyze

↓

Column Mapping

↓

Validation

↓

Duplicate Detection

↓

Geocoding

↓

Import


Use:


- pandas
- openpyxl


Implement:


- Import history
- Error reporting
- Duplicate detection
- Background processing


Frontend:


Create import wizard:

Step 1:
Upload


Step 2:
Map columns


Step 3:
Review errors


Step 4:
Confirm import


Step 5:
Import results


---

# 7. Scheduling Prompt


PROMPT:


Implement appointment scheduling.


Features:


Calendar:

- Day view
- Week view


Appointments:


Create

Update

Cancel


Validation:


- Therapist availability
- Patient availability
- Appointment conflicts
- Travel feasibility


Frontend:


Create:

- Calendar interface
- Appointment cards
- Schedule management


---

# 8. Map Integration Prompt


PROMPT:


Implement geographic functionality.


Use:


OpenStreetMap

Nominatim

OSRM


Features:


- Address geocoding
- Distance calculation
- Travel time calculation
- Daily route visualization


Create:


Map component

Route component

Travel calculation service


---

# 9. Optimization Engine Prompt


PROMPT:


Implement the RouteCare AI optimization engine.


Technology:


Python

Google OR-Tools


The engine must optimize:


- Appointment timing
- Patient ordering
- Travel reduction
- Schedule efficiency


Constraints:


- Therapist working hours
- Patient availability
- Visit duration
- Existing appointments
- Travel time


Output:


Generate top 3 recommendations.


Each recommendation must include:


- Schedule changes
- Efficiency score
- Miles saved
- Minutes saved
- Reason codes


The engine must NEVER directly modify appointments.


---

# 10. Recommendation Explanation Prompt


PROMPT:


Implement the recommendation explanation system.


MVP:

Rule-based explanations.


Input:


Reason codes:

- NEARBY_PATIENTS
- REDUCED_DRIVING
- PATIENT_AVAILABLE
- BETTER_ROUTE_ORDER


Output:


Human-friendly explanations.


Example:


"This schedule groups nearby patients and reduces estimated driving time by 24 minutes."


Prepare architecture for future LLM integration.


---

# 11. What-If Sandbox Prompt


PROMPT:


Implement schedule simulation.


Requirements:


Users can:


- Duplicate schedule
- Move appointments
- Test changes


System calculates:


Before:

- Driving time
- Mileage
- Efficiency


After:

- Driving time
- Mileage
- Efficiency


Changes should not affect real schedule until approved.


---

# 12. Testing Prompt


PROMPT:


Review the current RouteCare AI implementation.


Create:


Unit tests for:

- Authentication
- Permissions
- Scheduling rules
- Optimization calculations
- Import validation


API tests for:


- CRUD endpoints
- Authorization
- Error handling


End-to-end workflow test:


Import patients

↓

Create appointment

↓

Optimize schedule

↓

Accept recommendation


Identify bugs and improvement opportunities.


---

# 13. Code Review Prompt


PROMPT:


Act as a senior software architect reviewing this codebase.


Review:


Architecture

Security

Performance

Maintainability

Database design

API design

Frontend quality


Identify:


- Technical debt
- Security risks
- Scalability issues
- Missing error handling


Provide recommended fixes.


---

# 14. Production Readiness Prompt


PROMPT:


Prepare RouteCare AI for production deployment.


Review:


Security:

- Authentication
- Authorization
- Encryption
- Secrets


Performance:

- Database indexing
- API optimization
- Background jobs


Deployment:

- Docker configuration
- Environment variables
- Logging
- Monitoring


Create production checklist.


---

# Claude Working Rules


Claude must always:


✓ Explain before implementing

✓ Follow existing architecture

✓ Avoid rewriting unrelated code

✓ Maintain modular structure

✓ Ask clarification when requirements conflict

✓ Write maintainable production-quality code

