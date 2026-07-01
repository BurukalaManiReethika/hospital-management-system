"""Database connection handling and schema initialization."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "hospital.db"

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS patients (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name      TEXT NOT NULL,
    last_name       TEXT NOT NULL,
    date_of_birth   TEXT NOT NULL,
    gender          TEXT NOT NULL CHECK (gender IN ('M', 'F', 'O')),
    phone           TEXT,
    address         TEXT,
    blood_group     TEXT,
    registered_on   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS doctors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name      TEXT NOT NULL,
    last_name       TEXT NOT NULL,
    specialization  TEXT NOT NULL,
    phone           TEXT,
    consultation_fee REAL NOT NULL DEFAULT 0,
    available       INTEGER NOT NULL DEFAULT 1 CHECK (available IN (0, 1))
);

CREATE TABLE IF NOT EXISTS departments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,
    floor           TEXT
);

CREATE TABLE IF NOT EXISTS doctor_departments (
    doctor_id       INTEGER NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    department_id   INTEGER NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    PRIMARY KEY (doctor_id, department_id)
);

CREATE TABLE IF NOT EXISTS appointments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id      INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    doctor_id       INTEGER NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    scheduled_at    TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'SCHEDULED'
                    CHECK (status IN ('SCHEDULED', 'COMPLETED', 'CANCELLED', 'NO_SHOW')),
    reason          TEXT,
    created_on      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS beds (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ward            TEXT NOT NULL,
    bed_number      TEXT NOT NULL,
    is_occupied     INTEGER NOT NULL DEFAULT 0 CHECK (is_occupied IN (0, 1)),
    UNIQUE (ward, bed_number)
);

CREATE TABLE IF NOT EXISTS admissions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id      INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    bed_id          INTEGER NOT NULL REFERENCES beds(id),
    admitted_on     TEXT NOT NULL DEFAULT (datetime('now')),
    discharged_on   TEXT,
    diagnosis       TEXT
);

CREATE TABLE IF NOT EXISTS bills (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id      INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    appointment_id  INTEGER REFERENCES appointments(id) ON DELETE SET NULL,
    admission_id    INTEGER REFERENCES admissions(id) ON DELETE SET NULL,
    amount          REAL NOT NULL,
    description     TEXT,
    is_paid         INTEGER NOT NULL DEFAULT 0 CHECK (is_paid IN (0, 1)),
    created_on      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_appointments_patient ON appointments(patient_id);
CREATE INDEX IF NOT EXISTS idx_appointments_doctor ON appointments(doctor_id);
CREATE INDEX IF NOT EXISTS idx_admissions_patient ON admissions(patient_id);
CREATE INDEX IF NOT EXISTS idx_bills_patient ON bills(patient_id);
"""


def init_db(db_path: Path = DB_PATH) -> None:
    """Create the database file and schema if they don't already exist."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


@contextmanager
def get_connection(db_path: Path = None):
    """Yield a SQLite connection with foreign keys enforced and row access by name."""
    if db_path is None:
        db_path = DB_PATH
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
