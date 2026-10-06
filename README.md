## v2.5.14 — Technician Daily Report Self-Service

Technicians can now open their own submitted Daily Work Reports from the sidebar and use View, PDF, and CSV actions. Backend ownership checks remain enforced for technician report detail and exports. SAdmin self-service from v2.5.12 is retained.

# MKDSS IT Helpdesk Management System

Internal IT Helpdesk Management System for **MK Digital Security Solutions PLC (MKDSS)**.

This project is a Flask/SQLAlchemy web application intended for deployment on the MKDSS internal LAN. It uses persistent SQLite storage, role-based authorization, ticket workflows, notifications, daily work reports, audit logging, CSV/PDF exports, and secure attachment access.


## UI theme

Version 2.5.1 uses the MKDSS enterprise ITSM dashboard direction based on the reference UI supplied by the project owner. It includes a dark default theme, a professional light/day theme switcher, an SVG notification bell with unread badge and recent-notification popover, collapsible sidebar, KPI cards, status distribution, ticket trend chart, priority distribution, department/request-type views, and recent tickets. The existing MKDSS logo from the original source ZIP is preserved.

The dashboard contains real database data only. Empty databases display empty states rather than sample statistics.

## Important data policy

- The application does not seed demo users, tickets, notifications, reports, or dashboard statistics.
- The application does not automatically reset or delete the SQLite database.
- Existing production data must be backed up before upgrades.
- The clean source package intentionally excludes the live SQLite database and uploaded confidential files. Keep the existing `instance/mkdss_helpdesk.sqlite3` and `instance/attachments/` from the current installation when upgrading.
- Tests use temporary databases and do not create production business records.

## Requirements

- Python 3.11+ (Python 3.12 recommended)
- Flask 3.1.x
- Flask-SQLAlchemy 3.1.x
- Werkzeug 3.1.x
- ReportLab 4.4.x
- Windows or Linux server on the MKDSS LAN

## Installation - Windows

1. Copy the project to a server directory, for example:

   `C:\MKDSS_IT_Helpdesk`

2. Run:

   `INSTALL_WINDOWS.bat`

3. Preserve/copy the existing production `instance/mkdss_helpdesk.sqlite3` and `instance/attachments/` into the new installation if upgrading an existing system.

4. Review `.env.example` and set environment variables as required.

5. Start the server:

   `START_SERVER.bat`

The default LAN listener is:

`0.0.0.0:5001`

Clients can then open:

`http://SERVER-IP:5001`

## Installation - Linux

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python app.py --host 0.0.0.0 --port 5001
```

For a production Linux deployment, run the application under a service manager and restrict the listening port to the internal network.

## First administrator

On a new empty database, open:

`http://SERVER-IP:5001/setup`

Create the first System Administrator account.

The setup page is unavailable once an account exists.

No default password or demo account is created.

## Roles

- SYSTEM_ADMINISTRATOR
- IT_MANAGER
- IT_TEAM_LEADER
- IT_TECHNICIAN
- EMPLOYEE

Role authorization is enforced in the backend. Hiding navigation items is not used as the security boundary.

## Ticket workflow

Statuses:

`NEW -> ASSIGNED -> IN_PROGRESS -> PENDING -> IN_PROGRESS -> RESOLVED -> CLOSED`

Priority values:

- LOW
- MEDIUM
- HIGH
- CRITICAL

Priority is immutable after ticket creation.

### Assignment

- IT Support: Team Leader or Technician
- System Administration Support: System Administrator
- Team Leader can manage the IT Support queue
- Manager can assign only requests personally created by the Manager
- Employees and Technicians cannot assign tickets

Only the assigned user can perform operational ticket updates.

## Overdue logic

The application has one authoritative function: `is_ticket_overdue(ticket)`.

Rules:

1. NEW and unassigned for more than 1 hour -> overdue.
2. Any non-CLOSED request older than 24 hours -> overdue.
3. CLOSED requests are never overdue.

The same backend calculation is used by dashboard counts, request lists, ticket details, and overdue notifications.

## Notifications

Notifications are persistent database records.

The system provides:

- notification bell
- unread count
- notification dropdown/page
- mark as read
- mark all as read
- ticket links with authorization checks
- event notifications
- deduplicated overdue notifications

A notification cannot bypass ticket authorization.

## Daily work reports

Daily reports are available to:

- IT Manager
- IT Team Leader
- IT Technician
- System Administrator

The report records:

- date
- tickets worked on
- work summary
- challenges
- actions taken
- pending work
- next-day plan
- remarks
- submission time

Visibility:

- Manager: Manager, Team Leader, Technician, and System Administrator reports
- Team Leader: Team Leader and Technician reports
- Technician: own reports
- System Administrator: own report/export workflow

## Reports

