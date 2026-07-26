# RouteCare AI
# Security, Privacy & Compliance Design Document

Version: 1.0

Status: Draft


---

# 1. Security Philosophy


RouteCare AI follows a security-first architecture.


Primary goals:


1. Protect patient scheduling information

2. Prevent unauthorized access

3. Maintain clinic data isolation

4. Provide audit visibility

5. Prepare for healthcare compliance requirements


---

# 2. Compliance Position


## Current Product Scope


RouteCare AI initially stores:


- Patient identity information
- Patient addresses
- Scheduling information
- Therapist availability
- Operational analytics


It does NOT initially store:


- Medical records
- Diagnoses
- Treatment notes
- Clinical documentation
- Insurance information


---

## Future Compliance Consideration


If clinical data is added later:


The platform must evaluate:

- HIPAA requirements
- Business Associate Agreements (BAA)
- Additional encryption controls
- Compliance audits


---

# 3. Authentication Security


## Authentication Method


MVP:

JWT Authentication


Future:

OAuth2 / OpenID Connect


---

# Login Flow


User enters credentials


↓

Backend validates credentials


↓

Password verified


↓

JWT token generated


↓

Frontend stores token securely


↓

API requests include token



---

# 4. Password Security


Passwords must never be stored as plain text.


Required:


Password hashing:

bcrypt


Example:

Original:

MyPassword123

Stored:

$2b$12$encrypted_hash



---

# 5. JWT Security


JWT Requirements:


Include:


- User ID
- Clinic ID
- Role
- Expiration time


Example:


```json
{
"user_id":"123",
"clinic_id":"456",
"role":"THERAPIST",
"exp":"timestamp"
}
Token Rules

Access Token:

Short lifetime

Refresh Token:

Longer lifetime

6. Role-Based Access Control (RBAC)

Roles:

SYSTEM_ADMIN

Access:

Platform management
System monitoring
CLINIC_ADMIN

Access:

Clinic settings
Users
Reports
All clinic schedules
OFFICE_SCHEDULER

Access:

Patients
Scheduling
Optimization

Cannot:

Manage users
Change permissions
THERAPIST

Access:

Own schedule
Assigned patients
Own optimization

Cannot:

View unrelated therapists
Manage clinic users
7. Multi-Tenant Data Security

RouteCare AI is a multi-tenant SaaS platform.

Every organization record contains:

clinic_id

Example:

Patients Table:

patient_id

clinic_id

name

address

Data Access Rule

Every database query must include clinic filtering.

Example:

Correct:

SELECT *

FROM patients

WHERE clinic_id = current_user.clinic_id;


Incorrect:

SELECT *

FROM patients;

8. Database Security

Requirements:

Encryption

Sensitive data should be encrypted at rest.

Examples:

Patient addresses
Uploaded files
Personal information
Database Access

Rules:

No public database exposure
Private network access
Strong credentials
Limited permissions
9. API Security

All protected endpoints require authentication.

Example:

GET /patients


Authorization:

Bearer token

API Protection

Implement:

Input validation
Rate limiting
Request logging
Error handling
10. File Upload Security

Excel files may contain sensitive data.

Required protections:

File Validation

Check:

File type
File size
Malware scanning (future)
Storage

Uploaded files:

Must not be publicly accessible.

Storage options:

Development:

Local encrypted storage

Production:

Private object storage

11. Import Data Security

Import workflow:

Upload

↓

Temporary Storage

↓

Processing

↓

Database Import

↓

Delete Temporary File

Temporary files should not remain permanently.

12. Audit Logging

All important actions must be recorded.

Table:

audit_logs

Actions to Track

Authentication:

Login
Logout
Failed login

Patient Data:

Create patient
Update patient
Delete patient

Scheduling:

Create appointment
Move appointment
Cancel appointment
Accept AI recommendation

Administration:

Add user
Remove user
Change permissions
Audit Record Example
{
"user":"Sarah",
"action":"UPDATE_APPOINTMENT",
"entity":"appointment",
"time":"2026-07-20",
"change":{
"old":"10:00",
"new":"10:30"
}
}
13. AI Security Rules

The AI system must follow:

No Autonomous Changes

AI recommendations require human approval.

Explainability

Every recommendation must provide:

Reason
Impact
Calculation
Data Minimization

Only send required data to AI services.

14. External AI Provider Security

Future LLM integrations:

Before sending data:

Remove unnecessary identifiers.

Example:

Instead of:

John Smith
123 Main Street


Send:

Patient A
Location coordinate
Availability window

15. Frontend Security

Requirements:

Prevent XSS attacks
Secure cookies
Input sanitization
HTTPS only
16. Backend Security

Required:

Environment variables for secrets
No hardcoded passwords
Dependency updates
Secure error messages
17. Logging Requirements

Logs should include:

Timestamp
User ID
Request ID
Action

Logs should NOT include:

Passwords
Sensitive patient information
18. Backup Strategy

Production system should support:

Database backups:

Daily

File backups:

Scheduled

Recovery testing:

Regularly

19. Disaster Recovery

Future targets:

Recovery Point Objective:

How much data can be lost

Recovery Time Objective:

How quickly service returns

20. Security Testing

Before production:

Required testing:

Authentication Testing
Invalid passwords
Expired tokens
Permission bypass
Authorization Testing

Verify:

Therapist cannot access another therapist's patients.

Data Isolation Testing

Verify:

Clinic A cannot access Clinic B data.

File Upload Testing

Verify:

Invalid files are rejected.

21. Production Security Checklist

Before launch:

✓ HTTPS enabled

✓ Database encrypted

✓ Secrets secured

✓ Audit logs enabled

✓ Role permissions tested

✓ Backup configured

✓ Error monitoring enabled

✓ Access controls reviewed

Final Security Decisions

Authentication:

JWT

Authorization:

RBAC

Database:

PostgreSQL with tenant isolation

Password Security:

bcrypt

File Security:

Private storage + validation

AI:

Human approval required

Audit:

Enabled from MVP

Compliance:

HIPAA-conscious architecture