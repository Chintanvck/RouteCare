# RouteCare AI
# AI Optimization Engine Design Document

Version: 1.0

Status: Draft

Primary Technology:

Google OR-Tools

Language:

Python


---

# 1. Overview


The RouteCare AI Optimization Engine is responsible for generating efficient patient schedules for home healthcare professionals.


The engine optimizes:

- Appointment timing
- Patient visit order
- Travel distance
- Travel time
- Therapist working hours
- Patient availability
- Scheduling constraints


The engine provides:

- Top 3 schedule recommendations
- Efficiency scores
- Estimated savings
- Explanation reasons


The engine does not automatically modify schedules.


---

# 2. Optimization Philosophy


## Human-Controlled Optimization


The system follows:


AI analyzes

↓

AI recommends

↓

Human reviews

↓

Human approves


---

# 3. Optimization Inputs


The engine receives:


## Therapist Information


Required:

- Therapist ID
- Working hours
- Starting location
- Ending location
- Break periods
- Maximum daily hours
- Maximum preferred driving time


Example:

Therapist:

Sarah Johnson

Working Hours:

8:00 AM - 5:00 PM

Start Location:

Newark, NJ

Lunch:

12:00 PM - 12:30 PM



---

## Patient Information


Required:


- Patient ID
- Location coordinates
- Availability windows
- Visit duration
- Frequency requirements


Example:



Patient:

Mary Smith

Availability:

Monday-Friday

9 AM - 2 PM

Duration:

45 minutes

Location:

Jersey City



---

## Existing Appointments


The engine considers:


- Already scheduled visits
- Fixed appointments
- Therapist commitments


Example:



10:00 AM

Patient A

45 minutes

2:00 PM

Patient B

60 minutes



---

# 4. Optimization Constraints


The engine must respect:


# 4.1 Therapist Working Hours


Rule:


Appointments cannot occur outside therapist availability.


Example:


Allowed:

9 AM - 5 PM


Invalid:

6 PM appointment


---

# 4.2 Patient Availability


Appointments must fit within patient availability.


Example:


Patient available:

10 AM - 1 PM


Valid:

11 AM


Invalid:

3 PM


---

# 4.3 Appointment Duration


Every appointment requires:


Visit duration

+

Travel time


Example:



Visit:

45 minutes

Drive:

20 minutes

Total:

65 minutes



---

# 4.4 No Appointment Overlap


A therapist cannot have:


Patient A:

10:00-10:45


and


Patient B:

10:30-11:15


---

# 4.5 Travel Feasibility


The engine must ensure:

Previous appointment

+

Driving time

+

Next appointment


is possible.


Example:


Invalid:



Patient A

10:00-11:00

Drive:

60 minutes

Patient B

11:15



---

# 4.6 Break Constraints


Respect:


- Lunch
- Personal breaks
- Clinic rules


---

# 5. Optimization Objectives


The engine optimizes using weighted scoring.


Priority order:


## Priority 1

Reduce travel time


Weight:

40%


---

## Priority 2

Reduce mileage


Weight:

25%


---

## Priority 3

Increase schedule efficiency


Weight:

20%


---

## Priority 4

Respect user preferences


Weight:

15%


---

# 6. Efficiency Score


Every schedule receives a score.


Range:


0-100


Example:



Before Optimization:

72%

After Optimization:

94%

Improvement:

+22%



---

# 7. Scoring Formula


Example:



Efficiency Score =

Travel Score

Mileage Score

Schedule Utilization Score

Preference Score



---

# 8. Recommendation Generation


The system should generate:


Top 3 recommendations.


Example:



Recommendation 1

Tuesday

10:30 AM

Score:

96%

Savings:

24 minutes

Reason:

Groups nearby patients

Recommendation 2

Wednesday

9:45 AM

Score:

93%

Recommendation 3

Thursday

1:00 PM

Score:

90%



---

# 9. Recommendation Reason Codes


The optimization engine returns structured reasons.


Examples:



NEARBY_PATIENTS

REDUCED_DRIVING

PATIENT_AVAILABLE

THERAPIST_AVAILABLE

BETTER_ROUTE_ORDER

REDUCED_IDLE_TIME



The explanation layer converts these into user-friendly messages.


---

# 10. Optimization Modes


## Mode 1:

Optimize New Patient Placement


Purpose:

Find best appointment slot for a new patient.


Input:

New patient


Output:

Top 3 placement options.



---

## Mode 2:

Optimize Daily Schedule


Purpose:

Improve one therapist's current day.


Input:

Current appointments


Output:

Improved schedule.



---

## Mode 3:

Optimize Weekly Schedule


Purpose:

Improve therapist weekly routing.


Input:

Entire week


Output:

Recommended adjustments.


---

# 11. New Patient Scheduling Workflow


Example:


New patient imported:



Patient:

John Smith

Availability:

Monday-Friday

9 AM-3 PM



Process:


1.

Find available therapist schedules


↓

2.

Generate possible appointment slots


↓

3.

Calculate travel impact


↓

4.

Calculate efficiency score


↓

5.

Rank options


↓

6.

Return top 3 recommendations


---

# 12. What-If Optimization


Sandbox optimization uses the same engine.


Example:


Current:



Driving:

120 minutes



User moves appointment.


Simulation:



New Driving:

85 minutes



System displays:



Improvement:

35 minutes saved



No changes are applied until approval.


---

# 13. Optimization Engine Components


Folder structure:



optimization/

├── engine.py

├── constraints.py

├── scoring.py

├── routing.py

├── recommendations.py

├── explanations.py

└── models.py



---

# 14. Routing Integration


The optimization engine uses:


Input:


Patient coordinates


↓

Routing Service


↓

Travel Matrix


Example:


    A     B     C

A 0 15 20

B 15 0 10

C 20 10 0



This matrix is used by OR-Tools.


---

# 15. Optimization API Flow


User:


Click:

"Optimize My Day"


↓

Backend


↓

Create Optimization Request


↓

Send data to Optimization Engine


↓

Generate recommendations


↓

Save results


↓

Display recommendations


---

# 16. Future Machine Learning Enhancements


Future versions may include:


## Preference Learning


Learn:

- Therapist habits
- Preferred routes
- Scheduling patterns


---

## Predictive Travel


Use:

- Historical traffic
- Time of day
- Weather


---

## Smart Recommendations


Example:


"The therapist usually prefers morning visits in this area."


---

# 17. Testing Requirements


The optimization engine must be tested with:


## Scenario 1

Patients close together


Expected:

Grouped schedule


---

## Scenario 2

Patients far apart


Expected:

Minimize unnecessary travel


---

## Scenario 3

Patient availability conflict


Expected:

Respect patient window


---

## Scenario 4

No valid schedule exists


Expected:

Explain conflict clearly


---

# Final AI Architecture Decisions


Optimization:

Google OR-Tools


Decision Engine:

Rule-based + constraint optimization


AI Explanation:

Rule-based initially


Future:

LLM enhancement


Output:

Top 3 recommendations


User Control:

Always required