Ticket and daily-report exports support CSV and PDF.

Exports use real database records and the MKDSS local timezone.

## Security

The application implements:

- password hashing
- CSRF protection for state-changing requests
- backend role authorization
- assigned-user update authorization
- attachment authorization
- secure uploaded filenames
- session protection
- XSS-safe Jinja templates
- ORM-based database access
- audit logging
- inactive-account blocking
- professional 403/404 handling

Do not place production secrets in source control.

## Configuration

Available environment variables:

```text
SECRET_KEY=
DATABASE_PATH=
DATABASE_URL=
HOST=0.0.0.0
PORT=5001
MAX_UPLOAD_SIZE=52428800
SESSION_COOKIE_SECURE=0
```

If `SECRET_KEY` is not supplied, the application persists a generated key in `instance/secret_key.txt`. Protect this file.

For Windows LAN-only HTTP deployment, keep `SESSION_COOKIE_SECURE=0`. If HTTPS is later enabled, set it to `1`.

## Backup

Back up both:

1. SQLite database:
   `instance/mkdss_helpdesk.sqlite3`

2. Uploaded attachments:
   `instance/attachments/`

Example Windows helper:

`BACKUP_DATABASE.bat`

Do not overwrite the original database while preparing a backup.

## Restore

1. Stop the application.
2. Restore the SQLite database to `instance/mkdss_helpdesk.sqlite3`.
3. Restore `instance/attachments/`.
4. Restore the correct `instance/secret_key.txt` or set the original `SECRET_KEY`.
5. Start the application.
6. Verify login, tickets, attachments, notifications, and reports.

## GitHub

Do not commit:

- `.venv/`
- `instance/mkdss_helpdesk.sqlite3`
- `instance/attachments/`
- production secret files
- confidential logs
- temporary files

Use `.env.example` as the configuration template.

## Testing

The repository contains automated tests under `tests/`.

Run:

```bash
python -m unittest discover -s tests -v
```

The tests are designed to use an isolated temporary SQLite database and do not modify production business data.

Before deployment, also verify:

- all five roles
- ticket authorization
- assignment rules
- immutable priority
- overdue rules
- notification persistence and authorization
- daily-report visibility
- PDF/CSV exports
- attachment authorization
- LAN access from another PC

## LAN deployment checklist

1. Install Python and dependencies on the internal server.
2. Preserve the existing database and attachments during upgrades.
3. Configure the server host as `0.0.0.0`.
4. Open the chosen TCP port in the internal server firewall only for the required LAN networks.
5. Start the application.
6. From another internal PC browse to `http://SERVER-IP:5001`.
7. Log in with an administrator-created account.
8. Verify that only authorized menus and records are visible.

## Troubleshooting

### Browser cannot connect

Check:

- server process is running
- server is listening on `0.0.0.0`
- Windows/Linux firewall allows the port
- client and server are on reachable LAN networks

### Login sessions disappear after restart

Preserve `instance/secret_key.txt` or configure a stable `SECRET_KEY`.

### Attachments fail

Check:

- `instance/attachments/` exists and is writable
- `MAX_UPLOAD_SIZE` is sufficient
- the logged-in user has permission to the ticket

### Database migration

The application performs only additive, data-preserving SQLite compatibility changes at startup. Always back up the database before upgrading.

## Project structure

```text
MKDSS_IT_Helpdesk/
├── app.py
├── requirements.txt
├── README.md
├── .env.example
├── .gitignore
├── START_SERVER.bat
├── INSTALL_WINDOWS.bat
├── RUN_LINUX.sh
├── BACKUP_DATABASE.bat
├── templates/
├── static/
└── tests/
```

## MKDSS branding

The existing MKDSS logo from the project source is preserved. The application identifies the organization as:

**MK Digital Security Solutions PLC (MKDSS)**

## UI Theme Update

The dashboard UI has been updated using the visual direction supplied by MKDSS: a dark enterprise ticket-dashboard layout with compact KPI cards, status distribution, real ticket trend visualization, priority distribution, department bars, recent requests, and request-type overview.

A light/day theme is also included. The theme toggle is available in the authenticated top navigation and the user's selection is stored locally in the browser. Both themes use the same real database data and authorization rules.

The MKDSS logo shipped with the original project ZIP is preserved and reused; it was not replaced with a third-party logo.

No dashboard chart contains seeded or hardcoded business statistics. When the database has no records, the relevant visualizations display an empty-state message instead.

### Windows timezone note

Windows does not include the IANA timezone database used by Python `zoneinfo`. The installer includes `tzdata`; the application also has a safe Africa/Addis_Ababa (UTC+03:00) fallback so it can start if the timezone package is temporarily unavailable.

## UI build 2.3 — reference dashboard correction

The dashboard UI was rebuilt against the supplied MKDSS/ITSM reference screenshot. The correction includes:

