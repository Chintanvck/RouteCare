# RouteCare AI
# User Stories Document

Version: 1.0

---

# 1. Introduction

This document defines user stories for RouteCare AI.

Each user story follows:

As a [user role]

I want to [perform an action]

So that [business value is achieved]

Each story includes acceptance criteria to define expected system behavior.

---

# 2. Clinic Administrator User Stories

---

## US-ADMIN-001
## Create Clinic Account

### User Story

As a clinic administrator,

I want to create a clinic account,

so that my organization can use RouteCare AI.

### Acceptance Criteria

The system must allow:

- Clinic name entry
- Clinic contact information
- Administrator account creation
- Secure authentication setup

After successful registration:

- Clinic workspace is created
- Administrator becomes the first user
- Clinic data is isolated from other organizations

---

## US-ADMIN-002
## Manage Clinic Users

### User Story

As a clinic administrator,

I want to add and manage users,

so that the right people have access to the system.

### Acceptance Criteria

Administrator can:

- Add office schedulers
- Add therapists
- Remove users
- Change user roles
- Disable accounts

The system must enforce role permissions.

---

## US-ADMIN-003
## View Clinic Performance

### User Story

As a clinic administrator,

I want to view scheduling analytics,

so that I understand operational efficiency.

### Acceptance Criteria

Dashboard displays:

- Total patients scheduled
- Total driving time
- Mileage
- Schedule efficiency
- Time saved

---

# 3. Office Scheduler User Stories

---

# Patient Management

---

## US-SCHED-001
## Import Patients From Excel

### User Story

As an office scheduler,

I want to import existing patient information from an Excel file,

so that I do not need to manually create hundreds of patients.

### Acceptance Criteria

The system must:

- Accept .xlsx files
- Read spreadsheet data
- Display detected columns
- Allow column mapping
- Validate required fields
- Show import preview
- Import valid records
- Report errors

---

## US-SCHED-002
## Detect Duplicate Patients

### User Story

As an office scheduler,

I want the system to identify duplicate patients,

so that I do not create duplicate records.

### Acceptance Criteria

The system should compare:

- Name
- Address
- Phone number
- Existing patient ID

If a duplicate exists:

Display:

"Possible duplicate patient found."

Allow:

- Merge
- Update
- Skip

---

## US-SCHED-003
## Validate Patient Address

### User Story

As an office scheduler,

I want patient addresses validated,

so that route calculations are accurate.

### Acceptance Criteria

The system should:

- Verify address
- Convert address into coordinates
- Detect invalid addresses
- Suggest corrections

---

# Scheduling

---

## US-SCHED-004
## View Therapist Availability

### User Story

As an office scheduler,

I want to view therapist availability,

so that I can schedule patients appropriately.

### Acceptance Criteria

Scheduler can see:

- Available time slots
- Working hours
- Existing appointments

Scheduler cannot see:

- Private therapist information
- Other clinic data

---

## US-SCHED-005
## Create Appointment Manually

### User Story

As an office scheduler,

I want to manually schedule a patient,

so that I can handle situations where human judgment is required.

### Acceptance Criteria

Scheduler can select:

- Therapist
- Patient
- Date
- Time
- Visit duration

System validates:

- Availability
- Conflicts
- Working hours

---

## US-SCHED-006
## Request AI Schedule Recommendations

### User Story

As an office scheduler,

I want AI-generated schedule recommendations,

so that I can create the most efficient schedule.

### Acceptance Criteria

The system analyzes:

- Patient location
- Therapist schedule
- Travel distance
- Availability
- Existing appointments

The system returns:

Top 3 recommendations.

---

# 4. Therapist User Stories

---

## US-THERAPIST-001
## View Daily Schedule

### User Story

As a therapist,

I want to view my daily schedule,

so that I know my patient visits.

### Acceptance Criteria

Display:

- Appointment times
- Patient information
- Address
- Route order
- Travel time

---

## US-THERAPIST-002
## Optimize My Schedule

### User Story

As a therapist,

I want AI to optimize my schedule,

so that I spend less time driving.

### Acceptance Criteria

The system should:

Analyze current schedule.

Generate recommendations.

Show:

- Current efficiency
- Recommended efficiency
- Estimated time saved
- Mileage saved

---

## US-THERAPIST-003
## Accept AI Recommendation

### User Story

As a therapist,

I want to accept an AI recommendation,

so that my schedule updates automatically.

### Acceptance Criteria

When accepted:

- Calendar updates
- Route updates
- Efficiency recalculates

---

## US-THERAPIST-004
## Modify AI Recommendation

### User Story

As a therapist,

I want to modify AI recommendations,

so that I can consider personal preferences.

### Acceptance Criteria

Therapist can:

- Change appointment time
- Move appointment order
- Adjust schedule

System recalculates impact.

---

## US-THERAPIST-005
## Reject AI Recommendation

### User Story

As a therapist,

I want to reject AI recommendations,

so that I remain in control.

### Acceptance Criteria

The schedule remains unchanged.

Optional feedback can be collected.

---

# 5. AI Scheduling User Stories

---

## US-AI-001
## Recommend Best Appointment Time

### User Story

As a user,

I want AI to recommend the best appointment time,

so that new patients fit efficiently into my schedule.

### Acceptance Criteria

AI considers:

- Patient availability
- Therapist availability
- Existing appointments
- Travel impact

---

## US-AI-002
## Recommend Multiple Options

### User Story

As a user,

I want multiple recommendations,

so that I can choose based on real-world circumstances.

### Acceptance Criteria

The system provides:

Recommendation 1:
Best option

Recommendation 2:
Alternative

Recommendation 3:
Backup option

Each includes reasoning.

---

## US-AI-003
## Explain Recommendations

### User Story

As a user,

I want to understand AI recommendations,

so that I can trust the system.

### Acceptance Criteria

Every recommendation includes:

- Why this time was selected
- Travel impact
- Efficiency impact

---

# 6. What-If Sandbox User Stories

---

## US-WHATIF-001
## Test Schedule Changes

### User Story

As a therapist,

I want to test schedule changes before saving,

so that I can understand the impact.

### Acceptance Criteria

Sandbox mode allows:

- Drag appointments
- Move visits
- Add temporary changes

System displays:

- Driving change
- Mileage change
- Efficiency change

---

## US-WHATIF-002
## Save Sandbox Changes

### User Story

As a user,

I want to apply sandbox changes,

so that my optimized schedule becomes active.

### Acceptance Criteria

When saved:

- Calendar updates
- Routes update
- Analytics update

---

# 7. System-Level User Stories

---

## US-SYSTEM-001
## Protect Clinic Data

### User Story

As a clinic,

I want my data isolated,

so that other organizations cannot access my information.

### Acceptance Criteria

The system must:

- Enforce tenant isolation
- Validate permissions
- Log access

---

## US-SYSTEM-002
## Maintain Audit History

### User Story

As an administrator,

I want schedule changes recorded,

so that I can understand operational decisions.

### Acceptance Criteria

System records:

- User
- Action
- Date/time
- Previous value
- New value

---

# 8. Future User Stories

Future versions may include:

- EMR integrations
- Automatic therapist matching recommendations
- Traffic-aware scheduling
- Mobile applications
- Voice scheduling assistant
- Predictive scheduling
