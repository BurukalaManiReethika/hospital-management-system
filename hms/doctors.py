"""Doctor and department management."""

from dataclasses import dataclass
from typing import Optional

from . import database
from .exceptions import NotFoundError, ValidationError


@dataclass
class Doctor:
    id: int
    first_name: str
    last_name: str
    specialization: str
    phone: Optional[str]
    consultation_fee: float
    available: int

    @property
    def full_name(self) -> str:
        return f"Dr. {self.first_name} {self.last_name}"


def _row_to_doctor(row) -> Doctor:
    return Doctor(**dict(row))


def add_doctor(
    first_name: str,
    last_name: str,
    specialization: str,
    consultation_fee: float,
    phone: str = None,
) -> Doctor:
    if not first_name.strip() or not last_name.strip():
        raise ValidationError("first_name and last_name are required")
    if consultation_fee < 0:
        raise ValidationError("consultation_fee cannot be negative")

    with database.get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO doctors (first_name, last_name, specialization, phone, consultation_fee)
               VALUES (?, ?, ?, ?, ?)""",
            (first_name.strip(), last_name.strip(), specialization.strip(), phone, consultation_fee),
        )
        new_id = cur.lastrowid
    return get_doctor(new_id)


def get_doctor(doctor_id: int) -> Doctor:
    with database.get_connection() as conn:
        row = conn.execute("SELECT * FROM doctors WHERE id = ?", (doctor_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"No doctor found with id {doctor_id}")
    return _row_to_doctor(row)


def set_availability(doctor_id: int, available: bool) -> Doctor:
    with database.get_connection() as conn:
        cur = conn.execute(
            "UPDATE doctors SET available = ? WHERE id = ?",
            (1 if available else 0, doctor_id),
        )
        if cur.rowcount == 0:
            raise NotFoundError(f"No doctor found with id {doctor_id}")
    return get_doctor(doctor_id)


def list_doctors(specialization: str = None, available_only: bool = False) -> list[Doctor]:
    query = "SELECT * FROM doctors WHERE 1=1"
    params = []
    if specialization:
        query += " AND specialization LIKE ? COLLATE NOCASE"
        params.append(f"%{specialization}%")
    if available_only:
        query += " AND available = 1"
    query += " ORDER BY last_name, first_name"

    with database.get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_doctor(r) for r in rows]


def add_department(name: str, floor: str = None) -> int:
    with database.get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO departments (name, floor) VALUES (?, ?)",
            (name.strip(), floor),
        )
        return cur.lastrowid


def assign_doctor_to_department(doctor_id: int, department_id: int) -> None:
    with database.get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO doctor_departments (doctor_id, department_id) VALUES (?, ?)",
            (doctor_id, department_id),
        )
