# VYON Fit Club - System Architecture

Version: 1.0
Last Updated: July 2026

---

# Project Overview

VYON Fit Club is a modern Gym Management System.

The project is being built in phases.

Current release focuses only on the Admin Portal.

Trainer Portal and Member Portal will be implemented in later releases.

Whenever making code changes, preserve existing architecture and avoid unnecessary refactoring.

---

# Current Release Scope

Implemented

- Authentication
- Dashboard
- Members
- Trainers
- Membership Plans
- Membership Assignment
- Payments
- Invoice Generation

Not Yet Implemented

- Trainer Portal
- Member Portal
- Attendance
- Reports
- Notifications
- Workout Plans
- Diet Plans
- QR / Face Recognition Integration

Do not implement future features unless explicitly requested.

---

# User Roles

The application supports four user roles.

## SUPER_ADMIN

Purpose

System Owner / Gym Owner

Permissions

- Full access
- Manage Admins
- Manage Trainers
- Manage Members
- Manage Membership Plans
- Manage Payments
- Generate Invoices
- View Reports
- Configure Settings
- Reset Passwords

Future

- Manage Multiple Gyms

---

## ADMIN

Purpose

Gym Administrator

Permissions

- Manage Members
- Manage Trainers
- Assign Memberships
- Collect Payments
- Generate Invoices
- View Reports
- View Attendance

Restrictions

- Cannot create Super Admins
- Cannot modify system-wide configuration

---

## TRAINER

Future Release

Permissions

- View Assigned Members
- Create Workout Plans
- Update Member Progress
- View Attendance

Restrictions

- No payment access
- No invoice management
- No membership management

---

## MEMBER

Future Release

Permissions

- View Own Membership
- Download Own Invoices
- View Attendance
- View Workout Plan
- View Diet Plan
- Update Profile
- Change Password

Restrictions

- Cannot access admin functionality.

---

# Authentication

Only one login page exists.

Users never choose their role.

Backend determines the role after authentication.

Current Release

Allowed to Login

- SUPER_ADMIN
- ADMIN

Trainer and Member login are intentionally disabled until their dashboards are built.

---

# Login

Users should be able to login using

- Email + Password
OR
- Phone Number + Password

Login screen should contain only one identifier field.

Label

Email or Phone Number

---

# Authorization

Never hardcode permissions throughout the project.

Always use centralized role checks.

Current Admin Routes

Allowed

- SUPER_ADMIN
- ADMIN

Denied

- TRAINER
- MEMBER

Both frontend routes and backend APIs must enforce authorization.

---

# Users

Users table represents every authenticated person.

Supported roles

- SUPER_ADMIN
- ADMIN
- TRAINER
- MEMBER

Each user contains

- Full Name
- Email
- Phone Number
- Password Hash
- Role
- Active Status

Passwords are never stored in plain text.

Use the existing PBKDF2 password hashing helper.

---

# Membership Workflow

Member Created

↓

Assign Membership

↓

Payment

↓

Invoice Generated

↓

Membership Active

↓

Renew Membership

Never bypass payment when assigning memberships.

---

# Payment Rules

Membership has an Original Price.

Gym owner may accept a negotiated Final Amount.

System automatically calculates

- Discount Amount
- Discount Percentage
- GST
- Total Paid

Users should never manually calculate discounts.

---

# GST

Current GST Rate

5%

GST logic must be centralized.

Avoid hardcoding the value throughout the project.

Future releases may allow changing GST from Settings.

---

# Invoice Rules

Invoice generated immediately after successful payment.

Invoice contains

- Gym Logo
- Invoice Number
- Invoice Date
- Member Details
- Membership
- Membership Duration
- Original Price
- Discount
- GST
- Total Paid
- Payment Mode

Invoice should always be downloadable.

Invoice layout should remain modular because the final invoice template may change.

---

# Members

Current Release

Admin can

- Add Member
- Edit Member
- Delete Member
- Assign Membership
- View Membership
- View Payments

Members page should prioritise readability.

Avoid horizontal scrolling.

Display only important columns.

---

# Trainers

Current Release

Admin can

- Add Trainer
- Edit Trainer
- Delete Trainer

Trainer Portal is not implemented.

---

# Dashboard

Dashboard should show operational information.

Examples

- Active Members
- Total Members
- Monthly Revenue
- Expiring Memberships

Do not display placeholder data in production.

---

# Attendance

Not implemented.

Future integration will use attendance data exported from a biometric / face recognition device.

Do not build assumptions around attendance until device format is finalized.

---

# Reports

Future feature.

Reports should be generated from existing data.

Do not implement placeholder reports.

---

# Coding Principles

Always

- Reuse existing components
- Reuse existing services
- Keep business logic separate from UI
- Keep authentication centralized
- Keep authorization centralized
- Follow existing project structure
- Keep code readable
- Prefer maintainability over clever code

Avoid

- Duplicated logic
- Hardcoded values
- Hardcoded roles
- Inline permission checks
- Unnecessary refactoring

---

# UI Principles

Application should feel like commercial software.

Priorities

- Simple
- Clean
- Fast
- Professional

Avoid

- Flashing error messages
- Demo text
- Placeholder users
- Unnecessary popups

Prefer

- Empty states
- Friendly messages
- Loading indicators
- Consistent spacing

---

# Future Roadmap

Phase 1

Admin Portal

Phase 2

Settings
Profile
Change Password
Forgot Password
Attendance

Phase 3

Trainer Portal

Phase 4

Member Portal

Phase 5

Multi Gym Support

---

# Important

Unless explicitly instructed otherwise,

Do NOT build future roadmap items.

Only implement requested functionality while preserving this architecture.

When uncertain,

choose maintainability over complexity.