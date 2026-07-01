from flask import Flask, render_template

from hms.database import initialize_database
from flask import Flask, render_template, request, redirect, url_for, flash
from hms.database import initialize_database
from hms import patients
@app.route("/patients")
def patient_list():
    all_patients = patients.get_all_patients()
    return render_template(
        "patients.html",
        patients=all_patients
    )


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
