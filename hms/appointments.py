"""Appointment scheduling with double-booking prevention."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from . import database
from .exceptions import ConflictError, NotFoundError, ValidationError

SLOT_DURATION_MINUTES = 30


@dataclass
class Appointment:
    id: int
    patient_id: int
    doctor_id: int
    scheduled_at: str
    status: str
    reason: Optional[str]
    created_on: str


def _row_to_appointment(row) -> Appointment:
    return Appointment(**dict(row))


def _parse_dt(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M")
    except ValueError:
        raise ValidationError("scheduled_at must be in 'YYYY-MM-DD HH:MM' format")


def book_appointment(patient_id: int, doctor_id: int, scheduled_at: str, reason: str = None) -> Appointment:
    appt_time = _parse_dt(scheduled_at)
    if appt_time < datetime.now():
        raise ValidationError("Cannot book an appointment in the past")

    window_start = appt_time - timedelta(minutes=SLOT_DURATION_MINUTES - 1)
    window_end = appt_time + timedelta(minutes=SLOT_DURATION_MINUTES - 1)

    with database.get_connection() as conn:
        # Verify patient and doctor exist
        if conn.execute("SELECT 1 FROM patients WHERE id = ?", (patient_id,)).fetchone() is None:
            raise NotFoundError(f"No patient found with id {patient_id}")
        doctor_row = conn.execute("SELECT available FROM doctors WHERE id = ?", (doctor_id,)).fetchone()
        if doctor_row is None:
            raise NotFoundError(f"No doctor found with id {doctor_id}")
        if not doctor_row["available"]:
            raise ConflictError("Doctor is not currently available for appointments")

        # Check for a conflicting slot with the same doctor
        conflict = conn.execute(
            """SELECT 1 FROM appointments
               WHERE doctor_id = ?
                 AND status = 'SCHEDULED'
                 AND scheduled_at BETWEEN ? AND ?""",
            (doctor_id, window_start.strftime("%Y-%m-%d %H:%M"), window_end.strftime("%Y-%m-%d %H:%M")),
        ).fetchone()
        if conflict:
            raise ConflictError("Doctor already has an appointment in that time slot")

        cur = conn.execute(
            """INSERT INTO appointments (patient_id, doctor_id, scheduled_at, reason)
               VALUES (?, ?, ?, ?)""",
            (patient_id, doctor_id, appt_time.strftime("%Y-%m-%d %H:%M"), reason),
        )
        new_id = cur.lastrowid
    return get_appointment(new_id)


def get_appointment(appointment_id: int) -> Appointment:
    with database.get_connection() as conn:
        row = conn.execute("SELECT * FROM appointments WHERE id = ?", (appointment_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"No appointment found with id {appointment_id}")
    return _row_to_appointment(row)


def update_status(appointment_id: int, status: str) -> Appointment:
    valid = {"SCHEDULED", "COMPLETED", "CANCELLED", "NO_SHOW"}
    if status not in valid:
        raise ValidationError(f"status must be one of {sorted(valid)}")
    with database.get_connection() as conn:
        cur = conn.execute(
            "UPDATE appointments SET status = ? WHERE id = ?", (status, appointment_id)
        )
        if cur.rowcount == 0:
            raise NotFoundError(f"No appointment found with id {appointment_id}")
    return get_appointment(appointment_id)


def cancel_appointment(appointment_id: int) -> Appointment:
    return update_status(appointment_id, "CANCELLED")


def list_appointments_for_doctor(doctor_id: int, status: str = None) -> list[Appointment]:
    query = "SELECT * FROM appointments WHERE doctor_id = ?"
    params = [doctor_id]
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY scheduled_at"
    with database.get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_appointment(r) for r in rows]


def list_appointments_for_patient(patient_id: int, status: str = None) -> list[Appointment]:
    query = "SELECT * FROM appointments WHERE patient_id = ?"
    params = [patient_id]
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY scheduled_at"
    with database.get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_appointment(r) for r in rows]


def upcoming_appointments(within_hours: int = 24) -> list[Appointment]:
    now = datetime.now()
    end = now + timedelta(hours=within_hours)
    with database.get_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM appointments
               WHERE status = 'SCHEDULED'
                 AND scheduled_at BETWEEN ? AND ?
               ORDER BY scheduled_at""",
            (now.strftime("%Y-%m-%d %H:%M"), end.strftime("%Y-%m-%d %H:%M")),
        ).fetchall()
    return [_row_to_appointment(r) for r in rows]
