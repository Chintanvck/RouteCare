# RouteCare AI
# Product Requirements Document (PRD)

Version: 1.0  
Status: Draft  
Product Type: B2B SaaS  
Industry: Home Healthcare Operations  
Target Market: United States  

---

# 1. Product Overview

## Product Name

RouteCare AI

---

## Product Description

RouteCare AI is an AI-powered scheduling optimization platform designed for home healthcare providers.

The platform helps therapists, physical therapist assistants (PTAs), and healthcare organizations create efficient patient schedules by optimizing appointment timing, visit order, and travel routes.

Unlike traditional scheduling software that only manages appointments, RouteCare AI acts as an intelligent scheduling assistant that analyzes:

- Patient availability
- Therapist availability
- Patient locations
- Visit duration
- Existing appointments
- Travel time
- Geographic efficiency
- Scheduling constraints

The system provides ranked recommendations while keeping the final decision with the therapist or office scheduler.

---

# 2. Vision

Enable home healthcare professionals to spend less time driving and more time providing patient care.

---

# 3. Mission

Build the most intelligent scheduling assistant for home healthcare by combining scheduling automation, route optimization, and AI-powered recommendations.

---

# 4. Core Product Philosophy

## AI recommends. Humans decide.

RouteCare AI will never automatically change schedules without user approval.

Every recommendation must allow users to:

- Accept
- Modify
- Reject

The system should assist healthcare professionals, not replace their judgment.

---

# 5. Problem Statement

Home healthcare professionals spend significant amounts of time traveling between patient visits.

Current scheduling methods often rely on:

- Manual planning
- Experience
- Spreadsheets
- Calendar applications
- Office staff knowledge

This creates inefficient schedules.

Example:

Current schedule:

Patient A
1:00 PM
Newark

↓

Patient B
2:00 PM
Jersey City

↓

Patient C
3:00 PM
Newark


The therapist spends unnecessary time driving between locations.

A better schedule could group nearby patients together and reduce travel time.

---

# 6. Product Goals

## Primary Goals

1. Reduce therapist driving time.

2. Improve daily schedule efficiency.

3. Help clinics schedule more patients without increasing therapist workload.

4. Provide explainable AI recommendations.

5. Maintain therapist and scheduler control.

---

# 7. Success Metrics

## Primary Metrics

### Schedule Efficiency Improvement

Measure:

- Reduction in driving minutes
- Reduction in mileage
- Reduction in idle time


Target:

25% reduction in unnecessary travel time.

---

## Secondary Metrics

- Patients scheduled per therapist/day
- Time saved during scheduling
- AI recommendation acceptance rate
- User satisfaction
- Clinic retention

---

# 8. Target Customers

## Primary Customers

Home healthcare organizations in the United States.

Examples:

- Physical therapy clinics
- Occupational therapy providers
- Speech therapy providers
- Home nursing agencies

---

## Secondary Customers

- Independent therapists
- Small private practices
- Rehabilitation companies

---

# 9. User Roles

RouteCare AI supports four user roles.

---

# 9.1 Clinic Administrator

## Purpose

Manage clinic operations and users.

## Permissions

Can:

- Create clinic profile
- Manage users
- Add/remove therapists
- Configure clinic settings
- Import patient data
- View clinic analytics
- Manage subscription

Cannot:

- Modify system-level settings
- Access other clinics' data

---

# 9.2 Office Scheduler

## Purpose

Manage patient scheduling operations.

## Permissions

Can:

- Import patients
- Create patients
- Assign patients to therapists
- Create appointments
- Modify schedules
- Run AI optimization
- Accept AI recommendations
- Reject AI recommendations
- View therapist availability
- Manage calendars

---

# 9.3 Therapist

## Purpose

Manage personal patient schedule and routes.

## Permissions

Can:

- View own schedule
- View assigned patients
- View patient locations
- View optimized routes
- Use navigation
- Request schedule optimization
- Accept AI recommendations
- Modify schedules
- Reject AI recommendations
- Update availability

---

## Therapist Visibility Rules

Therapists can see:

- Their own schedule
- Their own patients
- Other therapist availability

Therapists cannot see:

- Other therapist patient names
- Other therapist patient addresses
- Other therapist routes
- Other therapist appointment details

---

# 9.4 RouteCare Platform Administrator

## Purpose

Manage SaaS platform operations.

