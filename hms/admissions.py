"""Bed inventory and patient admission/discharge management."""

from dataclasses import dataclass
from typing import Optional

from . import database
from .exceptions import ConflictError, NotFoundError, ValidationError


@dataclass
class Bed:
    id: int
    ward: str
    bed_number: str
    is_occupied: int


@dataclass
class Admission:
    id: int
    patient_id: int
    bed_id: int
    admitted_on: str
    discharged_on: Optional[str]
    diagnosis: Optional[str]


def add_bed(ward: str, bed_number: str) -> Bed:
    with database.get_connection() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO beds (ward, bed_number) VALUES (?, ?)", (ward.strip(), bed_number.strip())
            )
        except Exception as e:
            raise ConflictError(f"Bed {bed_number} already exists in ward {ward}") from e
        row = conn.execute("SELECT * FROM beds WHERE id = ?", (cur.lastrowid,)).fetchone()
    return Bed(**dict(row))


def list_available_beds(ward: str = None) -> list[Bed]:
    query = "SELECT * FROM beds WHERE is_occupied = 0"
    params = []
    if ward:
        query += " AND ward = ?"
        params.append(ward)
    query += " ORDER BY ward, bed_number"
    with database.get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [Bed(**dict(r)) for r in rows]


def admit_patient(patient_id: int, bed_id: int, diagnosis: str = None) -> Admission:
    with database.get_connection() as conn:
        if conn.execute("SELECT 1 FROM patients WHERE id = ?", (patient_id,)).fetchone() is None:
            raise NotFoundError(f"No patient found with id {patient_id}")

        bed_row = conn.execute("SELECT is_occupied FROM beds WHERE id = ?", (bed_id,)).fetchone()
        if bed_row is None:
            raise NotFoundError(f"No bed found with id {bed_id}")
        if bed_row["is_occupied"]:
            raise ConflictError("Bed is already occupied")

        cur = conn.execute(
            "INSERT INTO admissions (patient_id, bed_id, diagnosis) VALUES (?, ?, ?)",
            (patient_id, bed_id, diagnosis),
        )
        conn.execute("UPDATE beds SET is_occupied = 1 WHERE id = ?", (bed_id,))
        row = conn.execute("SELECT * FROM admissions WHERE id = ?", (cur.lastrowid,)).fetchone()
    return Admission(**dict(row))


def discharge_patient(admission_id: int) -> Admission:
    with database.get_connection() as conn:
        row = conn.execute("SELECT * FROM admissions WHERE id = ?", (admission_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"No admission found with id {admission_id}")
        if row["discharged_on"] is not None:
            raise ValidationError("Patient has already been discharged for this admission")

        conn.execute(
            "UPDATE admissions SET discharged_on = datetime('now') WHERE id = ?", (admission_id,)
        )
        conn.execute("UPDATE beds SET is_occupied = 0 WHERE id = ?", (row["bed_id"],))
        updated = conn.execute("SELECT * FROM admissions WHERE id = ?", (admission_id,)).fetchone()
    return Admission(**dict(updated))


def current_admissions() -> list[Admission]:
    with database.get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM admissions WHERE discharged_on IS NULL ORDER BY admitted_on"
        ).fetchall()
    return [Admission(**dict(r)) for r in rows]
