# RouteCare AI
# Development Roadmap Document

Version: 1.0

Status: Draft


---

# 1. Development Strategy


RouteCare AI will be developed incrementally.

Each phase must produce a working application.

Development priorities:

1. Core scheduling workflow
2. Patient management
3. Optimization engine
4. AI recommendations
5. Clinic management
6. Advanced features


---

# 2. MVP Definition


The MVP goal:


A home healthcare therapist or scheduler can:


1. Create a clinic account

2. Add therapists

3. Import patients from Excel

4. View patients on a map

5. Create appointments

6. Request AI schedule recommendations

7. Review and accept recommendations


---

# 3. Phase 0 — Project Foundation


Goal:

Create a clean development environment.


Tasks:


## Repository Setup


Create:



routecare-ai/

frontend/

backend/

database/

docs/

docker/



---

## Development Environment


Setup:


- Docker
- Docker Compose
- Environment variables
- Git workflow


---

## Backend Foundation


Implement:


- FastAPI project
- Database connection
- SQLAlchemy setup
- Migration system


---

## Frontend Foundation


Implement:


- Next.js project
- TypeScript
- Tailwind
- shadcn/ui


---

## Deliverable


Application runs locally.


---

# 4. Phase 1 — Authentication & Clinic Setup


Goal:

Users can securely access the system.


Features:


## Authentication


Implement:


- Registration
- Login
- Logout
- JWT authentication


---

## Clinic Management


Implement:


- Create clinic
- Update clinic profile


---

## User Roles


Implement:


Roles:


- Clinic Admin
- Office Scheduler
- Therapist


---

## Testing


Verify:


- Users can login
- Permissions work
- Clinic data isolation works


---

# Deliverable


A secure multi-tenant application foundation.


---

# 5. Phase 2 — Patient Management


Goal:

Allow clinics to manage patients.


Features:


## Patient CRUD


Implement:


- Create patient
- View patient
- Update patient
- Delete patient


---

## Patient Search


Support:


- Name search
- ZIP search
- Location filtering


---

## Address Processing


Implement:


- Address validation
- Geocoding
- Coordinate storage


---

## Deliverable


Clinic can manage patients.


---

# 6. Phase 3 — Excel Import System


Goal:

Allow TheraOffice patient migration.


Features:


## Upload System


Implement:


- Excel upload
- File validation
- Import tracking


---

## Column Mapping


Implement:


- Automatic column detection
- Manual mapping


---

## Validation


Implement:


- Missing fields
- Invalid addresses
- Duplicate detection


---

## Background Processing


Implement:


- Celery workers
- Import status tracking


---

## Deliverable


Clinic can import existing patients.


---

# 7. Phase 4 — Scheduling System


Goal:

Create the core scheduling workflow.


Features:


## Calendar


Implement:


- Day view
- Week view


---

## Appointment Management


Implement:


- Create appointment
- Edit appointment
- Cancel appointment


---

## Scheduling Rules


Implement:


- Availability checking
- Conflict detection
- Working hours validation


---

## Deliverable


Therapists can manage schedules.


---

# 8. Phase 5 — Route & Map System


Goal:

Visualize travel.


Features:


## Mapping


Implement:


- Patient locations
- Therapist locations
- Route visualization


---

## Travel Calculation


Implement:


- Distance calculation
- Travel time calculation


---

## Route Ordering


Implement:


- Appointment sequence


---

## Deliverable


Therapist can see daily route.


---

# 9. Phase 6 — Optimization Engine


Goal:

Build the main competitive advantage.


Features:


## Optimization Request


Implement:


- Create optimization job
- Background processing


---

## OR-Tools Integration


Implement:


Constraints:


- Therapist availability
- Patient availability
- Visit duration
- Travel time


---

## Recommendation Generation


Generate:


Top 3 options


Each includes:


- Schedule
- Efficiency score
- Time savings
- Mileage savings


---

## Deliverable


AI-assisted scheduling works.


---

# 10. Phase 7 — AI Explanation Layer


Goal:

Make recommendations understandable.


MVP:


Rule-based explanations.



Example:


Input:



Reason:

REDUCED_DRIVING

Savings:

25 minutes



Output:


"This option reduces driving by 25 minutes by grouping nearby patients."


---

Future:


Claude/OpenAI integration.



---

# 11. Phase 8 — What-If Sandbox


Goal:

Allow safe experimentation.


Features:


- Copy schedule
- Move appointments
- Recalculate efficiency
- Compare results
- Save changes


---

# Deliverable


Users can test schedule changes safely.


---

# 12. Phase 9 — Analytics Dashboard


Goal:

Show business value.


Metrics:


## Clinic Level


- Patients scheduled
- Miles saved
- Hours saved
- Efficiency score


---

## Therapist Level


- Daily efficiency
- Travel reduction
- Schedule utilization


---

# 13. Phase 10 — Production Preparation


Before launch:


## Security


Complete:


- Permission testing
- Encryption review
- Audit logging


---

## Performance


Test:


- Large patient imports
- Multiple therapists
- Large schedules


---

## Deployment


Setup:


- Production database
- Backend hosting
- Frontend hosting
- Monitoring


---

# 14. Features NOT Included in MVP


Avoid building:


## Clinical Documentation


No:

- Treatment notes
- Medical records
- Diagnoses


---

## Automatic Scheduling


AI recommends.

Humans approve.


---

## Mobile Application


Web responsive first.


---

## Full EMR Integration


Excel import first.


---

# 15. Recommended Build Order for Claude


Claude should implement in this exact order:


Project setup
Database models
Authentication
User roles
Patient management
Excel import
Scheduling
Maps
Optimization engine
AI explanations
Sandbox
Analytics
Production improvements


---

# 16. Testing Strategy


Each phase requires:


## Unit Tests


For:

- Business logic
- Optimization calculations


---

## API Tests


For:

- Authentication
- Permissions
- CRUD operations


---

## End-to-End Tests


For:


Complete workflow:


Import patients

↓

Create schedule

↓

Optimize

↓

Accept recommendation


---

# 17. Definition of Done


A feature is complete when:


✓ Backend implemented

✓ Frontend implemented

✓ Database changes completed

✓ Permissions tested

✓ Error handling added

✓ Documentation updated


---

# Final Development Decisions


Development Style:

Incremental


MVP Focus:

Scheduling optimization


Build Philosophy:

Working software first


AI Role:

Assistant, not autonomous decision maker


First Customer:

Home healthcare clinics
