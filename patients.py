import csv
import io

from flask import Blueprint, Response, flash, redirect, render_template, request, url_for
from flask_login import login_required

from extensions import db
from models import Patient

bp = Blueprint("patients", __name__, url_prefix="/patients")


def _validate(form):
    errors = []
    name = form.get("name", "").strip()
    age = form.get("age", "").strip()

    if not name:
        errors.append("Name is required.")
    if age and not age.isdigit():
        errors.append("Age must be a whole number.")
    elif age and not (0 <= int(age) <= 150):
        errors.append("Age must be between 0 and 150.")

    return errors


@bp.route("/")
@login_required
def patient_list():
    keyword = request.args.get("q", "").strip()
    query = Patient.query
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(
            db.or_(
                Patient.name.like(like),
                Patient.phone.like(like),
                Patient.gender.like(like),
            )
        )
    patients = query.order_by(Patient.id.desc()).all()
    return render_template("patients_list.html", patients=patients, keyword=keyword)


@bp.route("/add", methods=["GET", "POST"])
@login_required
def add_patient():
    if request.method == "POST":
        errors = _validate(request.form)
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("patient_form.html", patient=None, form=request.form)

        patient = Patient(
            name=request.form["name"].strip(),
            age=request.form.get("age") or None,
            gender=request.form.get("gender"),
            phone=request.form.get("phone"),
            address=request.form.get("address"),
        )
        db.session.add(patient)
        db.session.commit()

        flash("Patient added successfully!", "success")
        return redirect(url_for("patients.patient_list"))

    return render_template("patient_form.html", patient=None, form=None)


@bp.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
def edit_patient(id):
    patient = Patient.query.get_or_404(id)

    if request.method == "POST":
        errors = _validate(request.form)
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("patient_form.html", patient=patient, form=request.form)

        patient.name = request.form["name"].strip()
        patient.age = request.form.get("age") or None
        patient.gender = request.form.get("gender")
        patient.phone = request.form.get("phone")
        patient.address = request.form.get("address")
        db.session.commit()

        flash("Patient updated successfully!", "success")
        return redirect(url_for("patients.patient_list"))

    return render_template("patient_form.html", patient=patient, form=None)


@bp.route("/delete/<int:id>", methods=["POST"])
@login_required
def delete_patient(id):
    patient = Patient.query.get_or_404(id)
    db.session.delete(patient)
    db.session.commit()
    flash("Patient deleted successfully!", "warning")
    return redirect(url_for("patients.patient_list"))


@bp.route("/export.csv")
@login_required
def export_csv():
    patients = Patient.query.order_by(Patient.id).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["ID", "Name", "Age", "Gender", "Phone", "Address"])
    for p in patients:
        writer.writerow([p.id, p.name, p.age, p.gender, p.phone, p.address])

    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=patients.csv"},
    )
