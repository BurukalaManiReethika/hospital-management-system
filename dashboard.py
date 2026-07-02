from datetime import date

from flask import Blueprint, jsonify, render_template
from flask_login import login_required
from sqlalchemy import func

from extensions import db
from models import Admission, Appointment, Bill, Doctor, Patient

bp = Blueprint("dashboard", __name__)


@bp.route("/")
@login_required
def index():
    patient_count = Patient.query.count()
    doctor_count = Doctor.query.count()
    appointment_count = Appointment.query.count()
    admission_count = Admission.query.filter_by(discharged=False).count()
    revenue = db.session.query(func.coalesce(func.sum(Bill.total), 0)).filter(
        Bill.paid.is_(True)
    ).scalar()
    outstanding = db.session.query(func.coalesce(func.sum(Bill.total), 0)).filter(
        Bill.paid.is_(False)
    ).scalar()

    today = date.today().isoformat()
    todays_appointments = (
        Appointment.query.filter_by(appointment_date=today, status="Booked")
        .order_by(Appointment.appointment_time)
        .all()
    )

    status_counts = dict(
        db.session.query(Appointment.status, func.count(Appointment.id))
        .group_by(Appointment.status)
        .all()
    )

    return render_template(
        "dashboard.html",
        patient_count=patient_count,
        doctor_count=doctor_count,
        appointment_count=appointment_count,
        admission_count=admission_count,
        revenue=revenue,
        outstanding=outstanding,
        todays_appointments=todays_appointments,
        status_counts=status_counts,
    )


@bp.route("/api/revenue-by-month")
@login_required
def revenue_by_month():
    """JSON data for the dashboard revenue chart."""
    rows = (
        db.session.query(
            func.strftime("%Y-%m", Bill.created_at).label("month"),
            func.sum(Bill.total),
        )
        .filter(Bill.paid.is_(True))
        .group_by("month")
        .order_by("month")
        .all()
    )
    return jsonify({"labels": [r[0] for r in rows], "values": [r[1] for r in rows]})
