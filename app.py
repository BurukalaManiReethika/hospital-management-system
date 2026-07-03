from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify, session, g
import sqlite3
import os
import io
from datetime import datetime, timedelta
from functools import wraps

import qrcode
from werkzeug.security import generate_password_hash, check_password_hash

try:
    from twilio.rest import Client as TwilioClient
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "hospital_secret_key_2026")

DATABASE = "hospital.db"

# Default admin account, seeded on first run if the users table is empty.
# Override via environment variables in production.
DEFAULT_ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

# Roles, in order of privilege. "admin" is always allowed everywhere.
ROLES = ["admin", "doctor", "receptionist"]

# Default time (in minutes) a doctor takes per patient, used to estimate
# how long someone still waiting in the queue can expect to wait.
DEFAULT_CONSULT_MINUTES = 15


# -----------------------------
# Database Connection
# -----------------------------
def get_connection():
    conn = sqlite3.connect(DATABASE, timeout=10)
    conn.row_factory = sqlite3.Row
    # The live queue does frequent small writes (call next, complete,
    # SMS log inserts) alongside reads from the queue board polling
    # every few seconds. WAL mode lets reads proceed while a write is
    # in progress instead of raising "database is locked", and the
    # busy_timeout makes concurrent writers wait briefly instead of
    # failing immediately.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
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

    # Users (login accounts)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'receptionist',
        created_at TEXT
    )
    """)

    # Medical Records / Prescriptions
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS medical_records(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL,
        doctor_id INTEGER,
        visit_date TEXT NOT NULL,
        diagnosis TEXT,
        prescription TEXT,
        notes TEXT,
        created_by TEXT,
        created_at TEXT
    )
    """)

    conn.commit()
    conn.close()


initialize_database()


