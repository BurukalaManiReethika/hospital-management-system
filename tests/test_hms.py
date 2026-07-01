"""Test suite for the Hospital Management System.

Run with: pytest tests/test_hms.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hms import admissions, appointments, billing, database, doctors, patients
from hms.exceptions import ConflictError, NotFoundError, ValidationError


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """Point every module at a fresh temp database for each test."""
    path = tmp_path / "test_hospital.db"
    monkeypatch.setattr(database, "DB_PATH", path)
    database.init_db(path)
    return path


# ---------- Patients ----------

def test_register_and_get_patient(db_path):
    p = patients.register_patient("Jane", "Doe", "1990-05-15", "F", phone="555-1234")
    assert p.id == 1
    fetched = patients.get_patient(p.id)
    assert fetched.full_name == "Jane Doe"
    assert fetched.age >= 30


def test_register_patient_invalid_gender(db_path):
    with pytest.raises(ValidationError):
        patients.register_patient("Jane", "Doe", "1990-05-15", "X")


def test_register_patient_future_dob(db_path):
    with pytest.raises(ValidationError):
        patients.register_patient("Jane", "Doe", "2999-01-01", "F")


def test_get_missing_patient(db_path):
    with pytest.raises(NotFoundError):
        patients.get_patient(999)


def test_search_patients(db_path):
    patients.register_patient("Alice", "Smith", "1985-01-01", "F")
    patients.register_patient("Bob", "Smithson", "1990-01-01", "M")
    patients.register_patient("Carol", "Jones", "1970-01-01", "F")
    results = patients.search_patients("Smith")
    assert len(results) == 2


def test_update_patient(db_path):
    p = patients.register_patient("Jane", "Doe", "1990-05-15", "F")
    updated = patients.update_patient(p.id, phone="555-9999")
    assert updated.phone == "555-9999"


def test_delete_patient(db_path):
    p = patients.register_patient("Jane", "Doe", "1990-05-15", "F")
    patients.delete_patient(p.id)
    with pytest.raises(NotFoundError):
        patients.get_patient(p.id)


# ---------- Doctors ----------

def test_add_doctor(db_path):
    d = doctors.add_doctor("John", "Smith", "Cardiology", 150.0)
    assert d.full_name == "Dr. John Smith"
    assert d.available == 1


def test_add_doctor_negative_fee(db_path):
    with pytest.raises(ValidationError):
        doctors.add_doctor("John", "Smith", "Cardiology", -10.0)


def test_list_doctors_by_specialization(db_path):
    doctors.add_doctor("John", "Smith", "Cardiology", 150.0)
    doctors.add_doctor("Amy", "Lee", "Neurology", 200.0)
    results = doctors.list_doctors(specialization="cardio")
    assert len(results) == 1
    assert results[0].last_name == "Smith"


def test_set_availability(db_path):
    d = doctors.add_doctor("John", "Smith", "Cardiology", 150.0)
    updated = doctors.set_availability(d.id, False)
    assert updated.available == 0


# ---------- Appointments ----------

def test_book_appointment(db_path):
    p = patients.register_patient("Jane", "Doe", "1990-05-15", "F")
    d = doctors.add_doctor("John", "Smith", "Cardiology", 150.0)
    appt = appointments.book_appointment(p.id, d.id, "2099-01-01 10:00", reason="Checkup")
    assert appt.status == "SCHEDULED"


def test_book_appointment_double_booking_conflict(db_path):
    p1 = patients.register_patient("Jane", "Doe", "1990-05-15", "F")
    p2 = patients.register_patient("Jim", "Beam", "1988-02-20", "M")
    d = doctors.add_doctor("John", "Smith", "Cardiology", 150.0)
    appointments.book_appointment(p1.id, d.id, "2099-01-01 10:00")
    with pytest.raises(ConflictError):
        appointments.book_appointment(p2.id, d.id, "2099-01-01 10:15")


def test_book_appointment_unavailable_doctor(db_path):
    p = patients.register_patient("Jane", "Doe", "1990-05-15", "F")
    d = doctors.add_doctor("John", "Smith", "Cardiology", 150.0)
    doctors.set_availability(d.id, False)
    with pytest.raises(ConflictError):
        appointments.book_appointment(p.id, d.id, "2099-01-01 10:00")


def test_book_appointment_in_past(db_path):
    p = patients.register_patient("Jane", "Doe", "1990-05-15", "F")
    d = doctors.add_doctor("John", "Smith", "Cardiology", 150.0)
    with pytest.raises(ValidationError):
        appointments.book_appointment(p.id, d.id, "2000-01-01 10:00")


def test_cancel_appointment(db_path):
    p = patients.register_patient("Jane", "Doe", "1990-05-15", "F")
    d = doctors.add_doctor("John", "Smith", "Cardiology", 150.0)
    appt = appointments.book_appointment(p.id, d.id, "2099-01-01 10:00")
    cancelled = appointments.cancel_appointment(appt.id)
    assert cancelled.status == "CANCELLED"


# ---------- Admissions / Beds ----------

def test_admit_and_discharge_patient(db_path):
    p = patients.register_patient("Jane", "Doe", "1990-05-15", "F")
    bed = admissions.add_bed("ICU", "A1")
    admission = admissions.admit_patient(p.id, bed.id, diagnosis="Observation")
    assert admission.discharged_on is None

    beds_left = admissions.list_available_beds()
    assert len(beds_left) == 0

    discharged = admissions.discharge_patient(admission.id)
    assert discharged.discharged_on is not None

    beds_left = admissions.list_available_beds()
    assert len(beds_left) == 1


def test_admit_to_occupied_bed_fails(db_path):
    p1 = patients.register_patient("Jane", "Doe", "1990-05-15", "F")
    p2 = patients.register_patient("Jim", "Beam", "1988-02-20", "M")
    bed = admissions.add_bed("ICU", "A1")
    admissions.admit_patient(p1.id, bed.id)
    with pytest.raises(ConflictError):
        admissions.admit_patient(p2.id, bed.id)


def test_double_discharge_fails(db_path):
    p = patients.register_patient("Jane", "Doe", "1990-05-15", "F")
    bed = admissions.add_bed("ICU", "A1")
    admission = admissions.admit_patient(p.id, bed.id)
    admissions.discharge_patient(admission.id)
    with pytest.raises(ValidationError):
        admissions.discharge_patient(admission.id)


# ---------- Billing ----------

def test_create_bill_and_pay(db_path):
    p = patients.register_patient("Jane", "Doe", "1990-05-15", "F")
    bill = billing.create_bill(p.id, 250.0, description="Consultation")
    assert bill.is_paid == 0
    assert billing.outstanding_balance(p.id) == 250.0

    billing.mark_paid(bill.id)
    assert billing.outstanding_balance(p.id) == 0.0


def test_create_bill_invalid_amount(db_path):
    p = patients.register_patient("Jane", "Doe", "1990-05-15", "F")
    with pytest.raises(ValidationError):
        billing.create_bill(p.id, -50.0)


def test_outstanding_balance_multiple_bills(db_path):
    p = patients.register_patient("Jane", "Doe", "1990-05-15", "F")
    billing.create_bill(p.id, 100.0)
    billing.create_bill(p.id, 50.0)
    assert billing.outstanding_balance(p.id) == 150.0
