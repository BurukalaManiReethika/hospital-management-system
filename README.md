# Hospital Management Systems

A Flask + SQLite web app for running a small clinic or hospital's front
desk: patients, doctors, appointments, admissions, billing, and a **live
patient queue** with QR tokens and SMS notifications.

## Features

- **Patient management** — register, search, edit, and remove patient records
- **Doctor management** — add doctors, track specialization, and toggle
  live **availability** (Available / Unavailable)
- **Live queue tracking** — walk-in or existing patients get a numbered
  token per doctor per day; the queue board (`/queue`) auto-refreshes
  every few seconds so staff can see who's waiting, who's in with the
  doctor, and estimated wait times without reloading the page
- **QR token generation** — every token gets a QR code (generated on the
  fly, nothing saved to disk) that links to a public, no-login status
  page the patient can bookmark or scan to check their place in line
- **SMS notifications** — patients get a text when their token is
  created and when they're called in. Works out of the box in
  **simulated mode** (messages are logged and viewable on `/notifications`)
  and switches to real SMS automatically once Twilio credentials are set
  (see below)
- **Estimated waiting time** — computed from the number of people still
  waiting ahead of you for that doctor, multiplied by that doctor's
  average consultation time (configurable per doctor)
- **Appointment scheduling** — book appointments with double-booking
  prevention for the same doctor/date/time
- **Admissions** — track bed/ward assignment and discharge
- **Billing** — create bills (consultation + medicine + room fees), mark paid,
  and download a **PDF invoice** per bill or a full **PDF billing report**
- **Login & role-based access** — admin / doctor / receptionist accounts.
  Admins manage doctors and users; receptionists handle patients,
  appointments and billing; doctors can add medical records. A default
  admin account is seeded on first run (see below)
- **Patient medical history & prescriptions** — each patient has a profile
  page (`/patients/<id>`) showing past visits, diagnoses, prescriptions,
  appointments and bills in one place, with search on the patients list
- **Dashboard analytics** — charts for revenue (paid vs unpaid),
  appointment status breakdown, today's queue status, and admissions,
  backed by a small JSON API (`/api/dashboard/stats`)

## Logging in

A default admin account is created automatically the first time the app
runs:

```
username: admin
password: admin123
```

Change these before deploying publicly by setting `ADMIN_USERNAME` and
`ADMIN_PASSWORD` as environment variables (only takes effect on a fresh
database — it won't overwrite an existing admin user). Also set a real
`SECRET_KEY` env var in production; it defaults to a fixed dev value
otherwise. Once logged in as admin, create additional accounts under
**Users → Add User** and assign each the `admin`, `doctor`, or
`receptionist` role.

## Project structure

```
hospital-management-system/
├── app.py              # All routes, DB setup/migration, SMS + queue logic
├── templates/           # Jinja2 templates (Bootstrap 5)
├── static/
│   ├── css/style.css
│   └── js/app.js
├── requirements.txt
└── render.yaml           # Render.com deploy config
```

The app uses raw `sqlite3` (no ORM) against a single `hospital.db` file
that's created automatically on first run, with a small migration step
that adds new columns to older databases (e.g. deployments that predate
the queue feature) without wiping existing data. `app.py` is
self-contained — routes, auth, PDF export and all.

> **Note:** `auth.py`, `models.py`, `decorators.py`, `extensions.py`,
> `config.py`, `dashboard.py`, `patients.py`, `doctors.py`,
> `appointments.py`, `billing.py`, and `admission.py` are an earlier,
> unfinished Flask-SQLAlchemy/Flask-Login scaffold that isn't imported by
> `app.py` and isn't in `requirements.txt`. The login/roles feature
> described below was implemented directly in `app.py` using the same
> `sqlite3` style as the rest of the app instead, to keep one consistent
> architecture. You can safely delete those files, or finish wiring them
> up yourself if you'd rather move to SQLAlchemy.

## Getting started

**Requirements:** Python 3.10+

```bash
git clone https://github.com/<your-username>/hospital-management-system.git
cd hospital-management-system

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

python3 app.py
```

The app runs at `http://localhost:5000`. `hospital.db` is created
automatically on first request.

## Enabling real SMS (optional)

Without any configuration, "sending" an SMS just logs the message to the
`notifications` table, viewable on the **SMS Log** page — handy for demos
and local dev without a Twilio account.

To send real texts, set these environment variables (e.g. in Render's
dashboard, or a local `.env` loaded before `app.py` starts):

```
TWILIO_ACCOUNT_SID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_FROM_NUMBER=+1XXXXXXXXXX
```

No code changes needed — `send_sms()` in `app.py` detects the credentials
and switches from simulated to real sends automatically.

## How the live queue works

1. A receptionist opens **Live Queue → Add to Queue**, picks a doctor
   (only doctors marked *Available* are selectable) and either an
   existing patient or a walk-in name/phone.
2. A token number is generated (numbering restarts at 1 each day, per
   doctor) and an SMS is sent with the token number, estimated wait, and
   a link to the live status page.
3. The patient can open that link (or scan the QR code shown on the
   staff-facing token page) to see their status update live — no login,
   no app install.
4. Staff use **Call Next Patient** on the queue board to advance the
   queue; the patient gets a "please proceed to the doctor's room" text,
   and everyone still waiting sees their estimated wait shrink
   automatically.

## Deploying

`render.yaml` is already set up for [Render](https://render.com):
it installs `requirements.txt` and runs `gunicorn app:app`. Add the
Twilio environment variables above in the Render dashboard if you want
real SMS in production.

## License

MIT — see [LICENSE](LICENSE) if present, or the repository's license terms.
