# RouteCare AI
# UI/UX Guidelines Document

Version: 1.0

Status: Draft

Frontend:
Next.js + React + TypeScript

UI Framework:
Tailwind CSS

Component Library:
shadcn/ui

Design Philosophy:
Professional healthcare SaaS
Simple
Trustworthy
Efficient

---

# 1. Product Design Principles


## 1.1 Efficiency First

The primary goal of the interface:

Help therapists and schedulers make decisions quickly.

The interface should minimize:

- Clicking
- Manual data entry
- Searching
- Switching between screens


---

## 1.2 AI Transparency

AI recommendations must always explain:

- What it recommends
- Why it recommends it
- Expected impact


Never show:

"AI recommends this."

Without explanation.


---

## 1.3 Human Control

The user must always feel in control.

AI actions require:

- Accept
- Modify
- Reject


---

## 1.4 Healthcare Professional Design

The application should feel:

- Reliable
- Calm
- Professional
- Organized

Avoid:

- Gaming-style interfaces
- Excessive animations
- Distracting colors


---

# 2. Application Layout


## Desktop Layout

Sidebar Main Content

Dashboard Content Area

Patients

Calendar

Optimization

Reports

Settings



---

## Sidebar Navigation


Available based on role.


Common:


Dashboard

Calendar

Patients

Therapists

Optimization

Reports

Settings


---

# 3. Responsive Design


The application must support:


Desktop:

Office scheduler usage


Tablet:

Clinic operations


Mobile:

Therapist usage during visits


---

Mobile priorities:

1. Today's schedule
2. Patient details
3. Navigation
4. Route information


---

# 4. Design System


## Typography


Use:

Inter font


Hierarchy:


Page Title

Large


Section Title

Medium


Body

Regular


Supporting Text

Small


---

# 5. Core UI Components


## Buttons


Primary:

Main actions

Example:

"Optimize Schedule"


Secondary:

Alternative actions


Danger:

Destructive actions


---

## Cards


Used for:

- Patients
- Recommendations
- Metrics
- Schedule summaries


---

## Modals


Used for:

- Confirmation
- Editing
- Warnings


Avoid excessive modal usage.


---

# 6. Dashboard


Purpose:

Provide operational overview.


---

## Clinic Admin Dashboard


Display:


### Efficiency Summary


Example:

Today's Efficiency
94%
↑ 12% improvement



---

### Key Metrics


Cards:


Patients Scheduled

120


Driving Time

4h 20m


Miles

85


Time Saved

2h


---

### Schedule Overview


Display:


- Therapist schedules
- Conflicts
- Optimization opportunities


---

# 7. Therapist Dashboard


Focus:

Daily workflow.


Display:


## Today's Schedule


Example:
9:00 AM
John Smith
45 min visit
Travel:
12 minutes

11:00 AM
Mary Johnson
45 min visit
Travel:
8 minutes



---

## Quick Actions


Buttons:


Optimize My Day

View Route

Start Navigation


---

# 8. Patient Management UI


## Patient List Page


Features:


Search


Filters:

- Therapist
- Location
- Availability


Columns:


Name

Address

Assigned Therapist

Visit Duration

Status


---

## Patient Profile


Sections:


Basic Information


- Name
- Phone
- Address


Scheduling Preferences


- Available days
- Visit duration


History


- Previous appointments


Actions:


Schedule Visit

Edit Patient


---

# 9. Excel Import Wizard UI


This is a critical workflow.


The user should feel guided.


---

## Step 1: Upload


Screen:
Import Patients

Upload Excel File

[Choose File]

Supported:
.xlsx
.csv



---

## Step 2: File Analysis


Display:

File analyzed

542 records found

12 warnings



---

## Step 3: Column Mapping


Interface:

Excel Column RouteCare Field

Patient Name → Full Name

Address → Address

Phone → Phone



---

## Step 4: Preview


Show:


First 10 records


Highlight:

- Missing data
- Invalid addresses
- Duplicates


---

## Step 5: Import Result


Display:
Import Complete

Successfully Imported:
530

Duplicates:
8

Errors:
4


---

# 10. Calendar UI


The calendar is a core product feature.


---

## Views


Support:


Day View

Week View


---

## Appointment Card


Example:
10:30 AM

Mary Johnson

45 minutes

📍 Newark

🚗 12 min drive



---

## Drag and Drop


Users can:

- Move appointments
- Change order
- Adjust timing


System recalculates:

- Travel time
- Efficiency score


---

# 11. AI Recommendation UI


This is the main differentiator.


---

## Recommendation Panel


Example:
AI Schedule Recommendations

Option 1 ⭐ Best

Tuesday
10:30 AM

Efficiency:
96%

Benefits:

✓ Saves 24 minutes driving

✓ Saves 8 miles

✓ Groups nearby visits

[Accept]

[Modify]

[Reject]

Option 2

Wednesday
9:45 AM

Efficiency:
93%

[Accept]



---

# 12. Efficiency Score


Display visually.


Example:



Before

78%

After AI Optimization

95%

+17%



---

# 13. What-If Sandbox UI


Purpose:

Experiment safely.


---

Interface:


Left:

Current Schedule


Right:

Sandbox Schedule


Bottom:


Comparison:



Driving Time

Before:
120 minutes

After:
90 minutes

Savings:
30 minutes



Actions:


Save Changes

Discard


---

# 14. Route Map UI


Display:


Map

+

Appointment sequence


Example:



1

Patient A

↓

2

Patient B

↓

3

Patient C



Information:


- Travel time
- Distance
- Stop order


---

# 15. Reports UI


Display:


Charts:


- Mileage trends
- Efficiency trends
- Therapist performance
- Time savings


---

# 16. Form Design Rules


Forms should:


- Use clear labels
- Validate immediately
- Explain errors


Example:


Bad:


"Invalid"


Good:


"Address could not be verified. Please check street number."


---

# 17. Empty States


Every page needs helpful empty states.


Example:


No Patients:



No patients imported yet.

Import your patient list from TheraOffice
to start optimizing schedules.

[Import Patients]



---

# 18. Error Handling


Errors should be:

- Human readable
- Actionable


Example:


Bad:

"API Error 400"


Good:

"Patient address is incomplete. Add ZIP code."


---

# 19. Accessibility Requirements


Must support:


- Keyboard navigation
- Screen readers
- Proper contrast
- Clear focus states


---

# 20. UX Rules Summary


The interface must:

✓ Reduce scheduling effort

✓ Make AI understandable

✓ Keep users in control

✓ Prioritize therapist workflow

✓ Work well on mobile

✓ Feel professional and trustworthy


---

# Final UI Decisions


Framework:

Next.js


Language:

TypeScript


Styling:

Tailwind CSS


Components:

shadcn/ui


Primary Users:

Office schedulers on desktop

Therapists on mobile


Main Experience:

AI-assisted scheduling workflow
