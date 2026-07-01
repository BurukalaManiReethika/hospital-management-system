"""Populate the database with sample data for demoing the system.

Run with: python3 seed_demo_data.py
"""

from hms import admissions, appointments, billing, doctors, patients
from hms.database import init_db


def main():
    init_db()

    alice = patients.register_patient("Alice", "Ray", "1992-03-10", "F", phone="555-0101")
    bob = patients.register_patient("Bob", "Nguyen", "1978-11-02", "M", phone="555-0102")
    carol = patients.register_patient("Carol", "Diaz", "2001-07-19", "F", phone="555-0103")

    dr_cole = doctors.add_doctor("Sam", "Cole", "General Medicine", 100.0, phone="555-0201")
    dr_khan = doctors.add_doctor("Amina", "Khan", "Cardiology", 180.0, phone="555-0202")
    dr_lopez = doctors.add_doctor("Mateo", "Lopez", "Pediatrics", 120.0, phone="555-0203")

    appointments.book_appointment(alice.id, dr_cole.id, "2099-06-01 09:00", reason="Annual checkup")
    appointments.book_appointment(bob.id, dr_khan.id, "2099-06-02 14:30", reason="Chest pain follow-up")
    appointments.book_appointment(carol.id, dr_lopez.id, "2099-06-03 11:00", reason="Vaccination")

    bed_a1 = admissions.add_bed("General Ward", "A1")
    admissions.add_bed("General Ward", "A2")
    admissions.add_bed("ICU", "ICU-1")

    admissions.admit_patient(bob.id, bed_a1.id, diagnosis="Observation post chest pain")

    billing.create_bill(alice.id, 100.0, description="Consultation - General Medicine")
    billing.create_bill(bob.id, 450.0, description="Ward stay + Cardiology consult")
    billing.create_bill(carol.id, 120.0, description="Pediatric consultation + vaccine")

    print("Seeded database with demo patients, doctors, appointments, admissions, and bills.")
    print("Run 'python3 -m hms.cli' to explore the system interactively.")


if __name__ == "__main__":
    main()
