# RouteCare AI
# Patient Import System Design Document

Version: 1.0

Status: Draft


Primary Use Case:

Import existing home healthcare patients from TheraOffice Excel exports.


Supported Formats:

- .xlsx
- .csv (future)


Technology:

Python
pandas
openpyxl


---

# 1. Import System Overview


The import system allows clinics to migrate existing patient scheduling data into RouteCare AI.


The system handles:


- File upload
- Data extraction
- Column mapping
- Validation
- Duplicate detection
- Address verification
- Geocoding
- Database import
- Import reporting



Workflow:


Excel File

↓

Upload

↓

Analyze

↓

Map Columns

↓

Validate Data

↓

Detect Duplicates

↓

Geocode Addresses

↓

Import Patients

↓

Generate Report



---

# 2. Import Design Principles


## 2.1 Never Modify Original Data


The uploaded file should be stored as an original copy.


Purpose:

- Audit history
- Reprocessing
- Troubleshooting



---

## 2.2 Human Review Before Import


The system must show:

- Data preview
- Errors
- Warnings
- Duplicate candidates


before importing.



---

## 2.3 Import Should Be Repeatable


If a clinic uploads a new file:

The system should identify:

- New patients
- Updated patients
- Existing patients



---

# 3. Import User Flow



## Step 1: Upload File


User:

Office Scheduler


Action:


Upload TheraOffice export file.



Interface:

Import Patients

Drag Excel file here

or

[Choose File]

Supported:

.xlsx

.csv




---

# Step 2: File Analysis


System reads:

- Sheet names
- Column headers
- Row count


Example:



File:

TheraOffice Patients.xlsx

Sheets:

Patients
Appointments

Records Found:

542




---

# Step 3: Column Mapping



Different clinics may export different column names.


Example:



Excel Column:

Patient Full Name


↓

RouteCare Field:

Patient Name



Mapping Fields:


Required:


Patient Name

Address

City

State

ZIP


Optional:


Phone

Email

Patient ID

Visit Duration

Availability



---

# Step 4: Data Preview



Before import show:


First 10 records:




Name:

John Smith

Address:

123 Main St

ZIP:

07030

Status:

Valid




Highlight:


Green:

Valid


Yellow:

Warning


Red:

Error



---

# 4. Data Validation Engine



## Required Field Validation



Required:


- First name
- Last name
- Address
- City
- State
- ZIP



Missing fields create errors.



Example:



Error:

Patient address missing

Row:

124




---

# Address Validation



Purpose:


Ensure routing calculations are accurate.



Process:



Address

↓

Geocoding Service

↓

Latitude

Longitude



Example:


Input:



123 Main Street
Jersey City NJ




Output:



Latitude:

40.7282

Longitude:

-74.0776




---

# Invalid Address Handling



Example:


System:


"Address could not be verified."


User options:


- Edit address
- Skip patient
- Import without location



---

# 5. Duplicate Detection



Purpose:


Prevent duplicate patients.



Matching logic:


Primary:


External Patient ID



Secondary:


Combination:


- First name
- Last name
- Phone
- Address



---

# Duplicate Confidence Score



Example:



John Smith

Existing Patient:

John A Smith

Match Confidence:

92%




---

# Duplicate Actions



User can:


Accept Match


↓

Update existing patient



Ignore


↓

Create new patient



Merge


↓

Combine records



---

# 6. Geocoding Process



Every imported patient should have:



Address


↓

Geocoding Service


↓

Coordinates



Stored:



latitude

longitude



Required for:


- Distance calculations
- Route optimization
- Patient clustering



---

# 7. Import Processing Architecture



Large imports should run asynchronously.



Flow:



Upload File


↓

Create Import Record


↓

Queue Background Job


↓

Process File


↓

Update Status


↓

Notify User



---


# 8. Import Database Entities



## imports



Stores import jobs.



Fields:


id


clinic_id


uploaded_by


file_name


source_system


status


total_records


successful_records


failed_records


created_at



---

## import_errors



Stores failed rows.



Fields:


id


import_id


row_number


field_name


error_message



---

# 9. Import Status States




UPLOADED

↓

ANALYZING

↓

MAPPING_REQUIRED

↓

VALIDATING

↓

PROCESSING

↓

COMPLETED

or

FAILED




---

# 10. Import Error Reporting



After processing:



Example:




Import Complete

Total Records:

542

Imported:

525

Duplicates:

12

Errors:

5

View Report




---

# 11. Import History Page



Purpose:


Allow clinic admins to review previous imports.



Display:



File Name


Date


Uploaded By


Status


Records Imported


Errors



Actions:


View Details


Download Error Report



---

# 12. Updating Existing Patients



When importing again:



System compares:



External Patient ID


or


Duplicate matching logic



Possible actions:



New Patient:

Create



Existing Patient:

Update



Conflict:

Require Review



---

# 13. Security Requirements



Imported files contain sensitive information.



Requirements:



- Encrypt stored files
- Restrict access
- Delete temporary files
- Maintain audit logs



---

# 14. Import API Integration



Related APIs:



POST

/imports/upload



POST

/imports/{id}/mapping



GET

/imports/{id}



GET

/imports/{id}/errors



POST

/imports/{id}/confirm



---

# 15. Future Enhancements



Future integrations:


- TheraOffice API
- WebPT
- Net Health
- Other EMRs



Automatic synchronization:


Clinic EMR

↓

RouteCare AI

↓

Updated schedules



---

# Final Import System Decisions



File Processing:

pandas + openpyxl


Supported:

Excel first


Workflow:

Upload → Review → Validate → Import


Duplicate Handling:

Human approval required


Geographic Data:

Required for optimization


Processing:

Background jobs


Data Philosophy:

Scheduling data only initially