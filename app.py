from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = "hospital_secret_key_2026"

DATABASE = "hospital.db"


# -----------------------------
# Database Connection
# -----------------------------
def get_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


# -----------------------------
# Initialize Database
# -----------------------------
def initialize_database():

    conn = get_connection()
    cursor = conn.cursor()

    # Patients
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS patients(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        age INTEGER,
        gender TEXT,
        phone TEXT,
        address TEXT
    )
    """)

    # Doctors
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS doctors(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        specialization TEXT,
        phone TEXT
    )
    """)

    # Appointments
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS appointments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER,
        doctor_id INTEGER,
        appointment_date TEXT,
        appointment_time TEXT,
        status TEXT DEFAULT 'Booked'
    )
    """)

    # Admissions
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS admissions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER,
        bed_number TEXT,
        ward TEXT,
        admitted_on TEXT,
        discharged INTEGER DEFAULT 0
    )
    """)

    # Billing
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bills(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER,
        consultation_fee REAL,
        medicine_fee REAL,
        room_fee REAL,
        total REAL,
        paid INTEGER DEFAULT 0
    )
    """)

    conn.commit()
    conn.close()


initialize_database()


# ======================================
# Dashboard
# ======================================

@app.route("/")
def dashboard():

    conn = get_connection()

    patient_count = conn.execute(
        "SELECT COUNT(*) FROM patients"
    ).fetchone()[0]

    doctor_count = conn.execute(
        "SELECT COUNT(*) FROM doctors"
    ).fetchone()[0]

    appointment_count = conn.execute(
        "SELECT COUNT(*) FROM appointments"
    ).fetchone()[0]

    admission_count = conn.execute(
        "SELECT COUNT(*) FROM admissions WHERE discharged=0"
    ).fetchone()[0]

    revenue = conn.execute(
        "SELECT IFNULL(SUM(total),0) FROM bills WHERE paid=1"
    ).fetchone()[0]

    conn.close()

    return render_template(
        "dashboard.html",
        patient_count=patient_count,
        doctor_count=doctor_count,
        appointment_count=appointment_count,
        admission_count=admission_count,
        revenue=revenue
    )
# ======================================
# PATIENT MANAGEMENT
# ======================================

@app.route("/patients")
def patient_list():

    conn = get_connection()

    patients = conn.execute("""
        SELECT *
        FROM patients
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "patients.html",
        patients=patients
    )


@app.route("/patients/add", methods=["GET", "POST"])
def add_patient():

    if request.method == "POST":

        name = request.form["name"]
        age = request.form["age"]
        gender = request.form["gender"]
        phone = request.form["phone"]
        address = request.form["address"]

        conn = get_connection()

        conn.execute("""
            INSERT INTO patients
            (name, age, gender, phone, address)
            VALUES (?, ?, ?, ?, ?)
        """, (name, age, gender, phone, address))

        conn.commit()
        conn.close()

        flash("Patient added successfully!", "success")

        return redirect(url_for("patient_list"))

    return render_template("add_patient.html")


@app.route("/patients/edit/<int:id>", methods=["GET", "POST"])
def edit_patient(id):

    conn = get_connection()

    patient = conn.execute("""
        SELECT *
        FROM patients
        WHERE id=?
    """, (id,)).fetchone()

    if patient is None:
        conn.close()
        flash("Patient not found!", "danger")
        return redirect(url_for("patient_list"))

    if request.method == "POST":

        conn.execute("""
            UPDATE patients
            SET
                name=?,
                age=?,
                gender=?,
                phone=?,
                address=?
            WHERE id=?
        """, (
            request.form["name"],
            request.form["age"],
            request.form["gender"],
            request.form["phone"],
            request.form["address"],
            id
        ))

        conn.commit()
        conn.close()

        flash("Patient updated successfully!", "success")

        return redirect(url_for("patient_list"))

    conn.close()

    return render_template(
        "edit_patient.html",
        patient=patient
    )


@app.route("/patients/delete/<int:id>")
def delete_patient(id):

    conn = get_connection()

    conn.execute("""
        DELETE FROM patients
        WHERE id=?
    """, (id,))

    conn.commit()
    conn.close()

    flash("Patient deleted successfully!", "warning")

    return redirect(url_for("patient_list"))


@app.route("/patients/search")
def search_patient():

    keyword = request.args.get("q", "").strip()

    conn = get_connection()

    patients = conn.execute("""
        SELECT *
        FROM patients
        WHERE
            name LIKE ?
            OR phone LIKE ?
            OR gender LIKE ?
        ORDER BY id DESC
    """, (
        f"%{keyword}%",
        f"%{keyword}%",
        f"%{keyword}%"
    )).fetchall()

    conn.close()

    return render_template(
        "patients.html",
        patients=patients
    )
# ======================================
# DOCTOR MANAGEMENT
# ======================================