Permissions:

- Manage organizations
- Manage subscriptions
- Monitor system health
- Handle support operations

---

# 10. Core User Workflow

## New Clinic Setup

Flow:

Clinic creates account

↓

Creates clinic profile

↓

Adds therapists

↓

Imports existing patient data

↓

System validates patient information

↓

Patients become available for scheduling

---

# 11. Patient Import System

## Purpose

Allow clinics to migrate existing patient information from current systems.

Initial supported format:

Excel file exported from TheraOffice.

---

## Import Workflow

User:

Clicks Import Patients

↓

Uploads Excel file

↓

System analyzes file

↓

Displays column mapping

↓

User confirms mapping

↓

System validates data

↓

System imports patients

↓

Addresses are geocoded

↓

Patients become available for scheduling

---

## Import Requirements

The system must support:

- Excel (.xlsx)
- CSV (future)

---

## Import Validation

System should detect:

- Missing addresses
- Duplicate patients
- Invalid locations
- Missing required fields

---

## Import Summary

After import:

Display:

- Successful imports
- Failed imports
- Duplicate records
- Warnings

---

# 12. Patient Management

## Patient Information

Each patient should contain:

Required:

- Full name
- Address
- Location coordinates

Optional:

- Phone number
- Email
- Visit duration
- Availability window
- Visit frequency
- Notes
- Preferred therapist

---

# 13. Therapist Management

Therapist profile includes:

- Name
- Contact information
- Working days
- Working hours
- Starting location
- Ending location
- Break schedule
- Maximum daily hours
- Maximum driving preference

---

# 14. Scheduling System

The scheduling system supports:

- Manual scheduling
- AI recommendations
- Drag and drop changes
- Daily scheduling
- Weekly scheduling

---

# 15. AI Scheduling Assistant

## Purpose

Help users create efficient schedules.

---

## AI Inputs

The AI considers:

- Therapist availability
- Patient availability
- Patient location
- Appointment duration
- Existing appointments
- Travel time
- Working hours
- Breaks
- Existing routes

---

## AI Output

The system provides the top three recommendations.

Each recommendation includes:

- Date
- Time
- Appointment sequence
- Travel impact
- Mileage impact
- Efficiency score
- Explanation

---

# Example Recommendation

Option 1

Tuesday 10:30 AM

Efficiency:
96%

Benefits:

- Saves 24 minutes driving
- Saves 8.5 miles
- Groups nearby visits


Option 2

Wednesday 9:45 AM

Efficiency:
93%


Option 3

Thursday 1:00 PM

Efficiency:
90%

---

# 16. Schedule Actions

Users can:

## Accept

Apply recommendation.

## Modify

Adjust recommendation manually.

## Reject

Ignore recommendation.

---

# 17. What-If Sandbox

## Purpose

Allow users to test schedule changes without affecting the real calendar.

---

Workflow:

User enters sandbox mode

↓

Moves appointments

↓

System recalculates:

- Driving time
- Mileage
- Efficiency score

↓

User chooses:

Save changes

OR

Discard changes

---

# 18. Maps and Route Features

The system displays:

- Patient locations
- Visit order
- Route path
- Estimated driving time
- Estimated mileage

---

# 19. Analytics Dashboard

Dashboard metrics:

- Daily driving time
- Weekly mileage
- Schedule efficiency score
- Patients visited
- Time saved

---

# 20. Non-Functional Requirements

## Performance

The system should:

- Load dashboards quickly
- Generate recommendations efficiently
- Support multiple clinics

---

## Security

Requirements:

- Multi-tenant data isolation
- Role-based access control
- Encryption
- Secure authentication
- Audit logs

---

# 21. MVP Scope

The MVP includes:

## Included

✓ Multi-tenant clinics

✓ Authentication

✓ Therapist management

✓ Patient import

✓ Patient management

✓ Calendar scheduling

✓ AI recommendations

✓ Route optimization

✓ Maps

✓ What-if sandbox

✓ Analytics dashboard


---

## Not Included Initially

- Billing
- Clinical documentation
- Insurance processing
- Payroll
- EMR replacement
- Messaging
- Video calls

---

# 22. Future Roadmap

Future capabilities:

- Direct EMR integrations
- Automatic patient assignment recommendations
- Traffic prediction
- Mobile applications
- Voice assistant
- Advanced analytics
- Machine learning optimization
