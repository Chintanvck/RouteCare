# RouteCare AI
# System Architecture Document

Version: 1.0

Status: Draft

---

# 1. Architecture Overview

RouteCare AI is a multi-tenant SaaS platform designed to optimize scheduling for home healthcare providers.

The system follows a modular architecture:

- Frontend application
- Backend API
- Database layer
- Optimization engine
- Geographic services
- Background processing system
- Authentication and authorization layer


High-Level Architecture:


Users

↓

Next.js Frontend

↓

FastAPI Backend

↓

----------------------------------

| Database Layer                 |
| PostgreSQL + PostGIS           |
|                                |
| Optimization Engine             |
| OR-Tools                        |
|                                |
| Background Workers              |
| Celery + Redis                  |
|                                |
| Mapping Services                |
| OpenStreetMap + OSRM            |

----------------------------------


---

# 2. Architecture Principles


## 2.1 Open Source First

The system should prioritize:

- Open-source frameworks
- Self-hosting capability
- Avoiding vendor lock-in
- Replaceable external services


---

## 2.2 Modular Design

Each major capability should exist as an independent module.

Modules:

- Authentication
- User Management
- Clinic Management
- Patient Management
- Import System
- Scheduling
- Optimization Engine
- Maps
- Analytics
- Audit Logging


---

## 2.3 Human-Controlled AI

AI provides recommendations.

Users make decisions.

The system must never automatically change schedules without approval.


---

## 2.4 Explainable Recommendations

Every optimization result must include:

- Recommendation score
- Reason codes
- Impact metrics
- Explanation


---

# 3. Technology Stack


# Frontend

## Framework

Next.js

Version:
Latest stable


Language:

TypeScript


Reason:

- Open source
- React ecosystem
- Strong developer support
- Claude-friendly
- Excellent performance


---

## UI Framework


Tailwind CSS


Purpose:

- Responsive design
- Rapid UI development


---

## Component Library


shadcn/ui


Purpose:

- Accessible components
- Professional UI
- Consistent design system


---

## Frontend State Management


Recommended:

Zustand


Used for:

- Calendar state
- User state
- UI state


---

## API Communication


Recommended:

TanStack Query


Used for:

- API requests
- Cache management
- Loading states


---

# 4. Backend Architecture


## Framework

FastAPI


Language:

Python


Reasons:

- Excellent API performance
- AI/optimization ecosystem
- Easy integration with OR-Tools
- Strong typing support


---

# Backend Structure


The backend follows a modular architecture.


Example:


backend/
app/
├── main.py
├── core/
│ ├── config.py
│ ├── security.py
│ └── permissions.py
├── modules/
│ ├── auth/
│ ├── clinics/
│ ├── users/
│ ├── therapists/
│ ├── patients/
│ ├── imports/
│ ├── scheduling/
│ ├── optimization/
│ ├── maps/
│ ├── analytics/
│ └── audit/
├── database/
├── models/
├── schemas/
├── services/
└── workers/



---

# 5. Database Architecture


## Database

PostgreSQL


Reason:

- Open source
- Reliable
- Enterprise ready


---

## Geographic Extension


PostGIS


Used for:

- Patient locations
- Therapist locations
- Distance calculations
- Geographic queries


Example:

Find nearby patients: Find all patients within 5 miles of therapist location.



---

# ORM


SQLAlchemy


Purpose:

- Database abstraction
- Type-safe queries
- Maintainable models


---

# 6. Authentication Architecture


## MVP Authentication


JWT-based authentication


Flow:


User Login

↓

Validate Credentials

↓

Generate JWT Token

↓

Frontend Stores Token

↓

API Requests Include Token


---

# Authorization


Role Based Access Control (RBAC)


Roles:


SYSTEM_ADMIN

CLINIC_ADMIN

OFFICE_SCHEDULER

THERAPIST


---

# Permission Example


Therapist:

Allowed:

- View own schedule
- View assigned patients
- Request optimization


Denied:

- Manage users
- View other patient schedules


---

# 7. Multi-Tenant Architecture


The system supports multiple clinics.


Every business record contains:

clinic_id


Example:


patients table:
id
clinic_id
name
address
coordinates



---

Data isolation rule:


A user can only access data belonging to their clinic.


---

# 8. AI Optimization Architecture


The AI system consists of two layers.


## Layer 1

Optimization Engine


Technology:

Google OR-Tools


Purpose:

Generate optimal schedules.


Responsibilities:

- Appointment placement
- Route optimization
- Time window handling
- Constraint solving


---

## Layer 2

Explanation Engine


Purpose:

Explain recommendations.


MVP:

Rule-based explanations.


Future:

LLM integration.


---

# Optimization Flow


User clicks:

"Optimize Schedule"


↓

Backend receives request


↓

Optimization Engine processes:

- Patients
- Locations
- Availability
- Therapist hours
- Existing appointments


↓

Returns:

Top 3 recommendations


↓

Explanation generated


↓

Displayed to user


---

# 9. Mapping Architecture


## Geographic Data


OpenStreetMap


---

## Geocoding


Nominatim


Purpose:

Convert addresses into coordinates.


Example: 
123 Main Street
↓
Latitude
Longitude



---

## Routing


OSRM


Purpose:

Calculate:

- Driving distance
- Travel time
- Route order


---

# 10. File Import Architecture


Purpose:

Import existing patients from systems such as TheraOffice.


Supported:

- Excel (.xlsx)
- CSV (future)


---

# Import Pipeline


User uploads file


↓

File validation


↓

Column detection


↓

Column mapping


↓

Data cleaning


↓

Duplicate detection


↓

Address validation


↓

Geocoding


↓

Database import


↓

Import report generated


---

# Import Components

Import Module
├── File Upload Service
├── Excel Parser
├── Column Mapper
├── Validation Engine
├── Duplicate Detector
├── Geocoding Service
└── Import History



---

# 11. Background Processing Architecture


Some operations should run asynchronously.


Examples:


- Large patient imports
- Route calculations
- Schedule optimization
- Analytics generation


Technology:


Celery

+

Redis


Flow:


User Request

↓

API

↓

Queue Task

↓

Worker

↓

Database Update

↓

Notification


---

# 12. Deployment Architecture


## Development Environment


Docker Compose


Containers:
frontend
backend
postgres
redis
worker
routing services



---

# Production Architecture


Possible deployment:
Load Balancer
↓
Frontend Container
↓
Backend Containers
↓
Database
↓
Worker Services



---

# 13. Project Folder Structure


Root:
routecare-ai/
├── frontend/
├── backend/
├── workers/
├── database/
├── docs/
├── docker/
├── scripts/
└── README.md



---

# 14. Development Standards


## Code Quality

Requirements:

- TypeScript strict mode
- Python type hints
- Automated testing
- Clear module boundaries


---

## API Standards


Use:

REST API


Naming:


GET

/patients


POST

/patients


PUT

/patients/{id}


DELETE

/patients/{id}


---

# 15. Future Architecture Expansion


Future additions:


- EMR integrations
- Mobile applications
- Machine learning optimization
- Traffic prediction
- Voice assistant
- Advanced analytics


---

# Final Architecture Decisions


Locked:


Frontend:

Next.js + React + TypeScript


Backend:

FastAPI + Python


Database:

PostgreSQL + PostGIS


ORM:

SQLAlchemy


Authentication:

JWT + RBAC


Optimization:

Google OR-Tools


Maps:

OpenStreetMap + Nominatim + OSRM


Background Tasks:

Celery + Redis


AI:

Optimization engine first

Rule-based explanations initially

LLM enhancement later


Deployment:

Docker-based


Architecture:

Multi-tenant SaaS
