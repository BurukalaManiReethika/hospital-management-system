from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="receptionist")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"


class Patient(db.Model):
    __tablename__ = "patients"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    age = db.Column(db.Integer)
    gender = db.Column(db.String(20))
    phone = db.Column(db.String(20))
    address = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    appointments = db.relationship(
        "Appointment", backref="patient", cascade="all, delete-orphan"
    )
    admissions = db.relationship(
        "Admission", backref="patient", cascade="all, delete-orphan"
    )
    bills = db.relationship("Bill", backref="patient", cascade="all, delete-orphan")


class Doctor(db.Model):
    __tablename__ = "doctors"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    specialization = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    available = db.Column(db.Boolean, default=True)

    appointments = db.relationship("Appointment", backref="doctor")


class Appointment(db.Model):
    __tablename__ = "appointments"

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey("doctors.id"), nullable=False)
    appointment_date = db.Column(db.String(10), nullable=False)  # YYYY-MM-DD
    appointment_time = db.Column(db.String(5), nullable=False)  # HH:MM
    status = db.Column(db.String(20), default="Booked")  # Booked/Completed/Cancelled
    notes = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Admission(db.Model):
    __tablename__ = "admissions"

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    bed_number = db.Column(db.String(20))
    ward = db.Column(db.String(50))
    admitted_on = db.Column(db.String(20))
    discharged_on = db.Column(db.String(20))
    discharged = db.Column(db.Boolean, default=False)


class Bill(db.Model):
    __tablename__ = "bills"

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    consultation_fee = db.Column(db.Float, default=0)
    medicine_fee = db.Column(db.Float, default=0)
    room_fee = db.Column(db.Float, default=0)
    total = db.Column(db.Float, default=0)
    paid = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
