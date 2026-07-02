import csv
import io

from flask import Blueprint, Response, flash, redirect, render_template, request, url_for
from flask_login import login_required

from extensions import db
from models import Bill, Patient

bp = Blueprint("billing", __name__, url_prefix="/billing")


@bp.route("/")
@login_required
def billing_list():
    bills = Bill.query.join(Patient).order_by(Bill.id.desc()).all()
    return render_template("billing_list.html", bills=bills)


@bp.route("/create", methods=["GET", "POST"])
@login_required
def create_bill():
    patients = Patient.query.order_by(Patient.name).all()

    if request.method == "POST":
        try:
            consultation = float(request.form.get("consultation") or 0)
            medicine = float(request.form.get("medicine") or 0)
            room = float(request.form.get("room") or 0)
        except ValueError:
            flash("Fees must be valid numbers.", "danger")
            return render_template("bill_form.html", patients=patients, form=request.form)

        total = consultation + medicine + room

        bill = Bill(
            patient_id=request.form["patient"],
            consultation_fee=consultation,
            medicine_fee=medicine,
            room_fee=room,
            total=total,
        )
        db.session.add(bill)
        db.session.commit()

        flash("Bill created successfully!", "success")
        return redirect(url_for("billing.billing_list"))

    return render_template("bill_form.html", patients=patients, form=None)


@bp.route("/pay/<int:id>", methods=["POST"])
@login_required
def pay_bill(id):
    bill = Bill.query.get_or_404(id)
    bill.paid = True
    db.session.commit()
    flash("Payment received successfully!", "success")
    return redirect(url_for("billing.billing_list"))


@bp.route("/export.csv")
@login_required
def export_csv():
    bills = Bill.query.join(Patient).order_by(Bill.id).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["ID", "Patient", "Consultation", "Medicine", "Room", "Total", "Paid"]
    )
    for b in bills:
        writer.writerow(
            [
                b.id,
                b.patient.name,
                b.consultation_fee,
                b.medicine_fee,
                b.room_fee,
                b.total,
                "Yes" if b.paid else "No",
            ]
        )

    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=billing.csv"},
    )
