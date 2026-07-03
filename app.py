from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify
import sqlite3
import os
import io
from datetime import datetime

import qrcode

try:
    from twilio.rest import Client as TwilioClient
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False

app = Flask(__name__)
app.secret_key = "hospital_secret_key_2026"

DATABASE = "hospital.db"

# Default time (in minutes) a doctor takes per patient, used to estimate
# how long someone still waiting in the queue can expect to wait.
DEFAULT_CONSULT_MINUTES = 15


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
        phone TEXT,
        available INTEGER DEFAULT 1,
        avg_consult_minutes INTEGER DEFAULT 15
    )
    """)

    # Live Queue
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS queue(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token_number INTEGER NOT NULL,
        doctor_id INTEGER NOT NULL,
        patient_id INTEGER,
        patient_name TEXT NOT NULL,
        patient_phone TEXT,
        status TEXT DEFAULT 'Waiting',
        queue_date TEXT NOT NULL,
        created_at TEXT,
        called_at TEXT,
        completed_at TEXT
    )
    """)

    # SMS Notification Log
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notifications(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        queue_id INTEGER,
        phone TEXT,
        message TEXT,
        status TEXT,
        created_at TEXT
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


# -----------------------------
# Migrate Older Databases
# -----------------------------
def migrate_schema():
    """Add new columns to a pre-existing doctors table (deployed DBs that
    were created before availability / queue features existed)."""

    conn = get_connection()
    cursor = conn.cursor()

    existing_columns = [
        row["name"] for row in cursor.execute("PRAGMA table_info(doctors)").fetchall()
    ]

    if "available" not in existing_columns:
        cursor.execute("ALTER TABLE doctors ADD COLUMN available INTEGER DEFAULT 1")

    if "avg_consult_minutes" not in existing_columns:
        cursor.execute(
            f"ALTER TABLE doctors ADD COLUMN avg_consult_minutes INTEGER DEFAULT {DEFAULT_CONSULT_MINUTES}"
        )

    conn.commit()
    conn.close()


migrate_schema()


# -----------------------------
# SMS Notifications
# -----------------------------
def send_sms(phone, message, queue_id=None):
    """Send an SMS via Twilio if credentials are configured in the
    environment, otherwise log the message so it can still be reviewed
    on the Notifications page. This means the feature works out of the
    box in demo/dev mode, and starts sending real texts the moment
    TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER are set."""

    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = os.environ.get("TWILIO_FROM_NUMBER")

    status = "simulated"

    if TWILIO_AVAILABLE and account_sid and auth_token and from_number and phone:
        try:
            client = TwilioClient(account_sid, auth_token)
            client.messages.create(body=message, from_=from_number, to=phone)
            status = "sent"
        except Exception as error:
            status = f"failed: {error}"

    conn = get_connection()
    conn.execute("""
        INSERT INTO notifications
        (queue_id, phone, message, status, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (
        queue_id,
        phone,
        message,
        status,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))
    conn.commit()
    conn.close()

    return status


# -----------------------------
# Queue Helpers
# -----------------------------
def next_token_number(conn, doctor_id, queue_date):
    """Tokens restart at 1 each day, per doctor - the usual pattern for a
    hospital's physical/digital token boards."""

    row = conn.execute("""
        SELECT COALESCE(MAX(token_number), 0) AS max_token
        FROM queue
        WHERE doctor_id = ? AND queue_date = ?
    """, (doctor_id, queue_date)).fetchone()

    return row["max_token"] + 1


def queue_entry_eta(conn, entry):
    """Estimated minutes until this queue entry is called: number of
    people still waiting ahead of it, multiplied by that doctor's average
    consultation time."""

    if entry["status"] != "Waiting":
        return 0

    ahead = conn.execute("""
        SELECT COUNT(*) AS c
        FROM queue
        WHERE doctor_id = ?
          AND queue_date = ?
          AND status = 'Waiting'
          AND token_number < ?
    """, (entry["doctor_id"], entry["queue_date"], entry["token_number"])).fetchone()["c"]

    doctor = conn.execute(
        "SELECT avg_consult_minutes FROM doctors WHERE id=?", (entry["doctor_id"],)
    ).fetchone()

    consult_minutes = (doctor["avg_consult_minutes"] if doctor and doctor["avg_consult_minutes"] else DEFAULT_CONSULT_MINUTES)

    return ahead * consult_minutes


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

    today = datetime.now().strftime("%Y-%m-%d")

    waiting_count = conn.execute(
        "SELECT COUNT(*) FROM queue WHERE queue_date=? AND status='Waiting'",
        (today,)
    ).fetchone()[0]

    doctors_available = conn.execute(
        "SELECT COUNT(*) FROM doctors WHERE available=1"
    ).fetchone()[0]

    conn.close()

    return render_template(
        "dashboard.html",
        patient_count=patient_count,
        doctor_count=doctor_count,
        appointment_count=appointment_count,
        admission_count=admission_count,
        revenue=revenue,
        waiting_count=waiting_count,
        doctors_available=doctors_available
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
        avg_consult_minutes = request.form.get("avg_consult_minutes") or DEFAULT_CONSULT_MINUTES

        conn = get_connection()

        conn.execute("""
            INSERT INTO doctors
            (name, specialization, phone, available, avg_consult_minutes)
            VALUES (?, ?, ?, 1, ?)
        """, (
            name,
            specialization,
            phone,
            avg_consult_minutes
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
                phone=?,
                avg_consult_minutes=?
            WHERE id=?
        """, (
            request.form["name"],
            request.form["specialization"],
            request.form["phone"],
            request.form.get("avg_consult_minutes") or DEFAULT_CONSULT_MINUTES,
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


@app.route("/doctors/toggle/<int:id>")
def toggle_doctor_availability(id):

    conn = get_connection()

    doctor = conn.execute(
        "SELECT * FROM doctors WHERE id=?", (id,)
    ).fetchone()

    if doctor is None:
        conn.close()
        flash("Doctor not found!", "danger")
        return redirect(url_for("doctor_list"))

    new_value = 0 if doctor["available"] else 1

    conn.execute(
        "UPDATE doctors SET available=? WHERE id=?", (new_value, id)
    )

    conn.commit()
    conn.close()

    flash(
        f"Dr. {doctor['name']} marked as {'Available' if new_value else 'Unavailable'}.",
        "success"
    )

    return redirect(url_for("doctor_list"))


# ======================================
# LIVE QUEUE MANAGEMENT
# ======================================

@app.route("/queue")
def queue_board():

    conn = get_connection()

    today = datetime.now().strftime("%Y-%m-%d")

    doctors = conn.execute(
        "SELECT * FROM doctors ORDER BY name"
    ).fetchall()

    rows = conn.execute("""
        SELECT queue.*, doctors.name AS doctor_name, doctors.specialization
        FROM queue
        JOIN doctors ON queue.doctor_id = doctors.id
        WHERE queue.queue_date = ?
          AND queue.status IN ('Waiting', 'In Consultation')
        ORDER BY queue.doctor_id, queue.token_number
    """, (today,)).fetchall()

    entries = []
    for row in rows:
        entries.append({
            **dict(row),
            "eta_minutes": queue_entry_eta(conn, row)
        })

    conn.close()

    return render_template(
        "queue.html",
        entries=entries,
        doctors=doctors,
        today=today
    )


@app.route("/queue/data")
def queue_data():
    """JSON feed used by the queue board and token status pages to
    refresh themselves live, without a full page reload."""

    conn = get_connection()

    today = datetime.now().strftime("%Y-%m-%d")

    rows = conn.execute("""
        SELECT queue.*, doctors.name AS doctor_name, doctors.specialization
        FROM queue
        JOIN doctors ON queue.doctor_id = doctors.id
        WHERE queue.queue_date = ?
          AND queue.status IN ('Waiting', 'In Consultation')
        ORDER BY queue.doctor_id, queue.token_number
    """, (today,)).fetchall()

    entries = []
    for row in rows:
        entries.append({
            "id": row["id"],
            "token_number": row["token_number"],
            "doctor_id": row["doctor_id"],
            "doctor_name": row["doctor_name"],
            "patient_name": row["patient_name"],
            "status": row["status"],
            "eta_minutes": queue_entry_eta(conn, row)
        })

    conn.close()

    return jsonify(entries=entries)


@app.route("/queue/add", methods=["GET", "POST"])
def add_to_queue():

    conn = get_connection()

    patient_list = conn.execute(
        "SELECT * FROM patients ORDER BY name"
    ).fetchall()

    available_doctors = conn.execute(
        "SELECT * FROM doctors WHERE available=1 ORDER BY name"
    ).fetchall()

    if request.method == "POST":

        doctor_id = request.form["doctor"]
        patient_id = request.form.get("patient") or None

        if patient_id:
            patient = conn.execute(
                "SELECT * FROM patients WHERE id=?", (patient_id,)
            ).fetchone()
            patient_name = patient["name"]
            patient_phone = patient["phone"]
        else:
            patient_name = request.form.get("walkin_name", "").strip()
            patient_phone = request.form.get("walkin_phone", "").strip()

        if not patient_name:
            flash("Please select a patient or enter a walk-in name.", "danger")
            conn.close()
            return render_template(
                "add_to_queue.html",
                patients=patient_list,
                doctors=available_doctors
            )

        today = datetime.now().strftime("%Y-%m-%d")
        token_number = next_token_number(conn, doctor_id, today)

        cursor = conn.execute("""
            INSERT INTO queue
            (token_number, doctor_id, patient_id, patient_name, patient_phone,
             status, queue_date, created_at)
            VALUES (?, ?, ?, ?, ?, 'Waiting', ?, ?)
        """, (
            token_number,
            doctor_id,
            patient_id,
            patient_name,
            patient_phone,
            today,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

        queue_id = cursor.lastrowid
        conn.commit()

        new_entry = conn.execute(
            "SELECT * FROM queue WHERE id=?", (queue_id,)
        ).fetchone()
        eta = queue_entry_eta(conn, new_entry)

        doctor = conn.execute(
            "SELECT * FROM doctors WHERE id=?", (doctor_id,)
        ).fetchone()

        conn.close()

        status_link = url_for("token_status", id=queue_id, _external=True)

        send_sms(
            patient_phone,
            f"Hi {patient_name}, your token #{token_number} for Dr. {doctor['name']} "
            f"has been generated. Estimated wait: {eta} min. Track live: {status_link}",
            queue_id=queue_id
        )

        flash(f"Added to queue! Token #{token_number} generated.", "success")

        return redirect(url_for("token_status", id=queue_id))

    conn.close()

    return render_template(
        "add_to_queue.html",
        patients=patient_list,
        doctors=available_doctors
    )


@app.route("/queue/token/<int:id>")
def token_status(id):

    conn = get_connection()

    entry = conn.execute("""
        SELECT queue.*, doctors.name AS doctor_name, doctors.specialization
        FROM queue
        JOIN doctors ON queue.doctor_id = doctors.id
        WHERE queue.id = ?
    """, (id,)).fetchone()

    if entry is None:
        conn.close()
        flash("Queue token not found!", "danger")
        return redirect(url_for("queue_board"))

    eta = queue_entry_eta(conn, entry)

    conn.close()

    return render_template(
        "token_status.html",
        entry=entry,
        eta_minutes=eta
    )


@app.route("/queue/status/<int:id>")
def token_status_data(id):
    """JSON feed for the public token page to poll live."""

    conn = get_connection()

    entry = conn.execute(
        "SELECT * FROM queue WHERE id=?", (id,)
    ).fetchone()

    if entry is None:
        conn.close()
        return jsonify(error="not_found"), 404

    eta = queue_entry_eta(conn, entry)

    conn.close()

    return jsonify(
        status=entry["status"],
        token_number=entry["token_number"],
        eta_minutes=eta
    )


@app.route("/queue/qr/<int:id>.png")
def queue_qr(id):
    """Generates a QR code on the fly (nothing saved to disk) that
    encodes a link to this token's live public status page."""

    link = url_for("token_status", id=id, _external=True)

    img = qrcode.make(link)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return send_file(buffer, mimetype="image/png")


@app.route("/queue/call_next/<int:doctor_id>")
def call_next(doctor_id):

    conn = get_connection()

    today = datetime.now().strftime("%Y-%m-%d")

    next_entry = conn.execute("""
        SELECT * FROM queue
        WHERE doctor_id=? AND queue_date=? AND status='Waiting'
        ORDER BY token_number
        LIMIT 1
    """, (doctor_id, today)).fetchone()

    if next_entry is None:
        conn.close()
        flash("No one is waiting in this doctor's queue.", "warning")
        return redirect(url_for("queue_board"))

    conn.execute("""
        UPDATE queue
        SET status='In Consultation', called_at=?
        WHERE id=?
    """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), next_entry["id"]))

    conn.commit()

    doctor = conn.execute(
        "SELECT * FROM doctors WHERE id=?", (doctor_id,)
    ).fetchone()

    conn.close()

    send_sms(
        next_entry["patient_phone"],
        f"Token #{next_entry['token_number']}: please proceed to Dr. {doctor['name']}'s room now.",
        queue_id=next_entry["id"]
    )

    flash(f"Called token #{next_entry['token_number']} ({next_entry['patient_name']}).", "success")

    return redirect(url_for("queue_board"))


@app.route("/queue/complete/<int:id>")
def complete_queue_entry(id):

    conn = get_connection()

    conn.execute("""
        UPDATE queue
        SET status='Completed', completed_at=?
        WHERE id=?
    """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), id))

    conn.commit()
    conn.close()

    flash("Consultation marked as completed.", "success")

    return redirect(url_for("queue_board"))


@app.route("/queue/cancel/<int:id>")
def cancel_queue_entry(id):

    conn = get_connection()

    conn.execute("""
        UPDATE queue
        SET status='Cancelled'
        WHERE id=?
    """, (id,))

    conn.commit()
    conn.close()

    flash("Queue token cancelled.", "warning")

    return redirect(url_for("queue_board"))


@app.route("/notifications")
def notifications_log():

    conn = get_connection()

    logs = conn.execute("""
        SELECT notifications.*, queue.token_number, queue.patient_name
        FROM notifications
        LEFT JOIN queue ON notifications.queue_id = queue.id
        ORDER BY notifications.id DESC
        LIMIT 100
    """).fetchall()

    conn.close()

    return render_template("notifications.html", logs=logs)


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
