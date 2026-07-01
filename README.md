# Hospital Management System

A command-line Hospital Management System built in pure Python with SQLite —
no external database server or framework required. Designed as a clean,
well-tested reference implementation covering the core workflows a small
clinic or hospital needs.

## Features

- **Patient management** — register, search, update, and remove patient records
- **Doctor management** — add doctors, track specializations and availability
- **Appointment scheduling** — book appointments with automatic double-booking
  prevention (checks the doctor's schedule for conflicts) and past-date validation
- **Bed & admission tracking** — manage ward/bed inventory, admit and discharge
  patients, and prevent double-assignment of an occupied bed
- **Billing** — create bills tied to patients, appointments, or admissions;
  track paid/unpaid status and outstanding balances

## Project structure

```
hospital-management-system/
├── hms/
│   ├── __init__.py
│   ├── database.py       # SQLite connection + schema
│   ├── exceptions.py     # Custom exception types
│   ├── patients.py        # Patient CRUD
│   ├── doctors.py         # Doctor & department management
│   ├── appointments.py    # Appointment scheduling logic
│   ├── admissions.py      # Bed inventory + admit/discharge
│   ├── billing.py         # Billing & payments
│   └── cli.py              # Interactive CLI entry point
├── tests/
│   └── test_hms.py         # pytest suite (22 tests)
├── seed_demo_data.py       # Populates sample data for a quick demo
├── requirements.txt
├── LICENSE
└── README.md
```

## Getting started

**Requirements:** Python 3.10+

```bash
# Clone the repo
git clone https://github.com/<your-username>/hospital-management-system.git
cd hospital-management-system

# (optional) create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# install dev/test dependencies
pip install -r requirements.txt
```

### Run the interactive CLI

```bash
python3 -m hms.cli
```

This initializes a local SQLite database at `data/hospital.db` on first run
and drops you into a menu-driven interface for registering patients, booking
appointments, admitting patients, and managing bills.

### Load demo data

```bash
python3 seed_demo_data.py
```

Seeds a few patients, doctors, appointments, an admission, and some bills so
you can explore the CLI immediately instead of starting from an empty database.

### Run the tests

```bash
python3 -m pytest tests/ -v
```

## Design notes

- **SQLite with foreign keys enforced** — zero setup, but real relational
  integrity (`PRAGMA foreign_keys = ON`), cascading deletes where appropriate.
- **Business rules live in the service layer, not the UI** — `hms/appointments.py`,
  `hms/admissions.py`, etc. raise typed exceptions (`ConflictError`,
  `ValidationError`, `NotFoundError`) that the CLI (or any other frontend you
  bolt on later — a REST API, a GUI) can catch and handle consistently.
- **Double-booking prevention** — appointments are checked against a
  30-minute window around the requested slot for the same doctor.
- **Bed occupancy is transactional** — admitting/discharging a patient updates
  the bed's `is_occupied` flag in the same connection as the admission record,
  so the two can't drift out of sync.

## Extending this project

Some natural next steps if you want to build on this:

- Wrap the `hms` package in a REST API (FastAPI/Flask) for a web frontend
- Add role-based authentication (admin, doctor, receptionist)
- Add a prescriptions / medication tracking module
- Export bills/reports to PDF
- Swap SQLite for PostgreSQL for multi-user concurrent access

## License

MIT — see [LICENSE](LICENSE).
