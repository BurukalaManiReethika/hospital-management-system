from datetime import date, datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from extensions import db
from models import Appointment, Doctor, Patient

bp = Blueprint("appointments", __name__, url_prefix="/appointments")


@bp.route("/")
@login_required
def appointment_list():
    keyword = request.args.get("q", "").strip()

    query = (
        Appointment.query.join(Patient)
        .join(Doctor)
        .add_columns(
            Appointment.id,
            Patient.name.label("patient_name"),
            Doctor.name.label("doctor_name"),
            Doctor.specialization,
            Appointment.appointment_date,
            Appointment.appointment_time,
            Appointment.status,
        )
    )

    if keyword:
        like = f"%{keyword}%"
        query = query.filter(
            db.or_(
                Patient.name.like(like),
                Doctor.name.like(like),
                Doctor.specialization.like(like),
                Appointment.appointment_date.like(like),
            )
        )

    appointments = query.order_by(Appointment.id.desc()).all()
    return render_template("appointments_list.html", appointments=appointments, keyword=keyword)


@bp.route("/add", methods=["GET", "POST"])
@login_required
def add_appointment():
    patients = Patient.query.order_by(Patient.name).all()
    doctors = Doctor.query.order_by(Doctor.name).all()

    if request.method == "POST":
        patient_id = request.form["patient"]
        doctor_id = request.form["doctor"]
        appointment_date = request.form["date"]
        appointment_time = request.form["time"]

        errors = []

        try:
            picked = datetime.strptime(appointment_date, "%Y-%m-%d").date()
            if picked < date.today():
                errors.append("Appointment date can't be in the past.")
        except ValueError:
            errors.append("Please provide a valid date.")

        conflict = Appointment.query.filter_by(
            doctor_id=doctor_id,
            appointment_date=appointment_date,
            appointment_time=appointment_time,
            status="Booked",
        ).first()
        if conflict:
            errors.append("This doctor already has a booked appointment at that time.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template(
                "appointment_form.html", patients=patients, doctors=doctors, form=request.form
            )

        appt = Appointment(
            patient_id=patient_id,
            doctor_id=doctor_id,
            appointment_date=appointment_date,
            appointment_time=appointment_time,
            notes=request.form.get("notes"),
            status="Booked",
        )
        db.session.add(appt)
        db.session.commit()

        flash("Appointment booked successfully!", "success")
        return redirect(url_for("appointments.appointment_list"))

    return render_template("appointment_form.html", patients=patients, doctors=doctors, form=None)


@bp.route("/cancel/<int:id>", methods=["POST"])
@login_required
def cancel_appointment(id):
    appt = Appointment.query.get_or_404(id)
    appt.status = "Cancelled"
    db.session.commit()
    flash("Appointment cancelled.", "warning")
    return redirect(url_for("appointments.appointment_list"))


@bp.route("/complete/<int:id>", methods=["POST"])
@login_required
def complete_appointment(id):
    appt = Appointment.query.get_or_404(id)
    appt.status = "Completed"
    db.session.commit()
    flash("Appointment marked as completed.", "success")
    return redirect(url_for("appointments.appointment_list"))
