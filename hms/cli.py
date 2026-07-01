"""Interactive command-line interface for the Hospital Management System."""

import sys

from . import admissions, appointments, billing, doctors, patients
from .database import init_db
from .exceptions import HMSError

MENU = """
=========================================
   HOSPITAL MANAGEMENT SYSTEM
=========================================
 1. Register new patient
 2. Search patients
 3. Add doctor
 4. List doctors
 5. Book appointment
 6. View doctor's appointments
 7. Cancel appointment
 8. Add bed
 9. Admit patient
10. Discharge patient
11. View current admissions
12. Create bill
13. Mark bill as paid
14. View patient's outstanding balance
 0. Exit
=========================================
"""


def prompt(label: str, required: bool = True) -> str:
    while True:
        value = input(f"{label}: ").strip()
        if value or not required:
            return value
        print("  This field is required.")


def register_patient_flow():
    fn = prompt("First name")
    ln = prompt("Last name")
    dob = prompt("Date of birth (YYYY-MM-DD)")
    gender = prompt("Gender (M/F/O)")
    phone = prompt("Phone", required=False)
    address = prompt("Address", required=False)
    blood_group = prompt("Blood group", required=False)
    p = patients.register_patient(fn, ln, dob, gender, phone or None, address or None, blood_group or None)
    print(f"\nRegistered patient #{p.id}: {p.full_name} (age {p.age})")


def search_patients_flow():
    query = prompt("Search by name")
    results = patients.search_patients(query)
    if not results:
        print("No patients found.")
        return
    for p in results:
        print(f"  #{p.id}  {p.full_name:<25} DOB {p.date_of_birth}  Phone {p.phone or '-'}")


def add_doctor_flow():
    fn = prompt("First name")
    ln = prompt("Last name")
    spec = prompt("Specialization")
    fee = float(prompt("Consultation fee"))
    phone = prompt("Phone", required=False)
    d = doctors.add_doctor(fn, ln, spec, fee, phone or None)
    print(f"\nAdded {d.full_name} (#{d.id}), {d.specialization}")


def list_doctors_flow():
    spec = prompt("Filter by specialization (blank for all)", required=False)
    for d in doctors.list_doctors(specialization=spec or None):
        status = "available" if d.available else "unavailable"
        print(f"  #{d.id}  {d.full_name:<25} {d.specialization:<20} ${d.consultation_fee:.2f}  ({status})")


def book_appointment_flow():
    patient_id = int(prompt("Patient ID"))
    doctor_id = int(prompt("Doctor ID"))
    when = prompt("Scheduled at (YYYY-MM-DD HH:MM)")
    reason = prompt("Reason", required=False)
    appt = appointments.book_appointment(patient_id, doctor_id, when, reason or None)
    print(f"\nBooked appointment #{appt.id} for {appt.scheduled_at}")


def view_doctor_appointments_flow():
    doctor_id = int(prompt("Doctor ID"))
    for a in appointments.list_appointments_for_doctor(doctor_id):
        print(f"  #{a.id}  {a.scheduled_at}  patient #{a.patient_id}  [{a.status}]  {a.reason or ''}")


def cancel_appointment_flow():
    appointment_id = int(prompt("Appointment ID"))
    a = appointments.cancel_appointment(appointment_id)
    print(f"\nAppointment #{a.id} is now {a.status}")


def add_bed_flow():
    ward = prompt("Ward name")
    bed_number = prompt("Bed number")
    b = admissions.add_bed(ward, bed_number)
    print(f"\nAdded bed #{b.id}: {b.ward} / {b.bed_number}")


def admit_patient_flow():
    patient_id = int(prompt("Patient ID"))
    print("Available beds:")
    for b in admissions.list_available_beds():
        print(f"  #{b.id}  {b.ward} / {b.bed_number}")
    bed_id = int(prompt("Bed ID"))
    diagnosis = prompt("Diagnosis", required=False)
    a = admissions.admit_patient(patient_id, bed_id, diagnosis or None)
    print(f"\nAdmitted patient #{a.patient_id} to bed #{a.bed_id}, admission #{a.id}")


def discharge_patient_flow():
    admission_id = int(prompt("Admission ID"))
    a = admissions.discharge_patient(admission_id)
    print(f"\nDischarged admission #{a.id} at {a.discharged_on}")


def view_admissions_flow():
    for a in admissions.current_admissions():
        print(f"  #{a.id}  patient #{a.patient_id}  bed #{a.bed_id}  admitted {a.admitted_on}")


def create_bill_flow():
    patient_id = int(prompt("Patient ID"))
    amount = float(prompt("Amount"))
    description = prompt("Description", required=False)
    b = billing.create_bill(patient_id, amount, description or None)
    print(f"\nCreated bill #{b.id} for ${b.amount:.2f}")


def mark_paid_flow():
    bill_id = int(prompt("Bill ID"))
    b = billing.mark_paid(bill_id)
    print(f"\nBill #{b.id} marked as paid")


def outstanding_balance_flow():
    patient_id = int(prompt("Patient ID"))
    total = billing.outstanding_balance(patient_id)
    print(f"\nOutstanding balance for patient #{patient_id}: ${total:.2f}")


ACTIONS = {
    "1": register_patient_flow,
    "2": search_patients_flow,
    "3": add_doctor_flow,
    "4": list_doctors_flow,
    "5": book_appointment_flow,
    "6": view_doctor_appointments_flow,
    "7": cancel_appointment_flow,
    "8": add_bed_flow,
    "9": admit_patient_flow,
    "10": discharge_patient_flow,
    "11": view_admissions_flow,
    "12": create_bill_flow,
    "13": mark_paid_flow,
    "14": outstanding_balance_flow,
}


def main():
    init_db()
    print("Database ready.")
    while True:
        print(MENU)
        choice = input("Choose an option: ").strip()
        if choice == "0":
            print("Goodbye!")
            sys.exit(0)
        action = ACTIONS.get(choice)
        if not action:
            print("Invalid option, try again.")
            continue
        try:
            action()
        except HMSError as e:
            print(f"\n  Error: {e}")
        except ValueError as e:
            print(f"\n  Invalid input: {e}")
        except KeyboardInterrupt:
            print("\nGoodbye!")
            sys.exit(0)


if __name__ == "__main__":
    main()