- fixed header/sidebar layout and spacing
- compact professional dark/light theme control
- working notification bell and unread badge
- preserved MKDSS logo from the original project
- reference-style KPI cards, status cards, line chart, priority donut, problem/category view, department view, priority summary, and recent tickets
- responsive layout for smaller screens
- cache-busted stylesheet URL so browsers do not keep an older `app.css`
- dashboard analytics remain based on the authorized real SQLite ticket records; no business demo numbers are added

## v2.5.1 Professional UI

The v2.5.1 interface follows the approved MKDSS ITSM dashboard design: compact enterprise header, MKDSS branding, global ticket search, compact theme switch, notification bell, role-aware sidebar, KPI cards, status distribution, ticket trend, response-time distribution, priority/department/request-type charts, recent-ticket table, and activity feed. Dashboard values are calculated from the authorized live SQLite records; no demo business data is included.

The original `static/mkdss-logo.png` is preserved. Theme selection is stored in the browser and the switch uses a compact professional control rather than a large moon button.

## Completion approval and requester acceptance workflow

A support user marks work `RESOLVED` with a resolution note. The request cannot be directly closed by the assignee. An authorized IT Team Leader (IT Support) or IT Manager must approve the completion with an approval note. The requester is then notified and can review the completion report and confirm acceptance with an acceptance note. Only requester confirmation changes the ticket from `RESOLVED` to `CLOSED`.

Completed Requests reporting includes only tickets that are both management-approved and requester-accepted, with CSV and completion-report PDF support.

## v2.5.3 workflow fixes

- Dashboard content is role-specific for Employee, IT Technician, IT Team Leader, IT Manager, and System Administrator.
- New IT Support requests explicitly notify active IT Team Leaders and IT Managers.
- New System Administration requests explicitly notify active System Administrators and IT Managers.
- Assigned support users have an explicit **Submit Completed Work for Approval** action.
- Completion submission changes the ticket to `RESOLVED`, records the work summary, and notifies the authorized approvers.
- `RESOLVED` remains the internal completion state awaiting approval/requester acceptance; `CLOSED` remains the final accepted state.

## v2.5.6 System-wide UI and QA update
- Applied the professional MKDSS reference UI language to all shared application pages, not only the dashboard.
- Standardized panels, page headers, forms, tables, filters, notifications, ticket detail, reports and administration pages.
- Preserved the supplied MKDSS logo.
- Kept dark/light theme support in the shared shell.
- Added static UI/workflow QA at `tests/qa_v2.5.6_ui_workflow.py`.
- See `QA_STATUS.txt` for exact QA scope and the live-environment limitation.


## v2.5.9 final QA fixes

- Corrected light/dark theme contrast across shared UI, including the global search bar.
- Dashboard From/To reporting dates are real selectable date controls and the selected period drives authorized dashboard metrics and the chart series for every role.
- Corrected notification **Mark as read** behavior: it marks the notification read and returns to the Notifications page; it does not open the related ticket. **Open** remains a separate action.
- Re-ran system-wide static QA after all fixes; see `QA_STATUS.txt` and `tests/qa_v2_5_8_all_three.py`.

Live browser/session QA is not claimed in this build environment because Flask/Werkzeug are unavailable and package installation is offline.

## v2.5.10 — Completion Report readability fix
- Fixed Completion Report request metadata where labels and values could render without visible spacing (for example `StatusClosed`).
- Added dedicated semantic metadata label/value classes with explicit vertical spacing, readable typography, wrapping, and theme-safe backgrounds/borders.
- Retained all v2.5.9 persistence, theme, date-range, role dashboard, and notification behavior.

## v2.5.11 Daily Report Ownership and Reviewer Routing
- Daily reports are stored against the submitting user's account (`DailyReport.user_id`).
- IT Technician reports notify/review through the IT Team Leader.
- IT Team Leader reports notify/review through the IT Manager.
- System Administrator reports notify/review through the IT Manager.
- Manager-submitted reports are stored under the manager account without routing a self-review notification.
- Daily-report drafts are isolated by authenticated user ID in the browser session.
- Successful daily-report submission clears only that user's daily-report drafts.

## v2.5.14 — System Administrator Daily Report Self-Service
- System Administrators can open **Daily Reports** from their account after submitting a report.
- The SAdmin Daily Reports page shows only reports owned by the authenticated SAdmin account.
- SAdmins can open their own report detail and export their own report as PDF or CSV.
- Backend authorization blocks an SAdmin from opening or exporting another user's daily report.
- Technician, Team Leader, Manager, and existing reviewer/report visibility behavior remains unchanged.
- Added dedicated SAdmin daily-report authorization QA in `tests/qa_v2_5_12_sadmin_daily_reports.py`.
