from flask import Flask, render_template
from hms import appointments
from hms import doctors
from hms import patients
from hms.database import initialize_database
from flask import Flask, render_template, request, redirect, url_for, flash
from hms.database import initialize_database
from hms import doctors
from hms import patients
from hms import admissions
from hms import billing
@app.route("/billing/pay/<int:id>")
def pay_bill(id):

    billing.mark_bill_paid(id)

    flash("Payment Successful")

    return redirect(url_for("billing_list"))
@app.route("/admissions")
def admission_list():

    data = admissions.get_all_admissions()

    return render_template(
        "admissions.html",
        admissions=data
    )
@app.route("/billing/create", methods=["GET","POST"])
def create_bill():

    if request.method == "POST":

        billing.create_bill(

            patient_id=int(request.form["patient"]),

            consultation_fee=float(request.form["consultation"]),

            medicine_fee=float(request.form["medicine"]),

            room_fee=float(request.form["room"])

        )

        flash("Bill created successfully!")

        return redirect(url_for("billing_list"))

    return render_template(
        "create_bill.html",
        patients=patients.get_all_patients()
    )

@app.route("/admissions/add", methods=["GET", "POST"])
def add_admission():

    if request.method == "POST":

        admissions.admit_patient(
            patient_id=int(request.form["patient"]),
            bed_number=request.form["bed"],
            ward=request.form["ward"]
        )

        flash("Patient admitted successfully!")

        return redirect(url_for("admission_list"))

    return render_template(
        "add_admission.html",
        patients=patients.get_all_patients()
    )
@app.route("/billing")
def billing_list():

    bills = billing.get_all_bills()

    return render_template(
        "billing.html",
        bills=bills
    )
@app.route("/admissions/discharge/<int:id>")
def discharge_patient(id):

    admissions.discharge_patient(id)

    flash("Patient discharged successfully!")

    return redirect(url_for("admission_list"))

@app.route("/")
def dashboard():

    patient_count = len(patients.get_all_patients())

    doctor_count = len(doctors.get_all_doctors())

    appointment_count = len(
        appointments.get_all_appointments()
    )

    return render_template(
        "dashboard.html",
        patient_count=patient_count,
        doctor_count=doctor_count,
        appointment_count=appointment_count
    )
if appointments.is_doctor_available(
    doctor_id,
    appointment_date,
    appointment_time
):
    appointments.book_appointment(...)
else:
    flash("Doctor is already booked for this time.")
@app.route("/appointments/add", methods=["GET", "POST"])
def add_appointment():

    if request.method == "POST":

        appointments.book_appointment(
            patient_id=int(request.form["patient"]),
            doctor_id=int(request.form["doctor"]),
            appointment_date=request.form["date"],
            appointment_time=request.form["time"]
        )

        flash("Appointment booked successfully!")

        return redirect(url_for("appointment_list"))

    patient_list = patients.get_all_patients()
    doctor_list = doctors.get_all_doctors()

    return render_template(
        "add_appointment.html",
        patients=patient_list,
        doctors=doctor_list
    )
@app.route("/appointments/search")
def search_appointments():

    keyword = request.args.get("q", "")

    appointment_data = appointments.search_appointments(keyword)

    return render_template(
        "appointments.html",
        appointments=appointment_data
    )
@app.route("/appointments/cancel/<int:id>")
def cancel_appointment(id):

    appointments.cancel_appointment(id)

    flash("Appointment cancelled.")

    return redirect(url_for("appointment_list"))
@app.route("/appointments")
def appointment_list():

    appointment_data = appointments.get_all_appointments()

    return render_template(
        "appointments.html",
        appointments=appointment_data
    )
@app.route("/patients")
def patient_list():
    all_patients = patients.get_all_patients()
    return render_template(
        "patients.html",
        patients=all_patients
    )
@app.route("/doctors/delete/<int:id>")
def delete_doctor(id):

    doctors.delete_doctor(id)

    flash("Doctor deleted successfully!")

    return redirect(url_for("doctor_list"))
@app.route("/")
def dashboard():

    patient_count = len(patients.get_all_patients())
    doctor_count = len(doctors.get_all_doctors())

    return render_template(
        "dashboard.html",
        patient_count=patient_count,
        doctor_count=doctor_count
    )
@app.route("/")
def dashboard():

    patient_count = len(patients.get_all_patients())

    return render_template(
        "dashboard.html",
        patient_count=patient_count
    )
@app.route("/doctors/edit/<int:id>", methods=["GET", "POST"])
def edit_doctor(id):

    doctor = doctors.get_doctor(id)

    if request.method == "POST":

        doctors.update_doctor(
            id,
            request.form["name"],
            request.form["specialization"],
            request.form["phone"]
        )

        flash("Doctor updated successfully!")

        return redirect(url_for("doctor_list"))

    return render_template(
        "edit_doctor.html",
        doctor=doctor
    )
@app.route("/doctors")
def doctor_list():

    all_doctors = doctors.get_all_doctors()

    return render_template(
        "doctors.html",
        doctors=all_doctors
    )
@app.route("/doctors/search")
def search_doctors():

    keyword = request.args.get("q", "")

    results = doctors.search_doctors(keyword)

    return render_template(
        "doctors.html",
        doctors=results
    )
@app.route("/doctors/add", methods=["GET", "POST"])
def add_doctor():

    if request.method == "POST":

        doctors.add_doctor(
            name=request.form["name"],
            specialization=request.form["specialization"],
            phone=request.form["phone"]
        )

        flash("Doctor added successfully!")

        return redirect(url_for("doctor_list"))

    return render_template("add_doctor.html")
@app.route("/patients/add", methods=["GET", "POST"])
def add_patient():

    if request.method == "POST":

        patients.add_patient(
            name=request.form["name"],
            age=int(request.form["age"]),
            gender=request.form["gender"],
            phone=request.form["phone"],
            address=request.form["address"]
        )

        flash("Patient added successfully!")

        return redirect(url_for("patient_list"))

    return render_template("add_patient.html")
app = Flask(__name__)

# Initialize the database once when the app starts
initialize_database()


@app.route("/")
def dashboard():
    return render_template("dashboard.html")


if __name__ == "__main__":
    app.run(debug=True)
