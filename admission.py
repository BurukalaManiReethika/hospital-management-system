from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from extensions import db
from models import Admission, Patient

bp = Blueprint("admissions", __name__, url_prefix="/admissions")


@bp.route("/")
@login_required
def admission_list():
    admissions = Admission.query.join(Patient).order_by(Admission.id.desc()).all()
    return render_template("admissions_list.html", admissions=admissions)


@bp.route("/add", methods=["GET", "POST"])
@login_required
def add_admission():
    patients = Patient.query.order_by(Patient.name).all()

    if request.method == "POST":
        bed_number = request.form.get("bed", "").strip()

        # Prevent double-booking the same bed while it's occupied
        conflict = Admission.query.filter_by(bed_number=bed_number, discharged=False).first()
        if conflict:
            flash(f"Bed {bed_number} is already occupied.", "danger")
            return render_template("admission_form.html", patients=patients, form=request.form)

        admission = Admission(
            patient_id=request.form["patient"],
            bed_number=bed_number,
            ward=request.form.get("ward"),
            admitted_on=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
        db.session.add(admission)
        db.session.commit()

        flash("Patient admitted successfully!", "success")
        return redirect(url_for("admissions.admission_list"))

    return render_template("admission_form.html", patients=patients, form=None)


@bp.route("/discharge/<int:id>", methods=["POST"])
@login_required
def discharge_patient(id):
    admission = Admission.query.get_or_404(id)
    admission.discharged = True
    admission.discharged_on = datetime.now().strftime("%Y-%m-%d %H:%M")
    db.session.commit()

    flash("Patient discharged successfully!", "success")
    return redirect(url_for("admissions.admission_list"))