@app.route("/doctors")
def doctor_list():

    conn = get_connection()

    doctors = conn.execute("""
        SELECT *
        FROM doctors
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "doctors.html",
        doctors=doctors
    )


@app.route("/doctors/add", methods=["GET", "POST"])
def add_doctor():

    if request.method == "POST":

        name = request.form["name"]
        specialization = request.form["specialization"]
        phone = request.form["phone"]

        conn = get_connection()

        conn.execute("""
            INSERT INTO doctors
            (name, specialization, phone)
            VALUES (?, ?, ?)
        """, (
            name,
            specialization,
            phone
        ))

        conn.commit()
        conn.close()

        flash("Doctor added successfully!", "success")

        return redirect(url_for("doctor_list"))

    return render_template("add_doctor.html")


@app.route("/doctors/edit/<int:id>", methods=["GET", "POST"])
def edit_doctor(id):

    conn = get_connection()

    doctor = conn.execute("""
        SELECT *
        FROM doctors
        WHERE id=?
    """, (id,)).fetchone()

    if doctor is None:
        conn.close()
        flash("Doctor not found!", "danger")
        return redirect(url_for("doctor_list"))

    if request.method == "POST":

        conn.execute("""
            UPDATE doctors
            SET
                name=?,
                specialization=?,
                phone=?
            WHERE id=?
        """, (
            request.form["name"],
            request.form["specialization"],
            request.form["phone"],
            id
        ))

        conn.commit()
        conn.close()

        flash("Doctor updated successfully!", "success")

        return redirect(url_for("doctor_list"))

    conn.close()

    return render_template(
        "edit_doctor.html",
        doctor=doctor
    )


@app.route("/doctors/delete/<int:id>")
def delete_doctor(id):

    conn = get_connection()

    conn.execute("""
        DELETE FROM doctors
        WHERE id=?
    """, (id,))

    conn.commit()
    conn.close()

    flash("Doctor deleted successfully!", "warning")

    return redirect(url_for("doctor_list"))


@app.route("/doctors/search")
def search_doctors():

    keyword = request.args.get("q", "").strip()

    conn = get_connection()

    doctors = conn.execute("""
        SELECT *
        FROM doctors
        WHERE
            name LIKE ?
            OR specialization LIKE ?
            OR phone LIKE ?
        ORDER BY id DESC
    """, (
        f"%{keyword}%",
        f"%{keyword}%",
        f"%{keyword}%"
    )).fetchall()

    conn.close()

    return render_template(
        "doctors.html",
        doctors=doctors
    )
# ======================================
# APPOINTMENT MANAGEMENT
# ======================================

@app.route("/appointments")
def appointment_list():

    conn = get_connection()

    appointments = conn.execute("""
        SELECT
            appointments.id,
            patients.name AS patient_name,
            doctors.name AS doctor_name,
            doctors.specialization,
            appointments.appointment_date,
            appointments.appointment_time,
            appointments.status
        FROM appointments
        JOIN patients
            ON appointments.patient_id = patients.id
        JOIN doctors
            ON appointments.doctor_id = doctors.id
        ORDER BY appointments.id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "appointments.html",
        appointments=appointments
    )


@app.route("/appointments/add", methods=["GET", "POST"])
def add_appointment():

    conn = get_connection()

    patient_list = conn.execute(
        "SELECT * FROM patients ORDER BY name"
    ).fetchall()

    doctor_list = conn.execute(
        "SELECT * FROM doctors ORDER BY name"
    ).fetchall()

    if request.method == "POST":

        patient_id = request.form["patient"]
        doctor_id = request.form["doctor"]
        appointment_date = request.form["date"]
        appointment_time = request.form["time"]

        # Check Doctor Availability
        existing = conn.execute("""
            SELECT id
            FROM appointments
            WHERE doctor_id=?
            AND appointment_date=?
            AND appointment_time=?
            AND status='Booked'
        """, (
            doctor_id,
            appointment_date,
            appointment_time
        )).fetchone()

        if existing:

            flash(
                "Doctor already has an appointment at this time.",
                "danger"
            )

            conn.close()

            return render_template(
                "add_appointment.html",
                patients=patient_list,
                doctors=doctor_list
            )

        conn.execute("""
            INSERT INTO appointments(
                patient_id,
                doctor_id,
                appointment_date,
                appointment_time,
                status
            )
            VALUES(?,?,?,?,?)
        """, (
            patient_id,
            doctor_id,
            appointment_date,
            appointment_time,
            "Booked"
        ))

        conn.commit()
        conn.close()

        flash(
            "Appointment booked successfully!",
            "success"
        )

        return redirect(url_for("appointment_list"))

    conn.close()

    return render_template(
        "add_appointment.html",
        patients=patient_list,
        doctors=doctor_list
    )


