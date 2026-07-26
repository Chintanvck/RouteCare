# RouteCare AI
# MVP Launch Strategy Document

Version: 1.0

Status: Draft


---

# 1. Product Launch Goal


The goal of the MVP is:

Validate that home healthcare clinics will use and pay for RouteCare AI to reduce therapist driving time and improve scheduling efficiency.


The MVP does NOT need to become a complete healthcare platform.

The MVP needs to prove:

"RouteCare AI saves therapists time and helps clinics schedule more efficiently."


---

# 2. Target First Customer


Primary target:


Small to medium home healthcare clinics


Characteristics:


- Multiple therapists
- Large patient volume
- Manual scheduling process
- Therapists driving between visits
- Office scheduler manages appointments


---

# 3. MVP User Roles


Only support:


## Clinic Admin


Can:

- Manage clinic
- Add users
- View analytics


---

## Office Scheduler


Main MVP user.


Can:

- Import patients
- Manage schedules
- Generate recommendations


---

## Therapist


Can:

- View schedule
- Review recommendations
- Accept/reject changes


---

# 4. MVP Feature Scope


## Must Have Features


These features are required before demoing to a clinic.


---

# Feature 1

## Clinic Account


Required:


- Registration
- Login
- User roles


Purpose:

Allow secure clinic access.


---

# Feature 2

## Patient Import


Required:


- Excel upload
- Column mapping
- Validation
- Duplicate detection
- Address geocoding


Purpose:

Allow clinics to migrate existing patients easily.


---

# Feature 3

## Patient Management


Required:


- View patients
- Search patients
- Edit patient information


Purpose:

Allow schedulers to manage imported data.


---

# Feature 4

## Therapist Schedule


Required:


- Therapist availability
- Calendar view
- Appointment creation


Purpose:

Create real scheduling workflow.


---

# Feature 5

## Route Visualization


Required:


- Patient locations
- Route order
- Travel time


Purpose:

Show the driving problem visually.


---

# Feature 6

## AI Schedule Recommendation


Required:


- Optimize schedule
- Generate top recommendations
- Show savings


Example:


Current:


120 minutes driving


Recommendation:


85 minutes driving


Savings:


35 minutes


---

# Feature 7

## Accept Recommendation


Required:


User can:

- Accept
- Modify
- Reject


Purpose:

Maintain human control.


---

# 5. Features NOT Required For MVP


Do not build initially:


## Mobile Application


Reason:

Responsive web is enough.


---

## Full EMR Integration


Reason:

Excel import proves workflow first.


---

## Clinical Documentation


Reason:

Outside product scope.


---

## Automatic Scheduling


Reason:

Clinics want control.


---

## Advanced Machine Learning


Reason:

Need operational data first.


---

# 6. MVP Demo Workflow


The demo should follow this story:


## Step 1

Clinic uploads patient Excel file.


Example:


500 patients imported.



---

## Step 2

System validates patients.


Shows:


500 records found

480 valid

15 duplicates

5 errors


---

## Step 3

Scheduler views patient locations.


Map shows:

Patients spread across regions.


---

## Step 4

Scheduler creates therapist schedule.


Example:


Before optimization:

Patient A

9:00 AM

Drive:

25 minutes

Patient B

10:00 AM

Drive:

35 minutes

Patient C

11:30 AM



---

## Step 5

Click:


"Optimize Schedule"


---

## Step 6

System recommends:



Recommended Schedule

Patient A

9:00 AM

Patient C

10:00 AM

Patient B

11:00 AM

Savings:

35 minutes driving

12 miles reduced



---

## Step 7

Therapist accepts.


Schedule updates.


---

# 7. Success Metrics


The MVP should measure:


## Operational Metrics


Before vs After:


Driving time reduced

Mileage reduced

Idle time reduced

Patients scheduled per day


---

## Business Metrics


Measure:


Clinic adoption

Number of schedules optimized

Weekly active users

Recommendation acceptance rate


---

# 8. Pilot Program Strategy


First customer:


Potential clinic already identified.


---

Pilot length:


30-60 days


---

Pilot goals:


Validate:


- Does scheduler use it daily?
- Does it save time?
- Does therapist trust recommendations?
- Would clinic pay?


---

# 9. Feedback Collection


Collect feedback from:


Schedulers:


Questions:


"Does this reduce scheduling effort?"

"What tasks are still manual?"


---

Therapists:


Questions:


"Do recommendations make sense?"

"Would you trust this schedule?"


---

Administrators:


Questions:


"Does this improve operations?"

"Would you pay monthly?"


---

# 10. Pricing Validation


Initial pricing model:


SaaS subscription


Possible structure:


## Small Clinic


Monthly subscription


Based on:

- Number of therapists
- Number of users


---

## Larger Clinics


Enterprise pricing:


Includes:

- More users
- Advanced analytics
- Integrations


---

# 11. Competitive Advantage


RouteCare AI differentiates through:


## 1. Healthcare Scheduling Focus


Not generic route planning.


---

## 2. Human-Controlled AI


AI recommends.

Humans decide.


---

## 3. Explainable Optimization


Users understand why changes are suggested.


---

## 4. Workflow Integration


Designed around:

- Therapists
- Schedulers
- Home healthcare operations


---

# 12. Development Priorities Based On Business Value


Priority:


## Highest Value


1. Optimization engine

2. Patient import

3. Calendar scheduling

4. Route visualization


---

## Medium Value


5. Analytics

6. What-if sandbox


---

## Later


7. AI chatbot

8. Mobile app

9. EMR integrations


---

# 13. Beta Launch Checklist


Before first clinic:


Product:


✓ Patient import works

✓ Scheduling works

✓ Optimization works

✓ Recommendations explainable


Security:


✓ Authentication works

✓ Data isolation tested

✓ Audit logs enabled


Technical:


✓ Error handling

✓ Backup strategy

✓ Deployment complete


Business:


✓ Demo prepared

✓ Feedback process ready

✓ Pricing discussion prepared


---

# 14. Long-Term Product Roadmap


Future versions:


## Version 2


- Mobile therapist app
- Advanced analytics
- Better routing


---

## Version 3


- EMR integrations
- Automatic synchronization
- Predictive scheduling


---

## Version 4


AI Scheduling Assistant:


Example:


"Schedule this new patient with the least disruption."


---

# Final Launch Strategy Decisions


MVP Goal:

Prove scheduling optimization value.


First Users:

Home healthcare clinics.


First Workflow:

Import → Schedule → Optimize → Approve.


AI Role:

Recommendation engine.


Business Model:

SaaS subscription.


Success Metric:

Reduced therapist driving time.

Complete RouteCare AI Planning Package
