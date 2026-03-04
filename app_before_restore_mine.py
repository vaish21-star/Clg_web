from flask import Flask, render_template, request, redirect, session, send_file, url_for
import os
import hashlib
import random
import csv
import io
import time
import smtplib
import zipfile
import re
import secrets
from email.message import EmailMessage
from datetime import date, datetime
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

from db import get_db
from pdf_utils import generate_admission_letter, generate_fee_receipt

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret_key")

AUTH_RATE_LIMIT_WINDOW_SECONDS = 300
AUTH_RATE_LIMIT_MAX_ATTEMPTS = 5
_AUTH_FAILED_ATTEMPTS = {}


def load_local_env(env_path=".env"):
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and not os.environ.get(key):
                    os.environ[key] = value
    except Exception:
        # If .env cannot be read, continue with OS environment variables.
        pass


def hash_password(password):
    return generate_password_hash(password)


def verify_password(stored_hash, raw_password):
    if not stored_hash:
        return False
    try:
        if check_password_hash(stored_hash, raw_password):
            return True
    except Exception:
        pass
    legacy_sha256 = hashlib.sha256(raw_password.encode()).hexdigest()
    return stored_hash == legacy_sha256


def client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _rate_limit_bucket(action, identity):
    return f"{action}:{identity}"


def is_auth_rate_limited(action, identity):
    now = time.time()
    key = _rate_limit_bucket(action, identity)
    attempts = _AUTH_FAILED_ATTEMPTS.get(key, [])
    attempts = [ts for ts in attempts if now - ts <= AUTH_RATE_LIMIT_WINDOW_SECONDS]
    _AUTH_FAILED_ATTEMPTS[key] = attempts
    return len(attempts) >= AUTH_RATE_LIMIT_MAX_ATTEMPTS


def record_auth_failure(action, identity):
    now = time.time()
    key = _rate_limit_bucket(action, identity)
    attempts = _AUTH_FAILED_ATTEMPTS.get(key, [])
    attempts = [ts for ts in attempts if now - ts <= AUTH_RATE_LIMIT_WINDOW_SECONDS]
    attempts.append(now)
    _AUTH_FAILED_ATTEMPTS[key] = attempts


def clear_auth_failures(action, identity):
    key = _rate_limit_bucket(action, identity)
    _AUTH_FAILED_ATTEMPTS.pop(key, None)


def ensure_csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def validate_csrf():
    expected = session.get("_csrf_token")
    provided = request.form.get("_csrf_token", "")
    if not expected or not provided:
        return False
    return secrets.compare_digest(str(expected), str(provided))


@app.context_processor
def inject_csrf_token():
    return {"csrf_token": ensure_csrf_token}


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_local_env(os.path.join(BASE_DIR, ".env"))


UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs("static/pdfs", exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


def ensure_employees_table():
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS employee_details (
            id INT AUTO_INCREMENT PRIMARY KEY,
            employee_name VARCHAR(100) NOT NULL,
            department VARCHAR(100) NOT NULL,
            designation VARCHAR(100) NOT NULL,
            mobile_no VARCHAR(15) NOT NULL,
            employee_type VARCHAR(30) NOT NULL DEFAULT 'TEACHING',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.commit()
    cur.close()
    db.close()


def ensure_students_rejection_reason_column():
    db = get_db()
    cur = db.cursor()
    try:
        # Safer than querying information_schema in restricted DB setups.
        cur.execute("SHOW COLUMNS FROM students LIKE 'rejection_reason'")
        row = cur.fetchone()
        if not row:
            cur.execute("ALTER TABLE students ADD COLUMN rejection_reason TEXT NULL")
            db.commit()
    except Exception:
        # If column already exists/race condition, continue.
        db.rollback()
    finally:
        cur.close()
        db.close()


def ensure_students_status_supports_rejected():
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("SHOW COLUMNS FROM students LIKE 'status'")
        row = cur.fetchone()
        if not row:
            return

        # row format: Field, Type, Null, Key, Default, Extra
        col_type = str(row[1]).lower() if len(row) > 1 else ""
        if col_type.startswith("enum(") and "'rejected'" not in col_type:
            cur.execute("""
                ALTER TABLE students
                MODIFY COLUMN status ENUM('INACTIVE','ACTIVE','REJECTED')
                NOT NULL DEFAULT 'INACTIVE'
            """)
            db.commit()
    except Exception:
        db.rollback()
    finally:
        cur.close()
        db.close()


def ensure_students_college_reg_no_column():
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("SHOW COLUMNS FROM students LIKE 'college_reg_no'")
        row = cur.fetchone()
        if not row:
            cur.execute("ALTER TABLE students ADD COLUMN college_reg_no VARCHAR(100) NULL")
            db.commit()
    except Exception:
        db.rollback()
    finally:
        cur.close()
        db.close()


def ensure_staff_auth_tables():
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS staff_accounts (
                id INT AUTO_INCREMENT PRIMARY KEY,
                employee_id INT NULL UNIQUE,
                employee_name VARCHAR(150) NULL,
                department VARCHAR(150) NULL,
                designation VARCHAR(100) NULL,
                email VARCHAR(255) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                is_verified TINYINT(1) NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("SHOW COLUMNS FROM staff_accounts LIKE 'employee_id'")
        emp_col = cur.fetchone()
        if emp_col and str(emp_col[2]).upper() == "NO":
            cur.execute("ALTER TABLE staff_accounts MODIFY COLUMN employee_id INT NULL UNIQUE")
        cur.execute("SHOW COLUMNS FROM staff_accounts LIKE 'employee_name'")
        if not cur.fetchone():
            cur.execute("ALTER TABLE staff_accounts ADD COLUMN employee_name VARCHAR(150) NULL")
        cur.execute("SHOW COLUMNS FROM staff_accounts LIKE 'department'")
        if not cur.fetchone():
            cur.execute("ALTER TABLE staff_accounts ADD COLUMN department VARCHAR(150) NULL")
        cur.execute("SHOW COLUMNS FROM staff_accounts LIKE 'designation'")
        if not cur.fetchone():
            cur.execute("ALTER TABLE staff_accounts ADD COLUMN designation VARCHAR(100) NULL")
        db.commit()
    except Exception:
        db.rollback()
    finally:
        cur.close()
        db.close()


def generate_otp():
    return f"{random.randint(100000, 999999)}"


def send_otp_email(to_email, subject, otp_code):
    sender = os.getenv("SVP_GMAIL_USER") or os.getenv("GMAIL_USER")
    app_password = os.getenv("SVP_GMAIL_APP_PASSWORD") or os.getenv("GMAIL_APP_PASSWORD")
    if not sender or not app_password:
        return False, "Gmail SMTP is not configured on server."

    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = to_email
        msg.set_content(
            f"Your OTP is: {otp_code}\n"
            "This OTP is valid for 10 minutes.\n"
            "If you did not request this, ignore this email."
        )
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender, app_password)
            smtp.send_message(msg)
        return True, ""
    except Exception:
        return False, "Failed to send OTP email."


def start_otp_flow(flow_key, email, extra_data):
    otp = generate_otp()
    session["otp_flow"] = {
        "flow_key": flow_key,
        "email": email.lower().strip(),
        "otp": otp,
        "expires_at": time.time() + 600,
        "extra": extra_data or {},
    }
    return otp


def verify_otp_flow(flow_key, email, otp):
    flow = session.get("otp_flow") or {}
    if not flow:
        return False, "OTP session not found."
    if flow.get("flow_key") != flow_key:
        return False, "Invalid OTP flow."
    if flow.get("email") != email.lower().strip():
        return False, "Email mismatch."
    if time.time() > float(flow.get("expires_at", 0)):
        return False, "OTP expired."
    if flow.get("otp") != str(otp).strip():
        return False, "Incorrect OTP."
    return True, ""


def get_access_scope():
    if "admin" not in session:
        return {"allowed": False, "is_staff": False, "department": None}

    staff_id = session.get("staff_id")
    if not staff_id:
        return {"allowed": True, "is_staff": False, "department": None}

    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT id, department, designation FROM staff_accounts WHERE id=%s", (staff_id,))
    staff = cur.fetchone()
    cur.close()
    db.close()

    if not staff:
        session.clear()
        return {"allowed": False, "is_staff": False, "department": None, "designation": None}

    return {
        "allowed": True,
        "is_staff": True,
        "department": (staff.get("department") or "").strip(),
        "designation": (staff.get("designation") or "").strip(),
    }


def student_in_department(admission_id, department):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT branch FROM students WHERE admission_id=%s", (admission_id,))
    row = cur.fetchone()
    cur.close()
    db.close()
    return bool(row and (row.get("branch") or "").strip().lower() == (department or "").strip().lower())


def can_edit_fees(scope):
    if not scope.get("is_staff"):
        return True
    dept = (scope.get("department") or "").strip().lower()
    desig = (scope.get("designation") or "").strip().lower()
    if "management" in dept:
        return True
    if "hod" in desig or "head of department" in desig:
        return True
    return False


def ensure_students_admission_year_column():
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("SHOW COLUMNS FROM students LIKE 'admission_year'")
        row = cur.fetchone()
        if not row:
            cur.execute("ALTER TABLE students ADD COLUMN admission_year INT NULL")
            db.commit()
    except Exception:
        db.rollback()
    finally:
        cur.close()
        db.close()


def ensure_fee_module_tables():
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS student_fee_structure (
                id INT AUTO_INCREMENT PRIMARY KEY,
                admission_id VARCHAR(50) NOT NULL UNIQUE,
                admission_fee_due DECIMAL(10,2) NOT NULL DEFAULT 0,
                tuition_fee_yearly_due DECIMAL(10,2) NOT NULL DEFAULT 0,
                management_fee_yearly_due DECIMAL(10,2) NOT NULL DEFAULT 0,
                exam_fee_per_sem_due DECIMAL(10,2) NOT NULL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS fee_payments (
                id INT AUTO_INCREMENT PRIMARY KEY,
                admission_id VARCHAR(50) NOT NULL,
                fee_type ENUM('ADMISSION','TUITION','MANAGEMENT','EXAM') NOT NULL,
                academic_year VARCHAR(20) NULL,
                semester_no TINYINT NULL,
                amount DECIMAL(10,2) NOT NULL,
                payment_date DATE NOT NULL,
                receipt_no VARCHAR(60) NOT NULL UNIQUE,
                remarks TEXT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS fee_structure_master (
                id INT AUTO_INCREMENT PRIMARY KEY,
                branch VARCHAR(100) NOT NULL,
                semester_no TINYINT NOT NULL,
                academic_year VARCHAR(20) NOT NULL,
                admission_fee_due DECIMAL(10,2) NOT NULL DEFAULT 0,
                tuition_fee_due DECIMAL(10,2) NOT NULL DEFAULT 0,
                management_fee_due DECIMAL(10,2) NOT NULL DEFAULT 0,
                exam_fee_due DECIMAL(10,2) NOT NULL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_fee_structure_period (branch, semester_no, academic_year)
            )
        """)
        cur.execute("SHOW INDEX FROM fee_payments WHERE Key_name='idx_fee_payments_admission_id'")
        if not cur.fetchone():
            cur.execute("CREATE INDEX idx_fee_payments_admission_id ON fee_payments(admission_id)")
        cur.execute("SHOW INDEX FROM fee_payments WHERE Key_name='idx_fee_payments_payment_date'")
        if not cur.fetchone():
            cur.execute("CREATE INDEX idx_fee_payments_payment_date ON fee_payments(payment_date)")
        db.commit()
    except Exception:
        db.rollback()
    finally:
        cur.close()
        db.close()


def ensure_academic_module_tables():
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS student_subjects (
                id INT AUTO_INCREMENT PRIMARY KEY,
                admission_id VARCHAR(50) NOT NULL,
                semester_no TINYINT NOT NULL DEFAULT 1,
                subject_code VARCHAR(30) NOT NULL,
                subject_name VARCHAR(150) NOT NULL,
                internal_max INT NOT NULL DEFAULT 25,
                external_max INT NOT NULL DEFAULT 75,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_subject_student_sem_code (admission_id, semester_no, subject_code)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS student_internal_marks (
                id INT AUTO_INCREMENT PRIMARY KEY,
                admission_id VARCHAR(50) NOT NULL,
                semester_no TINYINT NOT NULL DEFAULT 1,
                subject_code VARCHAR(30) NOT NULL,
                internal_marks DECIMAL(6,2) NOT NULL DEFAULT 0,
                external_marks DECIMAL(6,2) NOT NULL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_marks_student_sem_code (admission_id, semester_no, subject_code)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS student_attendance (
                id INT AUTO_INCREMENT PRIMARY KEY,
                admission_id VARCHAR(50) NOT NULL,
                semester_no TINYINT NOT NULL DEFAULT 1,
                subject_code VARCHAR(30) NOT NULL,
                total_classes INT NOT NULL DEFAULT 0,
                present_classes INT NOT NULL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_attendance_student_sem_code (admission_id, semester_no, subject_code)
            )
        """)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        cur.close()
        db.close()


def current_academic_year(today=None):
    today = today or datetime.today().date()
    start_year = today.year if today.month >= 6 else today.year - 1
    return f"{start_year}-{str((start_year + 1) % 100).zfill(2)}"


def normalize_branch_key(branch_name):
    raw = (branch_name or "").strip().lower().replace("&", " and ")
    cleaned = re.sub(r"[^a-z0-9]+", " ", raw)
    return re.sub(r"\s+", " ", cleaned).strip()


def branch_code_for_admission(branch_name):
    key = normalize_branch_key(branch_name)
    branch_codes = {
        "computer science and engineering": "CS",
        "computer engineering": "CS",
        "automobile engineering": "AT",
        "automobile": "AT",
        "electronics and communication engineering": "EC",
        "electronic and communication engineering": "EC",
        "electronics and communication": "EC",
        "mechanical engineering": "ME",
        "mechanical": "ME",
    }
    code = branch_codes.get(key)
    if code:
        return code

    parts = [p for p in key.split(" ") if p]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    if len(parts) == 1:
        return parts[0][:2].upper()
    return "SV"


def generate_admission_id(branch_name, academic_year=None):
    ay = (academic_year or current_academic_year()).strip()
    match = re.search(r"(\d{4})", ay)
    start_year = int(match.group(1)) if match else datetime.today().year
    yy = str(start_year)[-2:]
    prefix = f"{branch_code_for_admission(branch_name)}{yy}"
    pattern = f"{prefix}%"

    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("SELECT admission_id FROM students WHERE admission_id LIKE %s", (pattern,))
        rows = cur.fetchall() or []
    finally:
        cur.close()
        db.close()

    max_seq = 0
    seq_pattern = re.compile(rf"^{re.escape(prefix)}(\d{{3}})$")
    for row in rows:
        value = row[0] if isinstance(row, (list, tuple)) else row.get("admission_id")
        text = str(value or "").strip().upper()
        seq_match = seq_pattern.match(text)
        if seq_match:
            max_seq = max(max_seq, int(seq_match.group(1)))

    next_seq = max_seq + 1
    if next_seq > 999:
        raise ValueError(f"Admission sequence limit reached for {prefix}")
    return f"{prefix}{next_seq:03d}"


def parse_int_prefix(text):
    if text is None:
        return None
    raw = str(text).strip()
    if not raw:
        return None
    token = ""
    for ch in raw:
        if ch.isdigit():
            token += ch
        else:
            break
    if not token:
        return None
    try:
        return int(token)
    except ValueError:
        return None


def infer_current_sem(admission_year=None, year_sem=None, today=None):
    today = today or datetime.today().date()
    parsed_admission_year = parse_int_prefix(admission_year)
    fallback_sem = parse_int_prefix(year_sem)

    if not parsed_admission_year:
        return min(max(fallback_sem or 1, 1), 6)

    if today.year == parsed_admission_year and today.month < 6:
        sem = 1
    else:
        years_elapsed = today.year - parsed_admission_year
        sem = (years_elapsed * 2) + (1 if today.month >= 6 else 2)
    return min(max(sem, 1), 6)


def fee_summary_from_row(row, today=None, due=None, paid=None):
    today = today or datetime.today().date()
    current_sem = infer_current_sem(row.get("admission_year"), row.get("year_sem"), today=today)
    due = due or {}
    paid = paid or {}

    admission_due_total = float(due.get("ADMISSION", 0) or 0)
    tuition_due_total = float(due.get("TUITION", 0) or 0)
    management_due_total = float(due.get("MANAGEMENT", 0) or 0)
    exam_due_total = float(due.get("EXAM", 0) or 0)
    total_due = admission_due_total + tuition_due_total + management_due_total + exam_due_total

    admission_paid = float(paid.get("ADMISSION", 0) or 0)
    tuition_paid = float(paid.get("TUITION", 0) or 0)
    management_paid = float(paid.get("MANAGEMENT", 0) or 0)
    exam_paid = float(paid.get("EXAM", 0) or 0)
    total_paid = admission_paid + tuition_paid + management_paid + exam_paid
    balance = round(total_due - total_paid, 2)

    if total_paid <= 0:
        payment_state = "NOT PAID"
    elif balance <= 0:
        payment_state = "PAID"
    else:
        payment_state = "PENDING"

    result = dict(row)
    result.update({
        "current_sem": current_sem,
        "admission_due_total": round(admission_due_total, 2),
        "tuition_due_total": round(tuition_due_total, 2),
        "management_due_total": round(management_due_total, 2),
        "exam_due_total": round(exam_due_total, 2),
        "total_due": round(total_due, 2),
        "admission_paid": round(admission_paid, 2),
        "tuition_paid": round(tuition_paid, 2),
        "management_paid": round(management_paid, 2),
        "exam_paid": round(exam_paid, 2),
        "total_paid": round(total_paid, 2),
        "balance": balance,
        "payment_state": payment_state,
        "academic_year": current_academic_year(today=today),
    })
    return result


def marks_grade(score):
    try:
        val = float(score or 0)
    except (TypeError, ValueError):
        return "F"
    if val >= 90:
        return "A+"
    if val >= 80:
        return "A"
    if val >= 70:
        return "B+"
    if val >= 60:
        return "B"
    if val >= 50:
        return "C"
    return "F"


def infer_uploaded_doc_files(admission_id, docs):
    resolved = dict(docs or {})
    try:
        all_files = [
            f for f in os.listdir(UPLOAD_FOLDER)
            if f.startswith(f"{admission_id}_")
        ]
    except Exception:
        return resolved

    all_files.sort(
        key=lambda name: os.path.getmtime(os.path.join(UPLOAD_FOLDER, name)),
        reverse=True
    )

    def pick(tokens):
        for fname in all_files:
            low = fname.lower()
            if any(t in low for t in tokens):
                return fname
        return None

    if not resolved.get("student_photo"):
        resolved["student_photo"] = pick(["_photo_", "photo"])
    if not resolved.get("aadhaar_file"):
        resolved["aadhaar_file"] = pick(["aadhaar"])
    if not resolved.get("caste_file"):
        resolved["caste_file"] = pick(["caste"])
    if not resolved.get("income_file"):
        resolved["income_file"] = pick(["income"])
    if not resolved.get("marks_card_file"):
        resolved["marks_card_file"] = pick(["marks_card", "_marks_", "marks"])

    return resolved


def verify_password_compat(stored_hash, raw_password):
    stored = str(stored_hash or "").strip()
    if not stored:
        return False

    try:
        if check_password_hash(stored, raw_password):
            return True
    except Exception:
        pass

    return stored == hashlib.sha256((raw_password or "").encode()).hexdigest()


@app.route("/")
def root():
    return redirect("/home")

# =========================
# HOME PAGE (INDEX)
# =========================

@app.route("/home")
def home():
    return render_template("index.html")


# =========================
# LOGIN / AUTH
# =========================
@app.route("/login")
def login():
    return render_template("login_choice.html")


@app.route("/login/student", methods=["GET", "POST"])
def login_student():
    error = ""
    if request.method == "POST":
        if not validate_csrf():
            error = "Session expired. Refresh and try again."
            return render_template("login_student.html", error=error)

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        raw_password = request.form.get("password", "")
        identity = f"{client_ip()}:{username.lower()}"
        if is_auth_rate_limited("student_login", identity):
            error = "Too many failed attempts. Try again in 5 minutes."
            return render_template("login_student.html", error=error)

        db = get_db()
        cur = db.cursor(dictionary=True)
        cur.execute("""
            SELECT * FROM students
            WHERE UPPER(admission_id)=UPPER(%s)
        """, (username,))
        student = cur.fetchone()
        cur.close()
        db.close()

        if not student or not verify_password_compat(student.get("password_hash"), password):
            error = "Invalid student credentials."
            return render_template("login_student.html", error=error)

        clear_auth_failures("student_login", identity)
        if student["status"] == "ACTIVE":
            session.clear()
            session["student"] = student["admission_id"]
            return redirect("/student")
        elif student["status"] == "REJECTED":
            return render_template("student_rejected.html", reason=student.get("rejection_reason"))
        return render_template("student_pending.html")

    return render_template("login_student.html", error=error)


@app.route("/login/staff", methods=["GET", "POST"])
def login_staff_admin():
    ensure_staff_auth_tables()
    error = ""
    if request.method == "POST":
        if not validate_csrf():
            error = "Session expired. Refresh and try again."
            return render_template("login_staff_admin.html", error=error)

        login_type = request.form.get("login_type", "staff").strip().lower()
        login_id = request.form.get("login_id", "").strip()
        raw_password = request.form.get("password", "")
        identity = f"{client_ip()}:{login_type}:{login_id.lower()}"
        if is_auth_rate_limited("staff_admin_login", identity):
            error = "Too many failed attempts. Try again in 5 minutes."
            return render_template("login_staff_admin.html", error=error)

        db = get_db()
        cur = db.cursor(dictionary=True)

        if login_type == "admin":
            cur.execute(
                "SELECT * FROM admins WHERE LOWER(username)=LOWER(%s)",
                (login_id,)
            )
            admin = cur.fetchone()
            if admin and verify_password(admin.get("password_hash", ""), raw_password):
                clear_auth_failures("staff_admin_login", identity)
                session.clear()
                session["admin"] = admin["username"]
                cur.close()
                db.close()
                return redirect("/admin")
            record_auth_failure("staff_admin_login", identity)
            error = "Invalid admin credentials."
        else:
            cur.execute("""
                SELECT * FROM staff_accounts
                WHERE LOWER(email)=LOWER(%s) AND is_verified=1
            """, (login_id,))
            staff = cur.fetchone()
            if staff and verify_password(staff.get("password_hash", ""), raw_password):
                clear_auth_failures("staff_admin_login", identity)
                session.clear()
                session["admin"] = staff["email"]
                session["staff_id"] = staff["id"]
                cur.close()
                db.close()
                return redirect("/admin")
            record_auth_failure("staff_admin_login", identity)
            error = "Invalid staff credentials."

        cur.close()
        db.close()

    return render_template("login_staff_admin.html", error=error)


@app.route("/staff/register", methods=["GET", "POST"])
def staff_register():
    ensure_staff_auth_tables()
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT DISTINCT department FROM employee_details ORDER BY department ASC")
    department_rows = cur.fetchall()
    departments = [row["department"] for row in department_rows if row.get("department")]
    if "Management Department" not in departments:
        departments.append("Management Department")
    departments.sort()
    cur.close()
    db.close()

    error = ""
    message = ""
    if request.method == "POST":
        if not validate_csrf():
            error = "Session expired. Refresh and try again."
            return render_template("staff_register.html", error=error, message=message, departments=departments)

        employee_name = request.form.get("employee_name", "").strip()
        department = request.form.get("department", "").strip()
        designation = request.form.get("designation", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not employee_name:
            error = "Employee name is required."
        elif not department:
            error = "Department is required."
        elif not designation:
            error = "Designation is required."
        elif not email.endswith("@gmail.com"):
            error = "Use a valid Gmail address."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        elif password != confirm_password:
            error = "Passwords do not match."
        else:
            db = get_db()
            cur = db.cursor(dictionary=True)
            cur.execute("SELECT id FROM staff_accounts WHERE LOWER(email)=LOWER(%s)", (email,))
            existing = cur.fetchone()
            cur.close()
            db.close()

            if existing:
                error = "Staff account already exists for this Gmail."
            else:
                pending = {
                    "employee_id": None,
                    "employee_name": employee_name,
                    "department": department,
                    "designation": designation,
                    "email": email,
                    "password_hash": hash_password(password),
                }
                otp = start_otp_flow("staff_register", email, pending)
                sent, msg = send_otp_email(email, "SVP Staff Registration OTP", otp)
                if not sent:
                    error = msg
                else:
                    message = "OTP sent to your Gmail. Verify to complete registration."
                    return redirect(url_for("staff_register_verify", email=email, msg=message))

    return render_template("staff_register.html", error=error, message=message, departments=departments)


@app.route("/staff/register/verify", methods=["GET", "POST"])
def staff_register_verify():
    ensure_staff_auth_tables()
    email = request.args.get("email", "").strip().lower() or request.form.get("email", "").strip().lower()
    error = ""
    message = request.args.get("msg", "")
    if request.method == "POST":
        if not validate_csrf():
            error = "Session expired. Refresh and try again."
            return render_template("staff_register_verify.html", email=email, error=error, message=message)

        otp = request.form.get("otp", "").strip()
        ok, msg = verify_otp_flow("staff_register", email, otp)
        if not ok:
            error = msg
        else:
            flow = session.get("otp_flow") or {}
            extra = flow.get("extra") or {}
            db = get_db()
            cur = db.cursor()
            cur.execute("""
                INSERT INTO staff_accounts (employee_id, employee_name, department, designation, email, password_hash, is_verified)
                VALUES (%s,%s,%s,%s,%s,%s,1)
            """, (
                extra.get("employee_id"),
                extra.get("employee_name"),
                extra.get("department"),
                extra.get("designation"),
                extra.get("email"),
                extra.get("password_hash"),
            ))
            db.commit()
            cur.close()
            db.close()
            session.pop("otp_flow", None)
            return redirect(url_for("login_staff_admin"))

    return render_template("staff_register_verify.html", email=email, error=error, message=message)


@app.route("/forgot-password/student", methods=["GET", "POST"])
def forgot_password_student():
    error = ""
    message = ""
    if request.method == "POST":
        if not validate_csrf():
            error = "Session expired. Refresh and try again."
            return render_template("forgot_password_student.html", error=error, message=message)

        email = request.form.get("email", "").strip().lower()
        db = get_db()
        cur = db.cursor(dictionary=True)
        cur.execute("""
            SELECT spd.admission_id
            FROM student_personal_details spd
            JOIN students s ON s.admission_id = spd.admission_id
            WHERE LOWER(spd.student_email)=LOWER(%s)
            LIMIT 1
        """, (email,))
        row = cur.fetchone()
        cur.close()
        db.close()
        if not row:
            error = "Student email not found."
        else:
            otp = start_otp_flow("student_forgot_password", email, {"admission_id": row["admission_id"]})
            sent, msg = send_otp_email(email, "SVP Student Password Reset OTP", otp)
            if not sent:
                error = msg
            else:
                return redirect(url_for("forgot_password_student_verify"))

    return render_template("forgot_password_student.html", error=error, message=message)


@app.route("/forgot-password/student/verify", methods=["GET", "POST"])
def forgot_password_student_verify():
    email = request.args.get("email", "").strip().lower() or request.form.get("email", "").strip().lower()
    flow = session.get("otp_flow") or {}
    if (not email) and flow.get("flow_key") == "student_forgot_password":
        email = str(flow.get("email") or "").strip().lower()
    error = ""
    if request.method == "POST":
        if not validate_csrf():
            error = "Session expired. Refresh and try again."
            return render_template("forgot_password_verify.html", email=email, error=error, role_name="Student")

        otp = request.form.get("otp", "").strip()
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        if len(new_password) < 6:
            error = "Password must be at least 6 characters."
        elif new_password != confirm_password:
            error = "Passwords do not match."
        elif not email:
            error = "OTP session not found. Please request OTP again."
        else:
            ok, msg = verify_otp_flow("student_forgot_password", email, otp)
            if not ok:
                error = msg
            else:
                flow = session.get("otp_flow") or {}
                admission_id = (flow.get("extra") or {}).get("admission_id")
                db = get_db()
                cur = db.cursor()
                cur.execute(
                    "UPDATE students SET password_hash=%s WHERE admission_id=%s",
                    (generate_password_hash(new_password), admission_id)
                )
                db.commit()
                cur.close()
                db.close()
                session.pop("otp_flow", None)
                return redirect(url_for("login_student"))

    return render_template("forgot_password_verify.html", email=email, error=error, role_name="Student")


@app.route("/forgot-password/staff", methods=["GET", "POST"])
def forgot_password_staff():
    ensure_staff_auth_tables()
    error = ""
    if request.method == "POST":
        if not validate_csrf():
            error = "Session expired. Refresh and try again."
            return render_template("forgot_password_staff.html", error=error)

        email = request.form.get("email", "").strip().lower()
        db = get_db()
        cur = db.cursor(dictionary=True)
        cur.execute("SELECT id FROM staff_accounts WHERE LOWER(email)=LOWER(%s)", (email,))
        staff = cur.fetchone()
        cur.close()
        db.close()
        if not staff:
            error = "Staff email not found."
        else:
            otp = start_otp_flow("staff_forgot_password", email, {"staff_id": staff["id"]})
            sent, msg = send_otp_email(email, "SVP Staff Password Reset OTP", otp)
            if not sent:
                error = msg
            else:
                return redirect(url_for("forgot_password_staff_verify", email=email))

    return render_template("forgot_password_staff.html", error=error)


@app.route("/forgot-password/staff/verify", methods=["GET", "POST"])
def forgot_password_staff_verify():
    ensure_staff_auth_tables()
    email = request.args.get("email", "").strip().lower() or request.form.get("email", "").strip().lower()
    error = ""
    if request.method == "POST":
        if not validate_csrf():
            error = "Session expired. Refresh and try again."
            return render_template("forgot_password_verify.html", email=email, error=error, role_name="Staff")

        otp = request.form.get("otp", "").strip()
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        if len(new_password) < 6:
            error = "Password must be at least 6 characters."
        elif new_password != confirm_password:
            error = "Passwords do not match."
        else:
            ok, msg = verify_otp_flow("staff_forgot_password", email, otp)
            if not ok:
                error = msg
            else:
                flow = session.get("otp_flow") or {}
                staff_id = (flow.get("extra") or {}).get("staff_id")
                db = get_db()
                cur = db.cursor()
                cur.execute(
                    "UPDATE staff_accounts SET password_hash=%s WHERE id=%s",
                    (hash_password(new_password), staff_id)
                )
                db.commit()
                cur.close()
                db.close()
                session.pop("otp_flow", None)
                return redirect(url_for("login_staff_admin"))

    return render_template("forgot_password_verify.html", email=email, error=error, role_name="Staff")


# =========================
# LOGOUT
# =========================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# =========================
# ADMIN DASHBOARD
# =========================
@app.route("/admin")
def admin_dashboard():
    scope = get_access_scope()
    if not scope["allowed"]:
        return redirect("/")
    is_management_staff = scope["is_staff"] and "management" in (scope.get("department") or "").strip().lower()
    is_hod_staff = scope["is_staff"] and (
        "hod" in (scope.get("designation") or "").strip().lower()
        or "head of department" in (scope.get("designation") or "").strip().lower()
    )
    return render_template(
        "admin_dashboard.html",
        is_staff=scope["is_staff"],
        staff_department=scope["department"],
        is_management_staff=is_management_staff,
        is_hod_staff=is_hod_staff,
        can_manage_fees=can_edit_fees(scope)
    )


@app.route("/admin/student-details")
def admin_student_details():
    scope = get_access_scope()
    if not scope["allowed"]:
        return redirect("/")

    from datetime import date

    ensure_students_college_reg_no_column()

    q = request.args.get("q", "").strip()
    status = request.args.get("status", "ACTIVE").strip()
    branch = request.args.get("branch", "").strip()
    if scope["is_staff"]:
        branch = scope["department"]
    current_year = date.today().year
    academic_year = f"{current_year}-{str((current_year + 1) % 100).zfill(2)}"

    db = get_db()
    cur = db.cursor(dictionary=True)

    query = """
        SELECT
            s.admission_id,
            s.student_name,
            s.branch,
            s.mobile,
            COALESCE(s.college_reg_no, '') AS college_reg_no,
            COALESCE(spd.dob, '-') AS dob,
            COALESCE(spd.gender, '-') AS gender,
            COALESCE(spd.caste_category, '-') AS caste_category,
            COALESCE(spd.alloted_category, '-') AS alloted_category,
            COALESCE(sd.student_photo, spd.photo_file, '') AS photo_file
        FROM students s
        LEFT JOIN student_personal_details spd
            ON spd.admission_id = s.admission_id
        LEFT JOIN student_documents sd
            ON sd.admission_id = s.admission_id
        WHERE 1=1
    """
    params = []

    if q:
        query += """
            AND (
                s.student_name LIKE %s
                OR s.admission_id LIKE %s
                OR s.college_reg_no LIKE %s
                OR spd.register_number LIKE %s
            )
        """
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%"])

    if status:
        query += " AND s.status=%s"
        params.append(status)

    if branch:
        query += " AND s.branch=%s"
        params.append(branch)

    query += " ORDER BY s.student_name ASC"

    cur.execute(query, tuple(params))
    students = cur.fetchall()

    cur.execute("SELECT DISTINCT branch FROM students ORDER BY branch ASC")
    branch_rows = cur.fetchall()
    branches = [row["branch"] for row in branch_rows if row.get("branch")]

    cur.close()
    db.close()

    return render_template(
        "admin_student_details.html",
        students=students,
        branches=branches,
        academic_year=academic_year,
        is_staff=scope["is_staff"],
        staff_department=scope["department"],
        filters={
            "q": q,
            "status": status,
            "branch": branch
        }
    )


@app.route("/admin/student-details/edit/<admission_id>", methods=["GET", "POST"])
def edit_student_details(admission_id):
    scope = get_access_scope()
    if not scope["allowed"]:
        return redirect("/")
    if scope["is_staff"] and not student_in_department(admission_id, scope["department"]):
        return "Forbidden: You can edit only your department students.", 403

    ensure_students_college_reg_no_column()

    db = get_db()
    cur = db.cursor(dictionary=True)

    cur.execute("""
        SELECT
            s.admission_id,
            s.student_name,
            s.branch,
            s.mobile,
            COALESCE(s.college_reg_no, '') AS college_reg_no,
            COALESCE(spd.gender, '') AS gender,
            COALESCE(spd.caste_category, '') AS caste_category,
            COALESCE(spd.alloted_category, '') AS alloted_category,
            COALESCE(spd.register_number, '') AS register_number
        FROM students s
        LEFT JOIN student_personal_details spd
            ON spd.admission_id = s.admission_id
        WHERE s.admission_id=%s
    """, (admission_id,))
    student = cur.fetchone()

    if not student:
        cur.close()
        db.close()
        return "Student not found", 404

    if request.method == "POST":
        student_name = request.form.get("student_name", "").strip()
        branch = request.form.get("branch", "").strip()
        mobile = request.form.get("mobile", "").strip()
        college_reg_no = request.form.get("college_reg_no", "").strip()
        gender = request.form.get("gender", "").strip()
        caste_category = request.form.get("caste_category", "").strip()
        alloted_category = request.form.get("alloted_category", "").strip()
        register_number = request.form.get("register_number", "").strip()

        if not student_name or not branch or not mobile:
            cur.close()
            db.close()
            return "Student name, branch, and mobile are required"

        update_cur = db.cursor()
        update_cur.execute("""
            UPDATE students
            SET student_name=%s, branch=%s, mobile=%s, college_reg_no=%s
            WHERE admission_id=%s
        """, (student_name, branch, mobile, college_reg_no, admission_id))

        update_cur.execute("""
            SELECT id FROM student_personal_details WHERE admission_id=%s
        """, (admission_id,))
        personal_exists = update_cur.fetchone()

        if personal_exists:
            update_cur.execute("""
                UPDATE student_personal_details
                SET gender=%s,
                    caste_category=%s,
                    alloted_category=%s,
                    register_number=%s
                WHERE admission_id=%s
            """, (gender, caste_category, alloted_category, register_number, admission_id))
        else:
            update_cur.execute("""
                INSERT INTO student_personal_details
                (admission_id, gender, caste_category, alloted_category, register_number)
                VALUES (%s, %s, %s, %s, %s)
            """, (admission_id, gender, caste_category, alloted_category, register_number))

        db.commit()
        update_cur.close()
        cur.close()
        db.close()
        return redirect("/admin/student-details")

    cur.close()
    db.close()
    return render_template("admin_edit_student.html", student=student)


@app.route("/admin/employees")
def admin_employees():
    scope = get_access_scope()
    if not scope["allowed"]:
        return redirect("/")

    ensure_employees_table()

    employee_type = request.args.get("employee_type", "").strip()
    department = request.args.get("department", "").strip()
    if scope["is_staff"]:
        department = scope["department"]
    hod_only = request.args.get("hod", "").strip().lower()
    sort_by = request.args.get("sort_by", "employee_name").strip()
    name_query = request.args.get("name", "").strip()

    sort_columns = {
        "employee_name": "employee_name",
        "department": "department",
        "designation": "designation"
    }
    sort_column = sort_columns.get(sort_by, "employee_name")

    db = get_db()
    cur = db.cursor(dictionary=True)

    query = """
        SELECT id, employee_name, department, designation, mobile_no, employee_type
        FROM employee_details
        WHERE 1=1
    """
    params = []

    if employee_type:
        query += " AND employee_type = %s"
        params.append(employee_type)

    if department:
        query += " AND department = %s"
        params.append(department)

    if name_query:
        query += " AND LOWER(employee_name) LIKE LOWER(%s)"
        params.append(f"%{name_query}%")

    if hod_only == "yes":
        query += " AND (UPPER(designation) LIKE %s OR UPPER(designation) = %s)"
        params.append("%HOD%")
        params.append("HEAD OF DEPARTMENT")

    query += f" ORDER BY {sort_column} ASC"
    cur.execute(query, tuple(params))
    employees = cur.fetchall()

    cur.execute("SELECT DISTINCT department FROM employee_details ORDER BY department ASC")
    department_rows = cur.fetchall()
    departments = [row["department"] for row in department_rows if row.get("department")]

    cur.execute("SELECT DISTINCT employee_name FROM employee_details ORDER BY employee_name ASC")
    name_rows = cur.fetchall()
    employee_names = [row["employee_name"] for row in name_rows if row.get("employee_name")]

    cur.close()
    db.close()

    return render_template(
        "admin_employees.html",
        employees=employees,
        departments=departments,
        employee_names=employee_names,
        is_staff=scope["is_staff"],
        staff_department=scope["department"],
        filters={
            "employee_type": employee_type,
            "department": department,
            "hod": hod_only,
            "sort_by": sort_by,
            "name": name_query
        }
    )


@app.route("/admin/employees/add", methods=["GET", "POST"])
def add_employee():
    scope = get_access_scope()
    if not scope["allowed"]:
        return redirect("/")

    ensure_employees_table()

    if request.method == "POST":
        employee_name = request.form.get("employee_name", "").strip()
        department = request.form.get("department", "").strip()
        if scope["is_staff"]:
            department = scope["department"]
        designation = request.form.get("designation", "").strip()
        mobile_no = request.form.get("mobile_no", "").strip()

        if not employee_name or not department or not designation or not mobile_no:
            return "All fields are required"

        if not mobile_no.isdigit() or len(mobile_no) != 10:
            return "PLEASE ENTER 10 DIGIT MOBILE NUMBER"

        designation_type_map = {
            "HEAD OF DEPARTMENT": "TEACHING",
            "TEACHING STAFF": "TEACHING",
            "NON TEACHING STAFF": "NON-TEACHING",
            "HELPER": "HELPER"
        }
        employee_type = designation_type_map.get(designation.upper(), "TEACHING")

        db = get_db()
        cur = db.cursor()
        cur.execute("""
            INSERT INTO employee_details
            (employee_name, department, designation, mobile_no, employee_type)
            VALUES (%s, %s, %s, %s, %s)
        """, (employee_name, department, designation, mobile_no, employee_type))
        db.commit()
        cur.close()
        db.close()

        return redirect("/admin/employees")

    return render_template(
        "add_employee.html",
        edit_mode=False,
        employee={},
        is_staff=scope["is_staff"],
        staff_department=scope["department"]
    )


@app.route("/admin/employees/edit/<int:employee_id>", methods=["GET", "POST"])
def edit_employee(employee_id):
    scope = get_access_scope()
    if not scope["allowed"]:
        return redirect("/")

    ensure_employees_table()

    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT id, employee_name, department, designation, mobile_no
        FROM employee_details
        WHERE id=%s
    """, (employee_id,))
    employee = cur.fetchone()
    if scope["is_staff"] and employee and (employee.get("department") or "").strip().lower() != (scope["department"] or "").strip().lower():
        cur.close()
        db.close()
        return "Forbidden: You can edit only your department.", 403

    if not employee:
        cur.close()
        db.close()
        return "Employee not found", 404

    if request.method == "POST":
        employee_name = request.form.get("employee_name", "").strip()
        department = request.form.get("department", "").strip()
        if scope["is_staff"]:
            department = scope["department"]
        designation = request.form.get("designation", "").strip()
        mobile_no = request.form.get("mobile_no", "").strip()

        if not employee_name or not department or not designation or not mobile_no:
            cur.close()
            db.close()
            return "All fields are required"

        if not mobile_no.isdigit() or len(mobile_no) != 10:
            cur.close()
            db.close()
            return "PLEASE ENTER 10 DIGIT MOBILE NUMBER"

        designation_type_map = {
            "HEAD OF DEPARTMENT": "TEACHING",
            "TEACHING STAFF": "TEACHING",
            "NON TEACHING STAFF": "NON-TEACHING",
            "HELPER": "HELPER"
        }
        employee_type = designation_type_map.get(designation.upper(), "TEACHING")

        update_cur = db.cursor()
        update_cur.execute("""
            UPDATE employee_details
            SET employee_name=%s,
                department=%s,
                designation=%s,
                mobile_no=%s,
                employee_type=%s
            WHERE id=%s
        """, (employee_name, department, designation, mobile_no, employee_type, employee_id))
        db.commit()
        update_cur.close()
        cur.close()
        db.close()
        return redirect("/admin/employees")

    cur.close()
    db.close()
    return render_template(
        "add_employee.html",
        edit_mode=True,
        employee=employee,
        is_staff=scope["is_staff"],
        staff_department=scope["department"]
    )


# =========================
# ONLINE ADMISSION (PUBLIC)
# =========================

import os
import random
import hashlib
from werkzeug.utils import secure_filename
from flask import request, render_template
from db import get_db
UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@app.route("/admission", methods=["GET", "POST"])
def admission():
    if request.method == "POST":
        admission_id = generate_admission_id(
            request.form.get("branch", ""),
            current_academic_year()
        )

        # PASSWORD (student creates)
        password_hash = generate_password_hash(request.form["password"])


        # =========================
        # FILE UPLOADS
        # =========================
        photo = request.files["photo"]
        marks_card = request.files["marks_card"]
        caste_cert = request.files["caste_certificate"]
        income_cert = request.files["income_certificate"]

        photo_name = admission_id + "_photo_" + secure_filename(photo.filename)
        marks_name = admission_id + "_marks_" + secure_filename(marks_card.filename)
        caste_name = admission_id + "_caste_" + secure_filename(caste_cert.filename)
        income_name = admission_id + "_income_" + secure_filename(income_cert.filename)

        photo.save(os.path.join(UPLOAD_FOLDER, photo_name))
        marks_card.save(os.path.join(UPLOAD_FOLDER, marks_name))
        caste_cert.save(os.path.join(UPLOAD_FOLDER, caste_name))
        income_cert.save(os.path.join(UPLOAD_FOLDER, income_name))

        # =========================
        # DATABASE INSERTS
        # =========================
        db = get_db()
        cur = db.cursor()

        # 1️⃣ STUDENTS TABLE (LOGIN)
        cur.execute("""
            INSERT INTO students
            (admission_id, student_name, branch, mobile, password_hash, status)
            VALUES (%s,%s,%s,%s,%s,'INACTIVE')
        """, (
            admission_id,
            request.form["student_name"],
            request.form["branch"],
            request.form["student_mobile"],
            password_hash
        ))

        # 2️⃣ STUDENT PERSONAL DETAILS
        cur.execute("""
    INSERT INTO student_personal_details
    (admission_id, student_mobile, student_email,
     indian_nationality, religion, disability,
     aadhaar_number,
     caste_rd_number, caste_certificate_file,
     income_rd_number, income_certificate_file,
     annual_income,
     mother_name, mother_mobile,
     father_name, father_mobile,
     residential_address, permanent_address)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
""", (
    admission_id,
    request.form["student_mobile"].strip().upper(),
    request.form["student_email"].strip(),   # ← comma added here
    request.form["indian_nationality"].strip().upper(),
    request.form["religion"].strip().upper(),
    request.form["disability"].strip().upper(),
    request.form["aadhaar_number"].strip().upper(),
    request.form["caste_rd_number"].strip().upper(),
    caste_name,
    request.form["income_rd_number"].strip().upper(),
    income_name,
    request.form["annual_income"],
    request.form["mother_name"].strip().upper(),
    request.form["mother_mobile"],
    request.form["father_name"].strip().upper(),
    request.form["father_mobile"],
    request.form["residential_address"],
    request.form["permanent_address"]
))

        

        db.commit()

        return render_template(
            "admission_success.html",
            admission_id=admission_id
        )

    return render_template("admission_form.html")

@app.route("/admission/step-1", methods=["GET", "POST"])
def admission_step1():
    if request.method == "POST":
        admission_year = current_academic_year()

        session["admission"] = {
            "admission_id": None,
            "admission_year": admission_year,

            # Student Personal
            "student_name": request.form["student_name"],
            "student_mobile": request.form["student_mobile"],
            "student_email": request.form["student_email"],
            "dob": request.form["dob"],
            "gender": request.form["gender"],
            "indian_nationality": request.form["indian_nationality"],
            "religion": request.form.get("religion"),
            "caste_category": request.form["caste_category"],
            "alloted_category": request.form["alloted_category"],

            # Academic
            # Academic (Dynamic)
"qualifying_exam": request.form["qualifying_exam"],
"year_of_passing": request.form["year_of_passing"],
"register_number": request.form["register_number"],

# SSLC / PUC Marks
"maths_marks": request.form.get("maths_marks"),
"science_marks": request.form.get("science_marks"),
"total_marks": request.form.get("total_marks"),
"marks_obtained": request.form.get("marks_obtained"),
"percentage": request.form.get("percentage"),




            # Admission
            "admission_quota": request.form["admission_quota"],
            "branch": request.form["branch"],
            "password": request.form["password"]
        }

        session.modified = True
        return redirect("/admission/step-2")

    return render_template("admission_step1.html")






@app.route("/admission/step-2", methods=["GET", "POST"])
def admission_step2():

    # get admission data created in step-1
    admission = session.get("admission")
    if not admission:
        return redirect("/admission/step-1")

    if request.method == "POST":
        admission.update({
            "father_name": request.form.get("father_name").upper(),
            "father_mobile": request.form.get("father_mobile"),
            "mother_name": request.form.get("mother_name").upper(),
            "mother_mobile": request.form.get("mother_mobile"),
            "residential_address": request.form.get("residential_address").upper(),
            "permanent_address": request.form.get("permanent_address").upper(),
        })

        # VERY IMPORTANT
        session["admission"] = admission
        session.modified = True

        return redirect("/admission/step-3")

    return render_template("admission_step2.html")



from datetime import date
import hashlib
import os
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


from datetime import date
import hashlib
import os
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


from datetime import date
from werkzeug.utils import secure_filename

from datetime import date
import hashlib

import re
from datetime import date
import hashlib

@app.route("/admission/step-3", methods=["GET", "POST"])
def admission_step3():

    admission = session.get("admission")
    if not admission:
        return redirect("/admission/step-1")

    # =========================
    # POST → VALIDATION & SUBMIT
    # =========================
    if request.method == "POST":
        if not admission.get("admission_id"):
            admission["admission_id"] = generate_admission_id(
                admission.get("branch", ""),
                admission.get("admission_year") or current_academic_year()
            )
            session["admission"] = admission
            session.modified = True

        # ===== READ STEP-3 FORM DATA =====
        aadhaar_number = request.form.get("aadhaar_number", "").strip().upper()
        caste_rd_number = request.form.get("caste_rd_number", "").strip().upper()
        income_rd_number = request.form.get("income_rd_number", "").strip().upper()

        # ===== AADHAAR VALIDATION =====
        if not aadhaar_number.isdigit() or len(aadhaar_number) != 12:
            return "❌ Aadhaar number must be exactly 12 digits"

        # ===== CASTE RD VALIDATION =====
        if not re.match(r"^[A-Za-z0-9]{6,20}$", caste_rd_number):
            return "❌ Invalid Caste Certificate RD Number"

        # ===== INCOME RD VALIDATION =====
        if not re.match(r"^[A-Za-z0-9]{6,20}$", income_rd_number):
            return "❌ Invalid Income Certificate RD Number"

        # ===== AGE VALIDATION =====
        dob = date.fromisoformat(admission["dob"])
        age = (date.today() - dob).days // 365
        if age < 14:
            return "❌ Student must be at least 14 years old"

        # ===== YEAR VALIDATION =====
        year = int(admission["year_of_passing"])
        current_year = date.today().year
        if year > current_year or year < current_year - 10:
            return "❌ Invalid Year of Passing"

        # ===== QUALIFYING EXAM =====
        if admission["qualifying_exam"] not in ["SSLC","CBSE","ICSE", "PUC", "ITI"]:
            return "❌ Invalid Qualifying Exam"

        # ===== FILES (SAVE IF PROVIDED) =====
        def save_step3_file(file_obj, prefix):
            if not file_obj or file_obj.filename == "":
                return None
            if not allowed_file(file_obj.filename):
                return "INVALID_FILE"
            filename = f"{admission['admission_id']}_{prefix}_{secure_filename(file_obj.filename)}"
            file_obj.save(os.path.join(UPLOAD_FOLDER, filename))
            return filename

        photo_name = save_step3_file(request.files.get("student_photo"), "photo")
        aadhaar_file_name = save_step3_file(request.files.get("aadhaar_file"), "aadhaar")
        caste_file_name = save_step3_file(request.files.get("caste_certificate_file"), "caste")
        income_file_name = save_step3_file(request.files.get("income_certificate_file"), "income")
        marks_file_name = save_step3_file(request.files.get("marks_card_file"), "marks")

        if "INVALID_FILE" in [photo_name, aadhaar_file_name, caste_file_name, income_file_name, marks_file_name]:
            return "❌ Invalid file type. Allowed: PDF, JPG, JPEG, PNG"

        

        # ================= DATABASE =================
        db = get_db()
        cur = db.cursor()

        # ===== CREATE STUDENT LOGIN =====
        cur.execute("""
            INSERT INTO students
            (admission_id, student_name, branch, mobile, password_hash, status)
            VALUES (%s,%s,%s,%s,%s,'INACTIVE')
        """, (
            admission["admission_id"],
            admission["student_name"],
            admission["branch"],
            admission["student_mobile"],
           generate_password_hash(admission["password"])

        ))

        # ===== PERSONAL DETAILS =====
        cur.execute("""
            INSERT INTO student_personal_details (
                admission_id,
                dob, gender, indian_nationality, religion,
                caste_category, alloted_category,
                qualifying_exam, year_of_passing, register_number,
                admission_quota,
                father_name, father_mobile,
                mother_name, mother_mobile,
                residential_address, permanent_address
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                      %s,%s,%s,%s,%s,%s)
        """, (
            admission["admission_id"],
            admission["dob"],
            admission["gender"],
            admission["indian_nationality"],
            admission["religion"],
            admission["caste_category"],
            admission["alloted_category"],
            admission["qualifying_exam"],
            admission["year_of_passing"],
            admission["register_number"],
            admission["admission_quota"],
            admission["father_name"],
            admission["father_mobile"],
            admission["mother_name"],
            admission["mother_mobile"],
            admission["residential_address"],
            admission["permanent_address"]
        ))

        # ===== STEP-3 DETAILS (AADHAAR / RD NUMBERS + FILES) =====
        cur.execute(
            "SELECT id FROM student_documents WHERE admission_id=%s",
            (admission["admission_id"],)
        )
        existing_doc = cur.fetchone()

        if existing_doc:
            cur.execute("""
                UPDATE student_documents
                SET aadhaar_number=%s,
                    caste_rd_number=%s,
                    income_rd_number=%s,
                    student_photo=COALESCE(%s, student_photo),
                    aadhaar_file=COALESCE(%s, aadhaar_file),
                    caste_file=COALESCE(%s, caste_file),
                    income_file=COALESCE(%s, income_file),
                    marks_card_file=COALESCE(%s, marks_card_file)
                WHERE admission_id=%s
            """, (
                aadhaar_number,
                caste_rd_number,
                income_rd_number,
                photo_name,
                aadhaar_file_name,
                caste_file_name,
                income_file_name,
                marks_file_name,
                admission["admission_id"]
            ))
        else:
            cur.execute("""
                INSERT INTO student_documents
                (admission_id, aadhaar_number, caste_rd_number, income_rd_number,
                 student_photo, aadhaar_file, caste_file, income_file, marks_card_file)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                admission["admission_id"],
                aadhaar_number,
                caste_rd_number,
                income_rd_number,
                photo_name,
                aadhaar_file_name,
                caste_file_name,
                income_file_name,
                marks_file_name
            ))

        db.commit()
        cur.close()
        db.close()

        # CLEAR SESSION
        session.pop("admission", None)

        return render_template(
            "admission_success.html",
            admission_id=admission["admission_id"]
        )

    # =========================
    # GET → SHOW PAGE
    # =========================
    return render_template(
        "admission_step3.html",
        admission_id=admission["admission_id"]
    )

# =========================
# ADMIN: VIEW APPLICATIONS
# =========================
@app.route("/admin/applications")
def admin_applications():
    scope = get_access_scope()
    if not scope["allowed"]:
        return redirect("/")

    ensure_students_status_supports_rejected()
    ensure_students_rejection_reason_column()

    q = request.args.get("q", "").strip()
    status = request.args.get("status", "INACTIVE")
    branch = request.args.get("branch", "").strip()
    if scope["is_staff"]:
        branch = scope["department"]

    db = get_db()
    cur = db.cursor(dictionary=True)

    query = """
        SELECT
            s.admission_id,
            s.student_name,
            s.branch,
            s.status,
            COALESCE(spd.student_mobile, s.mobile) AS mobile,
            COALESCE(spd.dob, '-') AS dob,
            COALESCE(spd.gender, '-') AS gender,
            COALESCE(spd.caste_category, '-') AS caste_category,
            COALESCE(spd.alloted_category, '-') AS alloted_category,
            COALESCE(spd.register_number, '-') AS register_number,
            COALESCE(s.rejection_reason, '-') AS rejection_reason
        FROM students s
        LEFT JOIN student_personal_details spd
            ON spd.admission_id = s.admission_id
        WHERE 1=1
    """
    params = []

    if status and status != "ALL":
        query += " AND s.status=%s"
        params.append(status)

    if branch and branch != "ALL":
        query += " AND s.branch=%s"
        params.append(branch)

    if q:
        query += """
            AND (
                s.student_name LIKE %s
                OR s.admission_id LIKE %s
                OR s.college_reg_no LIKE %s
                OR spd.register_number LIKE %s
            )
        """
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%"])

    query += """
        ORDER BY s.student_name ASC
    """

    cur.execute(query, tuple(params))

    students = cur.fetchall()

    cur.execute("SELECT DISTINCT branch FROM students ORDER BY branch ASC")
    branch_rows = cur.fetchall()
    branches = [row["branch"] for row in branch_rows if row.get("branch")]

    cur.close()
    db.close()

    return render_template(
        "admin_applications.html",
        students=students,
        branches=branches,
        is_staff=scope["is_staff"],
        staff_department=scope["department"],
        q=q,
        status=status,
        branch=branch
    )

# =========================
# ADMIN: APPROVE STUDENT
# =========================
@app.route("/approve/<admission_id>")

def approve_student(admission_id):
    scope = get_access_scope()
    if not scope["allowed"]:
        return redirect("/")
    if scope["is_staff"] and not student_in_department(admission_id, scope["department"]):
        return "Forbidden: You can approve only your department students.", 403

    ensure_students_status_supports_rejected()
    ensure_students_rejection_reason_column()

    next_status = request.args.get("status", "INACTIVE")
    q = request.args.get("q", "")
    branch = request.args.get("branch", "")

    db = get_db()
    cur = db.cursor()

    cur.execute("""
        UPDATE students
        SET status='ACTIVE'
        WHERE admission_id=%s
    """, (admission_id,))

    db.commit()
    cur.close()
    db.close()   
    return redirect(url_for("admin_applications", status=next_status, q=q, branch=branch))

@app.route("/reject/<admission_id>", methods=["POST"])
def reject_student(admission_id):
    scope = get_access_scope()
    if not scope["allowed"]:
        return redirect("/")
    if scope["is_staff"] and not student_in_department(admission_id, scope["department"]):
        return "Forbidden: You can reject only your department students.", 403

    ensure_students_status_supports_rejected()
    ensure_students_rejection_reason_column()

    reason = request.form.get("reason", "").strip()
    next_status = request.form.get("status", "REJECTED")
    q = request.form.get("q", "")
    branch = request.form.get("branch", "")

    if not reason:
        return "Reason is required"

    db = get_db()
    cur = db.cursor()

    cur.execute("""
        UPDATE students
        SET status='REJECTED', rejection_reason=%s
        WHERE admission_id=%s
    """, (reason, admission_id))

    db.commit()
    cur.close()
    db.close()   

    return redirect(url_for("admin_applications", status=next_status, q=q, branch=branch))


# ADMIN: ACADEMIC RECORDS
# =========================
@app.route("/admin/academic-records", methods=["GET", "POST"])
def admin_academic_records():
    scope = get_access_scope()
    if not scope["allowed"]:
        return redirect("/")

    ensure_academic_module_tables()

    q = (request.args.get("admission_id") or "").strip().upper()
    msg = request.args.get("msg", "")

    if request.method == "POST":
        action = (request.form.get("action") or "").strip()
        admission_id = (request.form.get("admission_id") or "").strip().upper()
        semester_no = parse_int_prefix(request.form.get("semester_no")) or 1

        if not admission_id:
            return redirect(url_for("admin_academic_records", msg="Admission ID is required."))
        if scope["is_staff"] and not student_in_department(admission_id, scope["department"]):
            return "Forbidden: You can edit only your department students.", 403

        db = get_db()
        cur = db.cursor()
        try:
            if action == "subject":
                subject_code = (request.form.get("subject_code") or "").strip().upper()
                subject_name = (request.form.get("subject_name") or "").strip()
                internal_max = parse_int_prefix(request.form.get("internal_max")) or 25
                external_max = parse_int_prefix(request.form.get("external_max")) or 75
                if not subject_code or not subject_name:
                    return redirect(url_for("admin_academic_records", admission_id=admission_id, msg="Subject code and name are required."))
                cur.execute("""
                    INSERT INTO student_subjects
                    (admission_id, semester_no, subject_code, subject_name, internal_max, external_max)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE
                        subject_name=VALUES(subject_name),
                        internal_max=VALUES(internal_max),
                        external_max=VALUES(external_max)
                """, (admission_id, semester_no, subject_code, subject_name, internal_max, external_max))
                message = "Subject saved."
            elif action == "marks":
                subject_code = (request.form.get("subject_code") or "").strip().upper()
                internal_marks = float(request.form.get("internal_marks") or 0)
                external_marks = float(request.form.get("external_marks") or 0)
                if not subject_code:
                    return redirect(url_for("admin_academic_records", admission_id=admission_id, msg="Subject code is required for marks."))
                cur.execute("""
                    INSERT INTO student_internal_marks
                    (admission_id, semester_no, subject_code, internal_marks, external_marks)
                    VALUES (%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE
                        internal_marks=VALUES(internal_marks),
                        external_marks=VALUES(external_marks)
                """, (admission_id, semester_no, subject_code, internal_marks, external_marks))
                message = "Marks saved."
            elif action == "attendance":
                subject_code = (request.form.get("subject_code") or "").strip().upper()
                total_classes = parse_int_prefix(request.form.get("total_classes")) or 0
                present_classes = parse_int_prefix(request.form.get("present_classes")) or 0
                if not subject_code:
                    return redirect(url_for("admin_academic_records", admission_id=admission_id, msg="Subject code is required for attendance."))
                if present_classes > total_classes:
                    return redirect(url_for("admin_academic_records", admission_id=admission_id, msg="Present classes cannot be greater than total classes."))
                cur.execute("""
                    INSERT INTO student_attendance
                    (admission_id, semester_no, subject_code, total_classes, present_classes)
                    VALUES (%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE
                        total_classes=VALUES(total_classes),
                        present_classes=VALUES(present_classes)
                """, (admission_id, semester_no, subject_code, total_classes, present_classes))
                message = "Attendance saved."
            else:
                return redirect(url_for("admin_academic_records", admission_id=admission_id, msg="Invalid academic action."))
            db.commit()
        finally:
            cur.close()
            db.close()

        return redirect(url_for("admin_academic_records", admission_id=admission_id, msg=message))

    student = None
    records = []
    if q:
        db = get_db()
        cur = db.cursor(dictionary=True)
        cur.execute("SELECT admission_id, student_name, branch, year_sem, admission_year FROM students WHERE admission_id=%s", (q,))
        student = cur.fetchone()
        if student and scope["is_staff"] and (student.get("branch") or "").strip().lower() != (scope["department"] or "").strip().lower():
            cur.close()
            db.close()
            return "Forbidden: You can view only your department students.", 403

        if student:
            semester_no = infer_current_sem(student.get("admission_year"), student.get("year_sem"))
            cur.execute("""
                SELECT
                    ss.semester_no,
                    ss.subject_code,
                    ss.subject_name,
                    ss.internal_max,
                    ss.external_max,
                    COALESCE(sm.internal_marks, 0) AS internal_marks,
                    COALESCE(sm.external_marks, 0) AS external_marks,
                    COALESCE(sa.total_classes, 0) AS total_classes,
                    COALESCE(sa.present_classes, 0) AS present_classes
                FROM student_subjects ss
                LEFT JOIN student_internal_marks sm
                    ON sm.admission_id=ss.admission_id
                    AND sm.semester_no=ss.semester_no
                    AND sm.subject_code=ss.subject_code
                LEFT JOIN student_attendance sa
                    ON sa.admission_id=ss.admission_id
                    AND sa.semester_no=ss.semester_no
                    AND sa.subject_code=ss.subject_code
                WHERE ss.admission_id=%s AND ss.semester_no=%s
                ORDER BY ss.subject_name ASC
            """, (q, semester_no))
            records = cur.fetchall()

        cur.close()
        db.close()

    return render_template(
        "admin_academic_records.html",
        q=q,
        student=student,
        records=records,
        msg=msg,
        is_staff=scope["is_staff"],
        staff_department=scope["department"],
    )


# =========================
# ADMIN: ADD STUDENT
# =========================
@app.route("/add-student", methods=["GET", "POST"])
def add_student():
    scope = get_access_scope()
    if not scope["allowed"]:
        return redirect("/")

    if request.method == "POST":
        admission_id = request.form["admission_id"]
        name = request.form["student_name"]
        branch = request.form["branch"]
        if scope["is_staff"]:
            branch = scope["department"]
        year_sem = request.form["year_sem"]
        mobile = request.form["mobile"]
        password = password = generate_password_hash(request.form["password"])


        db = get_db()
        cur = db.cursor()
        cur.execute("""
            INSERT INTO students
            (admission_id, student_name, branch, year_sem, mobile, password_hash, status)
            VALUES (%s,%s,%s,%s,%s,%s,'ACTIVE')
        """, (admission_id, name, branch, year_sem, mobile, password))
        db.commit()

        return "✅ Student Added Successfully"

    return render_template("add_student.html", is_staff=scope["is_staff"], staff_department=scope["department"])


# =========================
# ADMIN: ADD EDUCATION
# =========================
@app.route("/add-education", methods=["GET", "POST"])
def add_education():
    scope = get_access_scope()
    if not scope["allowed"]:
        return redirect("/")

    if request.method == "POST":
        admission_id = request.form["admission_id"]
        if scope["is_staff"] and not student_in_department(admission_id, scope["department"]):
            return "Forbidden: You can edit only your department students.", 403
        data = (
            admission_id,
            request.form["qualifying_exam"],
            request.form["register_number"],
            request.form["year_of_passing"],
            request.form["total_max_marks"],
            request.form["total_marks_obtained"],
            request.form["science_max_marks"],
            request.form["science_marks_obtained"],
            request.form["maths_max_marks"],
            request.form["maths_marks_obtained"]
        )

        db = get_db()
        cur = db.cursor()
        cur.execute("""
            INSERT INTO education_details
            (admission_id, qualifying_exam, register_number, year_of_passing,
             total_max_marks, total_marks_obtained,
             science_max_marks, science_marks_obtained,
             maths_max_marks, maths_marks_obtained)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, data)
        db.commit()

        return "✅ Education Details Added"

    return render_template("add_education.html")


# =========================
# ADMIN: FEES MANAGEMENT
# =========================
def fetch_fee_overview_rows(q="", branch="", sem="", payment_state="", sort_by="name", forced_department=""):
    ensure_students_college_reg_no_column()
    ensure_students_admission_year_column()
    ensure_fee_module_tables()

    db = get_db()
    cur = db.cursor(dictionary=True)

    query = """
        SELECT
            s.admission_id,
            s.student_name,
            s.branch,
            s.mobile,
            s.year_sem,
            s.admission_year,
            COALESCE(s.college_reg_no, '') AS college_reg_no
        FROM students s
        WHERE 1=1
    """
    params = []

    if q:
        query += """
            AND (
                s.student_name LIKE %s
                OR s.admission_id LIKE %s
                OR s.college_reg_no LIKE %s
            )
        """
        like_q = f"%{q}%"
        params.extend([like_q, like_q, like_q])

    if forced_department:
        query += " AND s.branch=%s"
        params.append(forced_department)
    elif branch:
        query += " AND s.branch=%s"
        params.append(branch)

    cur.execute(query, tuple(params))
    raw_rows = cur.fetchall()

    cur.execute("SELECT DISTINCT branch FROM students ORDER BY branch ASC")
    branches = [row["branch"] for row in cur.fetchall() if row.get("branch")]

    ay = current_academic_year()
    cur.execute("""
        SELECT
            branch,
            semester_no,
            admission_fee_due,
            tuition_fee_due,
            management_fee_due,
            exam_fee_due
        FROM fee_structure_master
        WHERE academic_year=%s
    """, (ay,))
    structure_rows = cur.fetchall()
    fee_map = {}
    for fr in structure_rows:
        fee_map[(fr["branch"], int(fr["semester_no"]))] = {
            "ADMISSION": float(fr.get("admission_fee_due") or 0),
            "TUITION": float(fr.get("tuition_fee_due") or 0),
            "MANAGEMENT": float(fr.get("management_fee_due") or 0),
            "EXAM": float(fr.get("exam_fee_due") or 0),
        }

    cur.execute("""
        SELECT
            admission_id,
            fee_type,
            semester_no,
            COALESCE(SUM(amount), 0) AS total_amount
        FROM fee_payments
        WHERE academic_year=%s
        GROUP BY admission_id, fee_type, semester_no
    """, (ay,))
    payment_rows = cur.fetchall()
    payment_map = {}
    for pr in payment_rows:
        sem_no = int(pr["semester_no"]) if pr.get("semester_no") else None
        if sem_no is None:
            continue
        payment_map[(pr["admission_id"], sem_no, pr["fee_type"])] = float(pr.get("total_amount") or 0)

    cur.close()
    db.close()

    rows = []
    for row in raw_rows:
        current_sem = infer_current_sem(row.get("admission_year"), row.get("year_sem"))
        due = fee_map.get((row.get("branch"), current_sem), {})
        paid = {
            "ADMISSION": payment_map.get((row.get("admission_id"), current_sem, "ADMISSION"), 0),
            "TUITION": payment_map.get((row.get("admission_id"), current_sem, "TUITION"), 0),
            "MANAGEMENT": payment_map.get((row.get("admission_id"), current_sem, "MANAGEMENT"), 0),
            "EXAM": payment_map.get((row.get("admission_id"), current_sem, "EXAM"), 0),
        }
        rows.append(fee_summary_from_row(row, due=due, paid=paid))

    if sem:
        try:
            sem_value = int(sem)
            rows = [row for row in rows if row["current_sem"] == sem_value]
        except ValueError:
            pass

    if payment_state:
        state = payment_state.strip().upper()
        rows = [row for row in rows if row["payment_state"] == state]

    sort_key_map = {
        "name": lambda row: (row.get("student_name") or "").lower(),
        "admission_id": lambda row: (row.get("admission_id") or "").lower(),
        "branch": lambda row: (row.get("branch") or "").lower(),
        "sem_asc": lambda row: row.get("current_sem") or 0,
        "sem_desc": lambda row: -(row.get("current_sem") or 0),
        "balance_desc": lambda row: -(row.get("balance") or 0),
        "balance_asc": lambda row: row.get("balance") or 0,
    }
    rows.sort(key=sort_key_map.get(sort_by, sort_key_map["name"]))
    return rows, branches


@app.route("/admin/fees", methods=["GET", "POST"])
def admin_fees():
    scope = get_access_scope()
    if not scope["allowed"]:
        return redirect("/")
    can_manage = can_edit_fees(scope)

    ensure_students_college_reg_no_column()
    ensure_students_admission_year_column()
    ensure_fee_module_tables()

    msg = request.args.get("msg", "")
    ay = current_academic_year()

    if request.method == "POST":
        if not can_manage:
            return "Forbidden: Only Admin, HOD, or Management staff can add/edit fee details.", 403
        fee_branch = request.form.get("fee_branch", "").strip()
        if scope["is_staff"] and "management" not in (scope.get("department") or "").strip().lower():
            fee_branch = scope["department"]
        semester_no = parse_int_prefix(request.form.get("semester_no", "").strip())
        academic_year = request.form.get("academic_year", "").strip() or ay
        admission_fee_due = float(request.form.get("admission_fee_due") or 0)
        tuition_fee_due = float(request.form.get("tuition_fee_due") or 0)
        management_fee_due = float(request.form.get("management_fee_due") or 0)
        exam_fee_due = float(request.form.get("exam_fee_due") or 0)

        if not fee_branch:
            return redirect(url_for("admin_fees", msg="Branch is required for fee setup"))
        if semester_no is None or semester_no < 1 or semester_no > 6:
            return redirect(url_for("admin_fees", msg="Semester must be between 1 and 6"))

        db = get_db()
        cur = db.cursor(dictionary=True)
        cur.execute("""
            INSERT INTO fee_structure_master (
                branch,
                semester_no,
                academic_year,
                admission_fee_due,
                tuition_fee_due,
                management_fee_due,
                exam_fee_due
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
                admission_fee_due=VALUES(admission_fee_due),
                tuition_fee_due=VALUES(tuition_fee_due),
                management_fee_due=VALUES(management_fee_due),
                exam_fee_due=VALUES(exam_fee_due)
        """, (
            fee_branch,
            semester_no,
            academic_year,
            admission_fee_due,
            tuition_fee_due,
            management_fee_due,
            exam_fee_due
        ))

        db.commit()
        cur.close()
        db.close()
        return redirect(url_for("admin_fees", msg="Fee structure saved for branch/semester"))

    q = request.args.get("q", "").strip()
    branch = request.args.get("branch", "").strip()
    if scope["is_staff"] and "management" not in (scope.get("department") or "").strip().lower():
        branch = scope["department"]
    sem = request.args.get("sem", "").strip()
    payment_state = request.args.get("payment_state", "").strip().upper()
    sort_by = request.args.get("sort_by", "name").strip()

    students, branches = fetch_fee_overview_rows(
        q=q,
        branch=branch,
        sem=sem,
        payment_state=payment_state,
        sort_by=sort_by,
        forced_department=scope["department"] if (scope["is_staff"] and "management" not in (scope.get("department") or "").strip().lower()) else ""
    )

    return render_template(
        "admin_fees.html",
        students=students,
        branches=branches,
        filters={
            "q": q,
            "branch": branch,
            "sem": sem,
            "payment_state": payment_state,
            "sort_by": sort_by
        },
        default_academic_year=ay,
        is_staff=scope["is_staff"],
        staff_department=scope["department"],
        can_manage_fees=can_manage,
        msg=msg
    )


@app.route("/admin/fees/export")
def admin_fees_export():
    scope = get_access_scope()
    if not scope["allowed"]:
        return redirect("/")

    q = request.args.get("q", "").strip()
    branch = request.args.get("branch", "").strip()
    if scope["is_staff"] and "management" not in (scope.get("department") or "").strip().lower():
        branch = scope["department"]
    sem = request.args.get("sem", "").strip()
    payment_state = request.args.get("payment_state", "").strip().upper()
    sort_by = request.args.get("sort_by", "name").strip()

    rows, _ = fetch_fee_overview_rows(
        q=q,
        branch=branch,
        sem=sem,
        payment_state=payment_state,
        sort_by=sort_by,
        forced_department=scope["department"] if (scope["is_staff"] and "management" not in (scope.get("department") or "").strip().lower()) else ""
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Admission ID",
        "Reg No",
        "Student Name",
        "Branch",
        "Current Sem",
        "Academic Year",
        "Admission Due",
        "Tuition Due",
        "Management Due",
        "Exam Due",
        "Total Due",
        "Admission Paid",
        "Tuition Paid",
        "Management Paid",
        "Exam Paid",
        "Total Paid",
        "Balance",
        "Payment State"
    ])

    for row in rows:
        writer.writerow([
            row.get("admission_id", ""),
            row.get("college_reg_no", ""),
            row.get("student_name", ""),
            row.get("branch", ""),
            row.get("current_sem", ""),
            row.get("academic_year", ""),
            row.get("admission_due_total", 0),
            row.get("tuition_due_total", 0),
            row.get("management_due_total", 0),
            row.get("exam_due_total", 0),
            row.get("total_due", 0),
            row.get("admission_paid", 0),
            row.get("tuition_paid", 0),
            row.get("management_paid", 0),
            row.get("exam_paid", 0),
            row.get("total_paid", 0),
            row.get("balance", 0),
            row.get("payment_state", ""),
        ])

    csv_bytes = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    csv_bytes.seek(0)
    filename = f"fees_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return send_file(
        csv_bytes,
        mimetype="text/csv",
        as_attachment=True,
        download_name=filename
    )


@app.route("/admin/fees/student/<admission_id>")
def admin_fees_student_history(admission_id):
    scope = get_access_scope()
    if not scope["allowed"]:
        return redirect("/")
    if scope["is_staff"] and not student_in_department(admission_id, scope["department"]):
        return "Forbidden: You can view only your department students.", 403

    ensure_students_college_reg_no_column()
    ensure_students_admission_year_column()
    ensure_fee_module_tables()

    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT
            s.admission_id,
            s.student_name,
            s.branch,
            s.mobile,
            s.year_sem,
            s.admission_year,
            COALESCE(s.college_reg_no, '') AS college_reg_no
        FROM students s
        WHERE s.admission_id=%s
    """, (admission_id,))
    student = cur.fetchone()

    if not student:
        cur.close()
        db.close()
        return "Student not found", 404

    current_sem = infer_current_sem(student.get("admission_year"), student.get("year_sem"))
    ay = current_academic_year()
    cur.execute("""
        SELECT
            admission_fee_due,
            tuition_fee_due,
            management_fee_due,
            exam_fee_due
        FROM fee_structure_master
        WHERE branch=%s AND semester_no=%s AND academic_year=%s
    """, (student.get("branch"), current_sem, ay))
    structure = cur.fetchone() or {}

    due = {
        "ADMISSION": float(structure.get("admission_fee_due") or 0),
        "TUITION": float(structure.get("tuition_fee_due") or 0),
        "MANAGEMENT": float(structure.get("management_fee_due") or 0),
        "EXAM": float(structure.get("exam_fee_due") or 0),
    }

    cur.execute("""
        SELECT
            fee_type,
            COALESCE(SUM(amount), 0) AS total_amount
        FROM fee_payments
        WHERE admission_id=%s AND academic_year=%s AND semester_no=%s
        GROUP BY fee_type
    """, (admission_id, ay, current_sem))
    paid_rows = cur.fetchall()
    paid = {"ADMISSION": 0, "TUITION": 0, "MANAGEMENT": 0, "EXAM": 0}
    for pr in paid_rows:
        paid[pr["fee_type"]] = float(pr.get("total_amount") or 0)

    summary = fee_summary_from_row(student, due=due, paid=paid)

    cur.execute("""
        SELECT
            id,
            admission_id,
            fee_type,
            academic_year,
            semester_no,
            amount,
            payment_date,
            receipt_no,
            remarks
        FROM fee_payments
        WHERE admission_id=%s
        ORDER BY payment_date DESC, id DESC
    """, (admission_id,))
    payments = cur.fetchall()

    cur.close()
    db.close()

    return render_template(
        "admin_fee_history.html",
        student=summary,
        payments=payments,
        default_academic_year=ay,
        current_sem=current_sem,
        today_iso=datetime.today().strftime("%Y-%m-%d"),
        can_manage_fees=can_edit_fees(scope),
        msg=request.args.get("msg", "")
    )


@app.route("/admin/fees/student/<admission_id>/add-payment", methods=["POST"])
def admin_fees_add_payment(admission_id):
    scope = get_access_scope()
    if not scope["allowed"]:
        return redirect("/")
    if not can_edit_fees(scope):
        return "Forbidden: Only Admin, HOD, or Management staff can add/edit fee details.", 403
    if scope["is_staff"] and "management" not in (scope.get("department") or "").strip().lower() and not student_in_department(admission_id, scope["department"]):
        return "Forbidden: You can add payment only for your department students.", 403

    ensure_fee_module_tables()

    fee_type = request.form.get("fee_type", "").strip().upper()
    if fee_type not in {"ADMISSION", "TUITION", "MANAGEMENT", "EXAM"}:
        return redirect(url_for("admin_fees_student_history", admission_id=admission_id, msg="Invalid fee type"))

    amount = float(request.form.get("amount") or 0)
    if amount <= 0:
        return redirect(url_for("admin_fees_student_history", admission_id=admission_id, msg="Amount must be greater than 0"))

    academic_year = request.form.get("academic_year", "").strip() or current_academic_year()
    semester_raw = request.form.get("semester_no", "").strip()
    semester_no = parse_int_prefix(semester_raw)
    if semester_no is None:
        cur_date = datetime.today().date()
        db_tmp = get_db()
        cur_tmp = db_tmp.cursor(dictionary=True)
        cur_tmp.execute("SELECT admission_year, year_sem FROM students WHERE admission_id=%s", (admission_id,))
        sem_src = cur_tmp.fetchone() or {}
        cur_tmp.close()
        db_tmp.close()
        semester_no = infer_current_sem(sem_src.get("admission_year"), sem_src.get("year_sem"), today=cur_date)
    semester_no = min(max(semester_no, 1), 6)

    payment_date = request.form.get("payment_date", "").strip() or datetime.today().strftime("%Y-%m-%d")
    remarks = request.form.get("remarks", "").strip()

    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT admission_id FROM students WHERE admission_id=%s", (admission_id,))
    student = cur.fetchone()
    if not student:
        cur.close()
        db.close()
        return redirect(url_for("admin_fees", msg="Student not found"))

    receipt_no = f"SVP-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(100, 999)}"
    cur.execute("""
        INSERT INTO fee_payments (
            admission_id,
            fee_type,
            academic_year,
            semester_no,
            amount,
            payment_date,
            receipt_no,
            remarks
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        admission_id,
        fee_type,
        academic_year,
        semester_no,
        amount,
        payment_date,
        receipt_no,
        remarks
    ))
    db.commit()
    cur.close()
    db.close()
    return redirect(url_for("admin_fees_student_history", admission_id=admission_id, msg="Payment recorded successfully"))


@app.route("/admin/fees/payment/<int:payment_id>/receipt")
def admin_fees_payment_receipt(payment_id):
    scope = get_access_scope()
    if not scope["allowed"]:
        return redirect("/")

    ensure_fee_module_tables()

    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT
            fp.*,
            s.student_name,
            s.branch
        FROM fee_payments fp
        JOIN students s ON s.admission_id = fp.admission_id
        WHERE fp.id=%s
    """, (payment_id,))
    payment = cur.fetchone()
    cur.close()
    db.close()

    if not payment:
        return "Payment not found", 404
    if scope["is_staff"] and (payment.get("branch") or "").strip().lower() != (scope["department"] or "").strip().lower():
        return "Forbidden: You can access only your department receipts.", 403

    receipt_path = generate_fee_receipt(
        {
            "admission_id": payment["admission_id"],
            "student_name": payment["student_name"],
            "branch": payment["branch"],
        },
        {
            "admission_fee": payment["amount"] if payment["fee_type"] == "ADMISSION" else 0,
            "tuition_fee": payment["amount"] if payment["fee_type"] == "TUITION" else 0,
            "management_fee": payment["amount"] if payment["fee_type"] == "MANAGEMENT" else 0,
            "exam_fee": payment["amount"] if payment["fee_type"] == "EXAM" else 0,
            "payment_type": payment["fee_type"],
            "payment_status": payment["fee_type"],
            "receipt_no": payment["receipt_no"],
            "payment_date": payment["payment_date"],
            "academic_year": payment.get("academic_year"),
            "semester_no": payment.get("semester_no"),
        }
    )
    return send_file(
        receipt_path,
        as_attachment=True,
        download_name=f"receipt_{payment['receipt_no']}.pdf"
    )


# =========================
# STUDENT DASHBOARD
# =========================
@app.route("/student")
def student_dashboard():
    if "student" not in session:
        return redirect("/")

    admission_id = session["student"]

    db = get_db()
    cur = db.cursor(dictionary=True)

    cur.execute("SELECT * FROM students WHERE admission_id=%s", (admission_id,))
    student = cur.fetchone()

    cur.execute("SELECT * FROM education_details WHERE admission_id=%s", (admission_id,))
    education = cur.fetchone()

    cur.execute("SELECT * FROM fees WHERE admission_id=%s", (admission_id,))
    fees = cur.fetchone()

    return render_template(
        "student_dashboard.html",
        student=student,
        education=education,
        fees=fees
    )


# =========================
# PDF: ADMISSION LETTER
# =========================
@app.route("/student/admission-letter")
def admission_letter():
    if "student" not in session:
        return redirect("/")

    admission_id = session["student"]
    db = get_db()
    cur = db.cursor(dictionary=True)

    cur.execute("SELECT * FROM students WHERE admission_id=%s", (admission_id,))
    student = cur.fetchone()

    pdf = generate_admission_letter(student)
    return send_file(pdf, as_attachment=True)


# =========================
# PDF: FEE RECEIPT
# =========================
@app.route("/student/fee-receipt")
def fee_receipt():
    if "student" not in session:
        return redirect("/")

    admission_id = session["student"]
    db = get_db()
    cur = db.cursor(dictionary=True)

    cur.execute("SELECT * FROM students WHERE admission_id=%s", (admission_id,))
    student = cur.fetchone()

    cur.execute("SELECT * FROM fees WHERE admission_id=%s", (admission_id,))
    fees = cur.fetchone()

    pdf = generate_fee_receipt(student, fees)
    return send_file(pdf, as_attachment=True)


@app.route("/student/fees/payment/<int:payment_id>/receipt")
def student_fee_payment_receipt(payment_id):
    if "student" not in session:
        return redirect("/")

    admission_id = session["student"]
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT
            fp.*,
            s.student_name,
            s.branch
        FROM fee_payments fp
        JOIN students s ON s.admission_id = fp.admission_id
        WHERE fp.id=%s AND fp.admission_id=%s
    """, (payment_id, admission_id))
    payment = cur.fetchone()
    cur.close()
    db.close()

    if not payment:
        return "Payment not found", 404

    receipt_path = generate_fee_receipt(
        {
            "admission_id": payment["admission_id"],
            "student_name": payment["student_name"],
            "branch": payment["branch"],
        },
        {
            "admission_fee": payment["amount"] if payment["fee_type"] == "ADMISSION" else 0,
            "tuition_fee": payment["amount"] if payment["fee_type"] == "TUITION" else 0,
            "management_fee": payment["amount"] if payment["fee_type"] == "MANAGEMENT" else 0,
            "exam_fee": payment["amount"] if payment["fee_type"] == "EXAM" else 0,
            "payment_type": payment["fee_type"],
            "payment_status": payment["fee_type"],
            "receipt_no": payment["receipt_no"],
            "payment_date": payment["payment_date"],
            "academic_year": payment.get("academic_year"),
            "semester_no": payment.get("semester_no"),
        }
    )
    return send_file(
        receipt_path,
        as_attachment=True,
        download_name=f"receipt_{payment['receipt_no']}.pdf"
    )


@app.route("/admin/student/<admission_id>")
def admin_view_student(admission_id):
    scope = get_access_scope()
    if not scope["allowed"]:
        return redirect("/")
    if scope["is_staff"] and not student_in_department(admission_id, scope["department"]):
        return "Forbidden: You can view only your department students.", 403

    db = get_db()
    cur = db.cursor(dictionary=True)

    cur.execute("SELECT * FROM students WHERE admission_id=%s", (admission_id,))
    student = cur.fetchone()

    cur.execute("""
        SELECT * FROM student_personal_details
        WHERE admission_id=%s
    """, (admission_id,))
    personal = cur.fetchone()

    cur.execute("""
        SELECT *
        FROM student_documents
        WHERE admission_id=%s
    """, (admission_id,))
    documents = cur.fetchone()

    cur.close()
    db.close()

    # Support both new uploads table and legacy personal-details file columns.
    docs = {
        "student_photo": (documents or {}).get("student_photo") or (personal or {}).get("photo_file"),
        "aadhaar_file": (documents or {}).get("aadhaar_file") or (personal or {}).get("aadhaar_file"),
        "caste_file": (documents or {}).get("caste_file") or (personal or {}).get("caste_certificate_file"),
        "income_file": (documents or {}).get("income_file") or (personal or {}).get("income_certificate_file"),
        "marks_card_file": (documents or {}).get("marks_card_file") or (personal or {}).get("marks_card_file"),
        "aadhaar_number": (documents or {}).get("aadhaar_number") or (personal or {}).get("aadhaar_number"),
        "caste_rd_number": (documents or {}).get("caste_rd_number") or (personal or {}).get("caste_rd_number"),
        "income_rd_number": (documents or {}).get("income_rd_number") or (personal or {}).get("income_rd_number"),
    }
    docs = infer_uploaded_doc_files(admission_id, docs)

    return render_template(
        "admin_view_student.html",
        student=student,
        personal=personal,
        docs=docs,
        print_date=datetime.today().strftime("%d-%m-%Y")
    )


@app.route("/admin/student/<admission_id>/upload-docs", methods=["POST"])
def admin_upload_student_docs(admission_id):
    scope = get_access_scope()
    if not scope["allowed"]:
        return redirect("/")
    if scope["is_staff"] and not student_in_department(admission_id, scope["department"]):
        return "Forbidden: You can upload documents only for your department students.", 403

    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT admission_id FROM students WHERE admission_id=%s", (admission_id,))
    if not cur.fetchone():
        cur.close()
        db.close()
        return "Student not found", 404

    def save_admin_doc(file_obj, prefix):
        if not file_obj or file_obj.filename == "":
            return None
        if not allowed_file(file_obj.filename):
            return "INVALID_FILE"
        filename = f"{admission_id}_{prefix}_{secure_filename(file_obj.filename)}"
        file_obj.save(os.path.join(UPLOAD_FOLDER, filename))
        return filename

    photo_name = save_admin_doc(request.files.get("student_photo"), "photo")
    aadhaar_name = save_admin_doc(request.files.get("aadhaar_file"), "aadhaar")
    caste_name = save_admin_doc(request.files.get("caste_file"), "caste")
    income_name = save_admin_doc(request.files.get("income_file"), "income")
    marks_name = save_admin_doc(request.files.get("marks_card_file"), "marks")

    if "INVALID_FILE" in [photo_name, aadhaar_name, caste_name, income_name, marks_name]:
        cur.close()
        db.close()
        return "Invalid file type. Allowed: pdf, jpg, jpeg, png", 400

    cur.execute("SELECT id FROM student_documents WHERE admission_id=%s", (admission_id,))
    existing = cur.fetchone()
    write_cur = db.cursor()

    if existing:
        write_cur.execute("""
            UPDATE student_documents
            SET student_photo=COALESCE(%s, student_photo),
                aadhaar_file=COALESCE(%s, aadhaar_file),
                caste_file=COALESCE(%s, caste_file),
                income_file=COALESCE(%s, income_file),
                marks_card_file=COALESCE(%s, marks_card_file)
            WHERE admission_id=%s
        """, (photo_name, aadhaar_name, caste_name, income_name, marks_name, admission_id))
    else:
        write_cur.execute("""
            INSERT INTO student_documents
            (admission_id, student_photo, aadhaar_file, caste_file, income_file, marks_card_file)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (admission_id, photo_name, aadhaar_name, caste_name, income_name, marks_name))

    db.commit()
    write_cur.close()
    cur.close()
    db.close()
    return redirect(url_for("admin_view_student", admission_id=admission_id))

import zipfile
from io import BytesIO

import os
import zipfile
from flask import send_file
@app.route("/admin/download-all/<admission_id>")
def download_all_docs(admission_id):
    scope = get_access_scope()
    if not scope["allowed"]:
        return redirect("/")
    if scope["is_staff"] and not student_in_department(admission_id, scope["department"]):
        return "Forbidden: You can download only your department students documents.", 403

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT 
            COALESCE(sd.student_photo, spd.photo_file) AS student_photo,
            COALESCE(sd.aadhaar_file, spd.aadhaar_file) AS aadhaar_file,
            COALESCE(sd.caste_file, spd.caste_certificate_file) AS caste_file,
            COALESCE(sd.income_file, spd.income_certificate_file) AS income_file,
            COALESCE(sd.marks_card_file, spd.marks_card_file) AS marks_card_file
        FROM students s
        LEFT JOIN student_documents sd ON sd.admission_id = s.admission_id
        LEFT JOIN student_personal_details spd ON spd.admission_id = s.admission_id
        WHERE s.admission_id = %s
        """,
        (admission_id,)
    )
    data = cursor.fetchone()

    cursor.close()
    conn.close()

    docs = {
        "student_photo": (data or {}).get("student_photo"),
        "aadhaar_file": (data or {}).get("aadhaar_file"),
        "caste_file": (data or {}).get("caste_file"),
        "income_file": (data or {}).get("income_file"),
        "marks_card_file": (data or {}).get("marks_card_file"),
    }
    docs = infer_uploaded_doc_files(admission_id, docs)

    if not any(docs.values()):
        return "No documents found for this admission ID", 404

    zip_path = f"static/uploads/{admission_id}_documents.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for filename in docs.values():
            if filename:
                file_path = os.path.join("static/uploads", filename)
                if os.path.exists(file_path):
                    z.write(file_path, filename)

    return send_file(zip_path, as_attachment=True)
# imports
import os
import random
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ✅ save_file MUST be here
def save_file(file, prefix, admission_id):
    if not file or file.filename == "":
        return None

    filename = secure_filename(file.filename)
    ext = filename.rsplit(".", 1)[-1]

    unique_name = f"{admission_id}_{prefix}_{random.randint(100000,999999)}.{ext}"
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_name)

    file.save(file_path)
    return unique_name


# ✅ THEN your upload route


@app.route("/admission/upload-documents", methods=["POST"])
def upload_documents():

    # 1️⃣ admission id
    admission_id = request.form.get("admission_id")

    # 2️⃣ save files
    photo = save_file(request.files.get("student_photo"), "photo", admission_id)
    aadhaar = save_file(request.files.get("aadhaar_file"), "aadhaar", admission_id)
    caste = save_file(request.files.get("caste_file"), "caste", admission_id)
    income = save_file(request.files.get("income_file"), "income", admission_id)
    marks = save_file(request.files.get("marks_card_file"), "marks", admission_id)

    # 3️⃣ student_documents table
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT id FROM student_documents WHERE admission_id=%s",
        (admission_id,)
    )
    row = cursor.fetchone()

    if row:
        cursor.execute("""
            UPDATE student_documents SET
                student_photo=%s,
                aadhaar_file=%s,
                caste_file=%s,
                income_file=%s,
                marks_card_file=%s
            WHERE admission_id=%s
        """, (photo, aadhaar, caste, income, marks, admission_id))
    else:
        cursor.execute("""
            INSERT INTO student_documents
            (admission_id, student_photo, aadhaar_file, caste_file, income_file, marks_card_file)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (admission_id, photo, aadhaar, caste, income, marks))

    conn.commit()
    cursor.close()
    conn.close()

    # 4️⃣ get admission data from session
    admission = session.get("admission")
    if not admission:
        return redirect("/admission/step-1")

    # 5️⃣ students table (login)
    db = get_db()
    cur = db.cursor()

    cur.execute(
        "SELECT admission_id FROM students WHERE admission_id=%s",
        (admission_id,)
    )

    if not cur.fetchone():
        cur.execute("""
            INSERT INTO students
            (admission_id, student_name, branch, mobile, password_hash, status)
            VALUES (%s,%s,%s,%s,%s,'INACTIVE')
        """, (
            admission_id,
            admission["student_name"],
            admission["branch"],
            admission["student_mobile"],
            generate_password_hash(admission["password"])

        ))

    db.commit()
    cur.close()
    db.close()

    # 🔥🔥🔥 ADD YOUR CODE HERE 🔥🔥🔥
    # ===============================
    # INSERT PERSONAL DETAILS (STEP 1 + 2)
    # ===============================
    db = get_db()
    cur = db.cursor()

    cur.execute(
        "SELECT id FROM student_personal_details WHERE admission_id=%s",
        (admission_id,)
    )

    if not cur.fetchone():
        cur.execute("""
            INSERT INTO student_personal_details (
                admission_id,
                dob, gender, indian_nationality, religion,
                caste_category, alloted_category,
                qualifying_exam, year_of_passing, register_number,
                admission_quota,
                father_name, father_mobile,
                mother_name, mother_mobile,
                residential_address, permanent_address
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            admission_id,
            admission["dob"],
            admission["gender"],
            admission["indian_nationality"],
            admission["religion"],
            admission["caste_category"],
            admission["alloted_category"],
            admission["qualifying_exam"],
            admission["year_of_passing"],
            admission["register_number"],
            admission["admission_quota"],
            admission["father_name"],
            admission["father_mobile"],
            admission["mother_name"],
            admission["mother_mobile"],
            admission["residential_address"],
            admission["permanent_address"]
        ))

    db.commit()
    cur.close()
    db.close()

    # 6️⃣ clear session & show success
    session.pop("admission", None)

    return render_template(
        "admission_success.html",
        admission_id=admission_id
    )


@app.route("/student/reupload", methods=["GET", "POST"])
def student_reupload():
    if "student" not in session:
        return redirect("/login")

    admission_id = session["student"]

    if request.method == "POST":

        photo = request.files.get("photo")
        marks = request.files.get("marks_card")
        caste = request.files.get("caste_certificate")
        income = request.files.get("income_certificate")

        def save_file(file, prefix):
            if file and file.filename:
                if not allowed_file(file.filename):
                    return None, "❌ Invalid file type"
                name = f"{admission_id}_{prefix}_{secure_filename(file.filename)}"
                file.save(os.path.join(UPLOAD_FOLDER, name))
                return name, None
            return None, None

        photo_name, err = save_file(photo, "photo")
        if err: return err

        marks_name, err = save_file(marks, "marks")
        if err: return err

        caste_name, err = save_file(caste, "caste")
        if err: return err

        income_name, err = save_file(income, "income")
        if err: return err

        db = get_db()
        cur = db.cursor()

        # 🔁 UPDATE ONLY UPLOADED FILES
        if photo_name:
            cur.execute(
                "UPDATE student_personal_details SET photo_file=%s WHERE admission_id=%s",
                (photo_name, admission_id)
            )
        if marks_name:
            cur.execute(
                "UPDATE student_personal_details SET marks_card_file=%s WHERE admission_id=%s",
                (marks_name, admission_id)
            )
        if caste_name:
            cur.execute(
                "UPDATE student_personal_details SET caste_certificate_file=%s WHERE admission_id=%s",
                (caste_name, admission_id)
            )
        if income_name:
            cur.execute(
                "UPDATE student_personal_details SET income_certificate_file=%s WHERE admission_id=%s",
                (income_name, admission_id)
            )

        # 🔁 RESET STATUS FOR REVIEW
        cur.execute("""
            UPDATE students
            SET status='INACTIVE', rejection_reason=NULL
            WHERE admission_id=%s
        """, (admission_id,))

        db.commit()

        return """
        <h3>✅ Documents Re-uploaded Successfully</h3>
        <p>Your application is sent back for admin review.</p>
        <a href="/login">Back to Login</a>
        """

    return render_template("student_reupload.html")

# =========================
# RUN SERVER
# =========================
if __name__ == "__main__":
    app.run(debug=True)