@app.route("/appointments/search")
def search_appointments():

    keyword = request.args.get("q", "").strip()

    conn = get_connection()

    appointments = conn.execute("""
        SELECT
            appointments.id,
            patients.name AS patient_name,
            doctors.name AS doctor_name,
            doctors.specialization,
            appointments.appointment_date,
            appointments.appointment_time,
            appointments.status
        FROM appointments
        JOIN patients
            ON appointments.patient_id = patients.id
        JOIN doctors
            ON appointments.doctor_id = doctors.id
        WHERE
            patients.name LIKE ?
            OR doctors.name LIKE ?
            OR doctors.specialization LIKE ?
            OR appointments.appointment_date LIKE ?
        ORDER BY appointments.id DESC
    """, (
        f"%{keyword}%",
        f"%{keyword}%",
        f"%{keyword}%",
        f"%{keyword}%"
    )).fetchall()

    conn.close()

    return render_template(
        "appointments.html",
        appointments=appointments
    )


@app.route("/appointments/cancel/<int:id>")
def cancel_appointment(id):

    conn = get_connection()

    conn.execute("""
        UPDATE appointments
        SET status='Cancelled'
        WHERE id=?
    """, (id,))

    conn.commit()
    conn.close()

    flash(
        "Appointment cancelled successfully!",
        "warning"
    )

    return redirect(url_for("appointment_list"))
# ======================================
# ADMISSION MANAGEMENT
# ======================================

@app.route("/admissions")
def admission_list():

    conn = get_connection()

    admissions = conn.execute("""
        SELECT
            admissions.id,
            patients.name,
            admissions.bed_number,
            admissions.ward,
            admissions.admitted_on,
            admissions.discharged
        FROM admissions
        JOIN patients
        ON admissions.patient_id = patients.id
        ORDER BY admissions.id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "admissions.html",
        admissions=admissions
    )


@app.route("/admissions/add", methods=["GET", "POST"])
def add_admission():

    conn = get_connection()

    patient_list = conn.execute(
        "SELECT * FROM patients ORDER BY name"
    ).fetchall()

    if request.method == "POST":

        conn.execute("""
            INSERT INTO admissions
            (
                patient_id,
                bed_number,
                ward,
                admitted_on
            )
            VALUES (?,?,?,?)
        """, (
            request.form["patient"],
            request.form["bed"],
            request.form["ward"],
            datetime.now().strftime("%Y-%m-%d %H:%M")
        ))

        conn.commit()
        conn.close()

        flash(
            "Patient admitted successfully!",
            "success"
        )

        return redirect(url_for("admission_list"))

    conn.close()

    return render_template(
        "add_admission.html",
        patients=patient_list
    )


@app.route("/admissions/discharge/<int:id>")
def discharge_patient(id):

    conn = get_connection()

    conn.execute("""
        UPDATE admissions
        SET discharged=1
        WHERE id=?
    """, (id,))

    conn.commit()
    conn.close()

    flash(
        "Patient discharged successfully!",
        "success"
    )

    return redirect(url_for("admission_list"))


# ======================================
# BILLING MANAGEMENT
# ======================================

@app.route("/billing")
def billing_list():

    conn = get_connection()

    bills = conn.execute("""
        SELECT
            bills.id,
            patients.name,
            consultation_fee,
            medicine_fee,
            room_fee,
            total,
            paid
        FROM bills
        JOIN patients
        ON bills.patient_id = patients.id
        ORDER BY bills.id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "billing.html",
        bills=bills
    )


@app.route("/billing/create", methods=["GET", "POST"])
def create_bill():

    conn = get_connection()

    patient_list = conn.execute(
        "SELECT * FROM patients ORDER BY name"
    ).fetchall()

    if request.method == "POST":

        consultation = float(request.form["consultation"])
        medicine = float(request.form["medicine"])
        room = float(request.form["room"])

        total = consultation + medicine + room

        conn.execute("""
            INSERT INTO bills
            (
                patient_id,
                consultation_fee,
                medicine_fee,
                room_fee,
                total
            )
            VALUES (?,?,?,?,?)
        """, (
            request.form["patient"],
            consultation,
            medicine,
            room,
            total
        ))

        conn.commit()
        conn.close()

        flash(
            "Bill created successfully!",
            "success"
        )

        return redirect(url_for("billing_list"))

    conn.close()

    return render_template(
        "create_bill.html",
        patients=patient_list
    )


@app.route("/billing/pay/<int:id>")
def pay_bill(id):

    conn = get_connection()

    conn.execute("""
        UPDATE bills
        SET paid=1
        WHERE id=?
    """, (id,))

    conn.commit()
    conn.close()

    flash(
        "Payment received successfully!",
        "success"
    )

    return redirect(url_for("billing_list"))


# ======================================
# ERROR HANDLERS
# ======================================

@app.errorhandler(404)
def page_not_found(error):
    return render_template("404.html"), 404



# ======================================
# MAIN
# ======================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
