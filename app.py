from flask import Flask, render_template

from hms.database import initialize_database
from flask import Flask, render_template, request, redirect, url_for, flash
from hms.database import initialize_database
from hms import doctors
from hms import patients
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