def seed_default_admin():
    """Create a default admin account the first time the app runs, so
    there's always a way in. Change ADMIN_USERNAME / ADMIN_PASSWORD in
    production instead of relying on the default."""

    conn = get_connection()

    existing = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    if existing == 0:
        conn.execute("""
            INSERT INTO users (username, password_hash, role, created_at)
            VALUES (?, ?, 'admin', ?)
        """, (
            DEFAULT_ADMIN_USERNAME,
            generate_password_hash(DEFAULT_ADMIN_PASSWORD),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()

    conn.close()


seed_default_admin()


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
        try:
            cursor.execute("ALTER TABLE doctors ADD COLUMN available INTEGER DEFAULT 1")
        except sqlite3.OperationalError:
            pass  # another worker process already added it

    if "avg_consult_minutes" not in existing_columns:
        try:
            cursor.execute(
                f"ALTER TABLE doctors ADD COLUMN avg_consult_minutes INTEGER DEFAULT {DEFAULT_CONSULT_MINUTES}"
            )
        except sqlite3.OperationalError:
            pass  # another worker process already added it

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
# AUTHENTICATION
# ======================================

# Endpoints reachable without logging in. Token status/QR/live-status are
# meant to be shared with patients directly (e.g. via SMS), so they stay
# public even though everything else requires a login.
PUBLIC_ENDPOINTS = {
    "login",
    "static",
    "token_status",
    "token_status_data",
    "queue_qr",
}


@app.before_request
def require_login():
    if request.endpoint in PUBLIC_ENDPOINTS or request.endpoint is None:
        return None

    if "user_id" not in session:
        flash("Please log in to continue.", "warning")
        return redirect(url_for("login", next=request.path))

    g.user = {
        "id": session["user_id"],
        "username": session["username"],
        "role": session["role"],
    }

    return None


@app.context_processor
def inject_current_user():
    return {"current_user": getattr(g, "user", None)}


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def roles_required(*allowed_roles):
    """Restrict a view to users whose role is in allowed_roles. Admins
    can always access everything regardless of the roles listed."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            role = session.get("role")
            if role != "admin" and role not in allowed_roles:
                flash("You don't have permission to access that page.", "danger")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)
        return wrapped
    return decorator


@app.route("/login", methods=["GET", "POST"])
def login():

    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE username=?", (username,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]

            flash(f"Welcome back, {user['username']}!", "success")

            next_page = request.args.get("next")
            return redirect(next_page or url_for("dashboard"))

        flash("Invalid username or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# ======================================
# USER MANAGEMENT (admin only)
# ======================================

@app.route("/users")
@login_required
@roles_required("admin")
def user_list():

    conn = get_connection()
    users = conn.execute(
        "SELECT id, username, role, created_at FROM users ORDER BY id"
    ).fetchall()
    conn.close()

    return render_template("users.html", users=users, roles=ROLES)


@app.route("/users/add", methods=["GET", "POST"])
@login_required
@roles_required("admin")
def add_user():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "receptionist")

        if role not in ROLES:
            role = "receptionist"

        if not username or not password:
            flash("Username and password are required.", "danger")
            return render_template("add_user.html", roles=ROLES)

        conn = get_connection()

        existing = conn.execute(
            "SELECT id FROM users WHERE username=?", (username,)
        ).fetchone()

        if existing:
            conn.close()
            flash("That username is already taken.", "danger")
            return render_template("add_user.html", roles=ROLES)

        conn.execute("""
            INSERT INTO users (username, password_hash, role, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            username,
            generate_password_hash(password),
            role,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()
        conn.close()

        flash(f"User '{username}' created successfully!", "success")
        return redirect(url_for("user_list"))

    return render_template("add_user.html", roles=ROLES)


@app.route("/users/delete/<int:id>")
@login_required
@roles_required("admin")
def delete_user(id):

    if id == session.get("user_id"):
        flash("You can't delete your own account while logged in.", "danger")
        return redirect(url_for("user_list"))

    conn = get_connection()
    conn.execute("DELETE FROM users WHERE id=?", (id,))
    conn.commit()
    conn.close()

    flash("User deleted.", "warning")
    return redirect(url_for("user_list"))


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


@app.route("/api/dashboard/stats")
def dashboard_stats():
    """JSON feed powering the dashboard charts."""

    conn = get_connection()

    # Revenue for each of the last 7 days. Bills don't currently have a
    # created_at column with a reliable date to group by other than id
    # order, so we approximate "recent" bills by id if no date exists;
    # here we use the bills table's rowid creation order as a stand-in
    # only when a date isn't available. Since bills has no date column,
    # we report totals by payment status instead, which is always accurate.
    revenue_by_status = conn.execute("""
        SELECT
            CASE WHEN paid=1 THEN 'Paid' ELSE 'Unpaid' END AS label,
            IFNULL(SUM(total), 0) AS amount
        FROM bills
        GROUP BY paid
    """).fetchall()

    appointment_status = conn.execute("""
        SELECT status, COUNT(*) AS c
        FROM appointments
        GROUP BY status
    """).fetchall()

    queue_status = conn.execute("""
        SELECT status, COUNT(*) AS c
        FROM queue
        WHERE queue_date = ?
        GROUP BY status
    """, (datetime.now().strftime("%Y-%m-%d"),)).fetchall()

    admissions_status = conn.execute("""
        SELECT
            CASE WHEN discharged=1 THEN 'Discharged' ELSE 'Currently Admitted' END AS label,
            COUNT(*) AS c
        FROM admissions
        GROUP BY discharged
    """).fetchall()

    doctors_by_specialization = conn.execute("""
        SELECT IFNULL(specialization, 'General'), COUNT(*) AS c
        FROM doctors
        GROUP BY specialization
    """).fetchall()

    conn.close()

    return jsonify(
        revenue_by_status=[{"label": r["label"], "amount": r["amount"]} for r in revenue_by_status],
        appointment_status=[{"label": r["status"], "count": r["c"]} for r in appointment_status],
        queue_status=[{"label": r["status"], "count": r["c"]} for r in queue_status],
        admissions_status=[{"label": r["label"], "count": r["c"]} for r in admissions_status],
        doctors_by_specialization=[{"label": r[0], "count": r[1]} for r in doctors_by_specialization],
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
@roles_required("receptionist")
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
@app.route("/patients/<int:id>")
def patient_detail(id):

    conn = get_connection()

    patient = conn.execute(
        "SELECT * FROM patients WHERE id=?", (id,)
    ).fetchone()

    if patient is None:
        conn.close()
        flash("Patient not found!", "danger")
        return redirect(url_for("patient_list"))

    records = conn.execute("""
        SELECT medical_records.*, doctors.name AS doctor_name
        FROM medical_records
        LEFT JOIN doctors ON medical_records.doctor_id = doctors.id
        WHERE patient_id=?
        ORDER BY visit_date DESC, id DESC
    """, (id,)).fetchall()

    appointments = conn.execute("""
        SELECT appointments.*, doctors.name AS doctor_name
        FROM appointments
        JOIN doctors ON appointments.doctor_id = doctors.id
        WHERE patient_id=?
        ORDER BY appointment_date DESC
    """, (id,)).fetchall()

    bills = conn.execute("""
        SELECT * FROM bills WHERE patient_id=? ORDER BY id DESC
    """, (id,)).fetchall()

    conn.close()

    return render_template(
        "patient_detail.html",
        patient=patient,
        records=records,
        appointments=appointments,
        bills=bills
    )


@app.route("/patients/<int:id>/records/add", methods=["GET", "POST"])
@roles_required("doctor")
def add_medical_record(id):

    conn = get_connection()

    patient = conn.execute(
        "SELECT * FROM patients WHERE id=?", (id,)
    ).fetchone()

    if patient is None:
        conn.close()
        flash("Patient not found!", "danger")
        return redirect(url_for("patient_list"))

    doctors = conn.execute(
        "SELECT * FROM doctors ORDER BY name"
    ).fetchall()

    if request.method == "POST":

        conn.execute("""
            INSERT INTO medical_records
            (patient_id, doctor_id, visit_date, diagnosis, prescription, notes, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            id,
            request.form.get("doctor") or None,
            request.form.get("visit_date") or datetime.now().strftime("%Y-%m-%d"),
            request.form.get("diagnosis", "").strip(),
            request.form.get("prescription", "").strip(),
            request.form.get("notes", "").strip(),
            session.get("username"),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

        conn.commit()
        conn.close()

        flash("Medical record added successfully!", "success")
        return redirect(url_for("patient_detail", id=id))

    conn.close()

    return render_template(
        "add_medical_record.html",
        patient=patient,
        doctors=doctors,
        today=datetime.now().strftime("%Y-%m-%d")
    )


@app.route("/patients/<int:patient_id>/records/delete/<int:record_id>")
@roles_required("doctor")
def delete_medical_record(patient_id, record_id):

    conn = get_connection()
    conn.execute("DELETE FROM medical_records WHERE id=?", (record_id,))
    conn.commit()
    conn.close()

    flash("Medical record removed.", "warning")
    return redirect(url_for("patient_detail", id=patient_id))


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
@roles_required("admin")
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
@roles_required("admin")
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
@roles_required("admin")
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
@roles_required("receptionist")
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
@roles_required("receptionist")
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


@app.route("/billing/<int:id>/invoice.pdf")
def bill_invoice_pdf(id):

    conn = get_connection()

    bill = conn.execute("""
        SELECT bills.*, patients.name, patients.phone, patients.address
        FROM bills
        JOIN patients ON bills.patient_id = patients.id
        WHERE bills.id=?
    """, (id,)).fetchone()

    conn.close()

    if bill is None:
        flash("Bill not found!", "danger")
        return redirect(url_for("billing_list"))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=25 * mm, bottomMargin=20 * mm)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("Hospital Management System", styles["Title"]))
    elements.append(Paragraph(f"Invoice #{bill['id']}", styles["Heading2"]))
    elements.append(Spacer(1, 10))

    elements.append(Paragraph(f"<b>Patient:</b> {bill['name']}", styles["Normal"]))
    if bill["phone"]:
        elements.append(Paragraph(f"<b>Phone:</b> {bill['phone']}", styles["Normal"]))
    if bill["address"]:
        elements.append(Paragraph(f"<b>Address:</b> {bill['address']}", styles["Normal"]))
    elements.append(Paragraph(
        f"<b>Date generated:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles["Normal"]
    ))
    elements.append(Spacer(1, 16))

    data = [
        ["Description", "Amount (Rs.)"],
        ["Consultation Fee", f"{bill['consultation_fee']:.2f}"],
        ["Medicine Fee", f"{bill['medicine_fee']:.2f}"],
        ["Room Fee", f"{bill['room_fee']:.2f}"],
        ["Total", f"{bill['total']:.2f}"],
        ["Payment Status", "PAID" if bill["paid"] else "UNPAID"],
    ]

    table = Table(data, colWidths=[120 * mm, 50 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f6fed")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -2), (-1, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
    ]))

    elements.append(table)
    doc.build(elements)

    buffer.seek(0)

    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"invoice_{bill['id']}.pdf"
    )


@app.route("/billing/report.pdf")
@roles_required("receptionist")
def billing_report_pdf():

    conn = get_connection()

    bills = conn.execute("""
        SELECT bills.id, patients.name, total, paid
        FROM bills
        JOIN patients ON bills.patient_id = patients.id
        ORDER BY bills.id
    """).fetchall()

    total_revenue = conn.execute(
        "SELECT IFNULL(SUM(total),0) FROM bills WHERE paid=1"
    ).fetchone()[0]

    total_outstanding = conn.execute(
        "SELECT IFNULL(SUM(total),0) FROM bills WHERE paid=0"
    ).fetchone()[0]

    conn.close()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=25 * mm, bottomMargin=20 * mm)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("Hospital Management System", styles["Title"]))
    elements.append(Paragraph("Billing Report", styles["Heading2"]))
    elements.append(Paragraph(
        f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles["Normal"]
    ))
    elements.append(Spacer(1, 14))

    data = [["Bill #", "Patient", "Total (Rs.)", "Status"]]
    for b in bills:
        data.append([b["id"], b["name"], f"{b['total']:.2f}", "Paid" if b["paid"] else "Unpaid"])

    table = Table(data, colWidths=[25 * mm, 75 * mm, 35 * mm, 30 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f6fed")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))

    elements.append(table)
    elements.append(Spacer(1, 16))
    elements.append(Paragraph(f"<b>Total Revenue Collected:</b> Rs. {total_revenue:.2f}", styles["Normal"]))
    elements.append(Paragraph(f"<b>Total Outstanding:</b> Rs. {total_outstanding:.2f}", styles["Normal"]))

    doc.build(elements)
    buffer.seek(0)

    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="billing_report.pdf"
    )


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
