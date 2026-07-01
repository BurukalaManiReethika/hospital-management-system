"""Patient CRUD and lookup operations."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from . import database
from .exceptions import NotFoundError, ValidationError


@dataclass
class Patient:
    id: int
    first_name: str
    last_name: str
    date_of_birth: str
    gender: str
    phone: Optional[str]
    address: Optional[str]
    blood_group: Optional[str]
    registered_on: str

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def age(self) -> int:
        dob = datetime.strptime(self.date_of_birth, "%Y-%m-%d").date()
        today = date.today()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _row_to_patient(row) -> Patient:
    return Patient(**dict(row))


def _validate_dob(dob: str) -> None:
    try:
        parsed = datetime.strptime(dob, "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError("date_of_birth must be in YYYY-MM-DD format")
    if parsed > date.today():
        raise ValidationError("date_of_birth cannot be in the future")


def register_patient(
    first_name: str,
    last_name: str,
    date_of_birth: str,
    gender: str,
    phone: str = None,
    address: str = None,
    blood_group: str = None,
) -> Patient:
    if not first_name.strip() or not last_name.strip():
        raise ValidationError("first_name and last_name are required")
    if gender not in ("M", "F", "O"):
        raise ValidationError("gender must be one of 'M', 'F', 'O'")
    _validate_dob(date_of_birth)

    with database.get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO patients
               (first_name, last_name, date_of_birth, gender, phone, address, blood_group)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (first_name.strip(), last_name.strip(), date_of_birth, gender, phone, address, blood_group),
        )
        new_id = cur.lastrowid
    return get_patient(new_id)


def get_patient(patient_id: int) -> Patient:
    with database.get_connection() as conn:
        row = conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"No patient found with id {patient_id}")
    return _row_to_patient(row)


def update_patient(patient_id: int, **fields) -> Patient:
    allowed = {"first_name", "last_name", "date_of_birth", "gender", "phone", "address", "blood_group"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return get_patient(patient_id)
    if "date_of_birth" in updates:
        _validate_dob(updates["date_of_birth"])
    if "gender" in updates and updates["gender"] not in ("M", "F", "O"):
        raise ValidationError("gender must be one of 'M', 'F', 'O'")

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    with database.get_connection() as conn:
        cur = conn.execute(
            f"UPDATE patients SET {set_clause} WHERE id = ?",
            (*updates.values(), patient_id),
        )
        if cur.rowcount == 0:
            raise NotFoundError(f"No patient found with id {patient_id}")
    return get_patient(patient_id)


def delete_patient(patient_id: int) -> None:
    with database.get_connection() as conn:
        cur = conn.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
        if cur.rowcount == 0:
            raise NotFoundError(f"No patient found with id {patient_id}")


def search_patients(query: str) -> list[Patient]:
    """Search by first or last name (case-insensitive, partial match)."""
    like = f"%{query.strip()}%"
    with database.get_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM patients
               WHERE first_name LIKE ? COLLATE NOCASE
                  OR last_name LIKE ? COLLATE NOCASE
               ORDER BY last_name, first_name""",
            (like, like),
        ).fetchall()
    return [_row_to_patient(r) for r in rows]


def list_patients() -> list[Patient]:
    with database.get_connection() as conn:
        rows = conn.execute("SELECT * FROM patients ORDER BY id").fetchall()
    return [_row_to_patient(r) for r in rows]
