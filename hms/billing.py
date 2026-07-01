"""Billing and payment tracking."""

from dataclasses import dataclass
from typing import Optional

from . import database
from .exceptions import NotFoundError, ValidationError


@dataclass
class Bill:
    id: int
    patient_id: int
    appointment_id: Optional[int]
    admission_id: Optional[int]
    amount: float
    description: Optional[str]
    is_paid: int
    created_on: str


def create_bill(
    patient_id: int,
    amount: float,
    description: str = None,
    appointment_id: int = None,
    admission_id: int = None,
) -> Bill:
    if amount <= 0:
        raise ValidationError("amount must be greater than zero")

    with database.get_connection() as conn:
        if conn.execute("SELECT 1 FROM patients WHERE id = ?", (patient_id,)).fetchone() is None:
            raise NotFoundError(f"No patient found with id {patient_id}")
        cur = conn.execute(
            """INSERT INTO bills (patient_id, appointment_id, admission_id, amount, description)
               VALUES (?, ?, ?, ?, ?)""",
            (patient_id, appointment_id, admission_id, amount, description),
        )
        row = conn.execute("SELECT * FROM bills WHERE id = ?", (cur.lastrowid,)).fetchone()
    return Bill(**dict(row))


def mark_paid(bill_id: int) -> Bill:
    with database.get_connection() as conn:
        cur = conn.execute("UPDATE bills SET is_paid = 1 WHERE id = ?", (bill_id,))
        if cur.rowcount == 0:
            raise NotFoundError(f"No bill found with id {bill_id}")
        row = conn.execute("SELECT * FROM bills WHERE id = ?", (bill_id,)).fetchone()
    return Bill(**dict(row))


def outstanding_balance(patient_id: int) -> float:
    with database.get_connection() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM bills WHERE patient_id = ? AND is_paid = 0",
            (patient_id,),
        ).fetchone()
    return row["total"]


def list_bills_for_patient(patient_id: int) -> list[Bill]:
    with database.get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM bills WHERE patient_id = ? ORDER BY created_on", (patient_id,)
        ).fetchall()
    return [Bill(**dict(r)) for r in rows]
