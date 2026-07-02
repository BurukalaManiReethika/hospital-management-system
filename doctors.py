from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from decorators import roles_required
from extensions import db
from models import Doctor

bp = Blueprint("doctors", __name__, url_prefix="/doctors")


@bp.route("/")
@login_required
def doctor_list():
    doctors = Doctor.query.order_by(Doctor.id.desc()).all()
    return render_template("doctors_list.html", doctors=doctors)


@bp.route("/add", methods=["GET", "POST"])
@login_required
@roles_required("admin")
def add_doctor():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Doctor name is required.", "danger")
            return render_template("doctor_form.html", doctor=None, form=request.form)

        doctor = Doctor(
            name=name,
            specialization=request.form.get("specialization"),
            phone=request.form.get("phone"),
            email=request.form.get("email"),
            available=bool(request.form.get("available")),
        )
        db.session.add(doctor)
        db.session.commit()

        flash("Doctor added successfully!", "success")
        return redirect(url_for("doctors.doctor_list"))

    return render_template("doctor_form.html", doctor=None, form=None)


@bp.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
@roles_required("admin")
def edit_doctor(id):
    doctor = Doctor.query.get_or_404(id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Doctor name is required.", "danger")
            return render_template("doctor_form.html", doctor=doctor, form=request.form)

        doctor.name = name
        doctor.specialization = request.form.get("specialization")
        doctor.phone = request.form.get("phone")
        doctor.email = request.form.get("email")
        doctor.available = bool(request.form.get("available"))
        db.session.commit()

        flash("Doctor updated successfully!", "success")
        return redirect(url_for("doctors.doctor_list"))

    return render_template("doctor_form.html", doctor=doctor, form=None)


@bp.route("/delete/<int:id>", methods=["POST"])
@login_required
@roles_required("admin")
def delete_doctor(id):
    doctor = Doctor.query.get_or_404(id)
    db.session.delete(doctor)
    db.session.commit()
    flash("Doctor removed.", "warning")
    return redirect(url_for("doctors.doctor_list"))
