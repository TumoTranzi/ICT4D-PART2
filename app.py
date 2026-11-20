"""
Tsebisa – Community Service Delivery Reporting System
DIIC3110 ICT4D Group Project (Pilot Prototype)
"""

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
from routes.ussd import ussd_bp
import sqlite3
import os
import random
import string
import re
import secrets
import time
import math

app = Flask(__name__)
IS_PRODUCTION = os.environ.get("TSEBISA_ENV", "development").lower() == "production"
secret_key = os.environ.get("TSEBISA_SECRET_KEY")
if IS_PRODUCTION and not secret_key:
    raise RuntimeError("Set TSEBISA_SECRET_KEY before starting TTsebisa in production.")
if IS_PRODUCTION and not os.environ.get("TSEBISA_ADMIN_PASSWORD"):
    raise RuntimeError("Set TSEBISA_ADMIN_PASSWORD before first production startup.")
app.secret_key = secret_key or "local-only-change-before-hosting"
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=IS_PRODUCTION,
    TEMPLATES_AUTO_RELOAD=not IS_PRODUCTION,
)

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.environ.get("TSEBISA_DATA_DIR", PROJECT_DIR))
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "tsebisa.db")
UPLOAD_ROOT = os.path.join(DATA_DIR, "uploads") if DATA_DIR != PROJECT_DIR else os.path.join(PROJECT_DIR, "static")
VOICE_UPLOAD_FOLDER = os.path.join(UPLOAD_ROOT, "voice_notes")
PHOTO_UPLOAD_FOLDER = os.path.join(UPLOAD_ROOT, "report_photos")
os.makedirs(VOICE_UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PHOTO_UPLOAD_FOLDER, exist_ok=True)
app.config["TSEBISA_DB_PATH"] = DB_PATH
app.config["VOICE_UPLOAD_FOLDER"] = VOICE_UPLOAD_FOLDER
app.config["PHOTO_UPLOAD_FOLDER"] = PHOTO_UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
app.register_blueprint(ussd_bp)

ROLES = ("citizen", "partner", "admin")
ROLE_LABELS = {"citizen": "Citizen", "partner": "Minister", "admin": "Prime Minister"}


def current_role():
    return session.get("role")


def role_required(*allowed_roles):
    def decorator(view):
        @wraps(view)
        def protected(*args, **kwargs):
            role = current_role()
            if role not in allowed_roles:
                flash("Please sign in with an authorised account.", "error")
                return redirect(url_for("login"))
            return view(*args, **kwargs)
        return protected
    return decorator

# -------------------------------------------------
# Database helpers
# -------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reference TEXT UNIQUE NOT NULL,
            submission_channel TEXT DEFAULT 'Website',
            category TEXT NOT NULL,
            description TEXT,
            location TEXT,
            phone TEXT,
            language TEXT DEFAULT 'st',
            status TEXT DEFAULT 'received',
            created_at TEXT NOT NULL,
            updated_at TEXT
        )
    """)
    # Older pilot databases may predate the channel column. Add it in place.
    columns = {row[1] for row in c.execute("PRAGMA table_info(reports)").fetchall()}
    if "submission_channel" not in columns:
        c.execute("ALTER TABLE reports ADD COLUMN submission_channel TEXT DEFAULT 'Website'")
    if "voice_note" not in columns:
        c.execute("ALTER TABLE reports ADD COLUMN voice_note TEXT")
    if "photo" not in columns:
        c.execute("ALTER TABLE reports ADD COLUMN photo TEXT")
    c.execute("""
        CREATE TABLE IF NOT EXISTS feedback_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_ref TEXT,
            note TEXT,
            created_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_ref TEXT NOT NULL,
            sender_role TEXT NOT NULL,
            sender_name TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (report_ref) REFERENCES reports(reference)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_conversations_report_ref ON conversations(report_ref, id)")
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            display_name TEXT
        )
    """)
    # SQLite may have accepted a malformed pilot schema if one existed.
    user_columns = {row[1] for row in c.execute("PRAGMA table_info(users)").fetchall()}
    if "display_name" not in user_columns:
        c.execute("ALTER TABLE users ADD COLUMN display_name TEXT")

    default_users = (
        ("partner", os.environ.get("TSEBISA_PARTNER_PASSWORD") or (None if IS_PRODUCTION else "partner123"), "partner", "Minister"),
        ("admin", os.environ.get("TSEBISA_ADMIN_PASSWORD") or (None if IS_PRODUCTION else "admin123"), "admin", "Prime Minister"),
    )
    c.execute("DELETE FROM users WHERE role=?", ("citizen",))
    for username, password, role, display_name in default_users:
        if not password:
            continue
        if not c.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            c.execute(
                "INSERT INTO users (username, password_hash, role, display_name) VALUES (?, ?, ?, ?)",
                (username, generate_password_hash(password), role, display_name),
            )
    c.execute("UPDATE users SET display_name='Prime Minister' WHERE username='admin' AND display_name='System Administrator'")
    c.execute("UPDATE users SET display_name='Minister' WHERE username='partner' AND display_name='Community Partner'")
    conn.commit()
    conn.close()

def generate_reference():
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"TSE-{code}"


def chat_csrf_token():
    if "chat_csrf_token" not in session:
        session["chat_csrf_token"] = secrets.token_urlsafe(32)
    return session["chat_csrf_token"]


def chat_csrf_valid(value):
    expected = session.get("chat_csrf_token", "")
    return bool(expected and value and secrets.compare_digest(expected, value))


def can_view_conversation(reference):
    if current_role() in ("partner", "admin"):
        return True
    return (
        session.get("citizen_chat_ref") == reference
        and session.get("citizen_chat_until", 0) > time.time()
    )


def report_phone_matches(stored_phone, entered_phone):
    stored_digits = re.sub(r"\D", "", stored_phone or "")
    entered_digits = re.sub(r"\D", "", entered_phone or "")
    return bool(stored_digits and entered_digits and secrets.compare_digest(stored_digits, entered_digits))

# -------------------------------------------------
# Category definitions
# -------------------------------------------------
CATEGORIES = {
    "water": {"st": "Metsi (pompo / pipe e robehileng)", "en": "Water (broken pump / pipe)"},
    "roads": {"st": "Litsela (mekoallo / mekoti)", "en": "Roads (potholes / damage)"},
    "refuse": {"st": "Lithoto (ho bokella)", "en": "Refuse collection"},
    "lights": {"st": "Mabone a seterata", "en": "Street lights"},
    "other": {"st": "Tse ding", "en": "Other"},
}

CATEGORY_ICONS = {
    "water": "drop",
    "roads": "road",
    "refuse": "trash",
    "lights": "bulb",
    "other": "dots",
}

STATUS_LABELS = {
    "received": {"st": "E amohetsoe", "en": "Received"},
    "in_progress": {"st": "E ntse e sebetsoa", "en": "In progress"},
    "closed": {"st": "E koetsoe", "en": "Closed"},
}

# -------------------------------------------------
# Routes
# -------------------------------------------------
@app.route("/")
def home():
    return render_template("home.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username=?",
            (username,),
        ).fetchone()
        conn.close()
        if user and user["role"] in ("partner", "admin") and check_password_hash(user["password_hash"], password):
            session["role"] = user["role"]
            session["username"] = user["username"]
            session["display_name"] = user["display_name"] or user["username"]
            flash(f"Welcome, {session['display_name']}.", "success")
            if user["role"] == "admin":
                return redirect(url_for("admin_panel"))
            if user["role"] == "partner":
                return redirect(url_for("dashboard"))
            return redirect(url_for("home"))
        flash("Incorrect username or password.", "error")
    return render_template("login.html", show_demo_accounts=not IS_PRODUCTION)


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("home"))

@app.route("/report", methods=["GET", "POST"])
def report_start():
    if request.method == "POST":
        session["lang"] = request.form.get("lang", "st")
        if session["lang"] not in ("st", "en"):
            session["lang"] = "st"
        session.pop("category", None)
        return redirect(url_for("report_category"))
    return render_template("report_language.html")

@app.route("/report/category", methods=["GET", "POST"])
def report_category():
    lang = session.get("lang", "st")
    if request.method == "POST":
        category = request.form.get("category")
        if category not in CATEGORIES:
            flash("Choose a problem type.", "error")
            return redirect(url_for("report_category"))
        session["category"] = category
        return redirect(url_for("report_details"))
    return render_template("report_category.html", lang=lang, categories=CATEGORIES, category_icons=CATEGORY_ICONS)

@app.route("/report/details", methods=["GET", "POST"])
def report_details():
    lang = session.get("lang", "st")
    category = session.get("category")
    if not category:
        return redirect(url_for("report_start"))

    if request.method == "POST":
        description = request.form.get("description", "").strip()
        location = request.form.get("location", "").strip()
        phone = request.form.get("phone", "").strip()
        voice_note = request.files.get("voice_note")
        photo = request.files.get("photo")

        if category not in CATEGORIES:
            session.pop("category", None)
            return redirect(url_for("report_category"))

        compact_phone = re.sub(r"[\s()-]", "", phone)
        digits = compact_phone[1:] if compact_phone.startswith("+") else compact_phone
        if not digits.isdigit() or not 7 <= len(digits) <= 15:
            flash("Enter a valid phone number.", "error")
            return redirect(url_for("report_details"))

        voice_filename = None
        if voice_note and voice_note.filename:
            mime_to_extension = {
                "audio/webm": "webm",
                "audio/ogg": "ogg",
                "audio/mp4": "m4a",
                "audio/mpeg": "mp3",
                "audio/wav": "wav",
                "audio/x-wav": "wav",
            }
            extension = mime_to_extension.get(voice_note.mimetype)
            if not extension:
                flash("Please record or upload a supported audio note.", "error")
                return redirect(url_for("report_details"))
            voice_filename = f"voice-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}.{extension}"
            voice_note.save(os.path.join(VOICE_UPLOAD_FOLDER, voice_filename))

        photo_filename = None
        if photo and photo.filename:
            image_to_extension = {
                "image/jpeg": "jpg",
                "image/png": "png",
                "image/webp": "webp",
                "image/heic": "heic",
            }
            extension = image_to_extension.get(photo.mimetype)
            if not extension:
                flash("Please select a JPG, PNG, WebP or HEIC image.", "error")
                return redirect(url_for("report_details"))
            photo_filename = f"photo-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}.{extension}"
            photo.save(os.path.join(PHOTO_UPLOAD_FOLDER, photo_filename))

        if not description and voice_filename:
            description = "[Voice note]"
        elif not description and photo_filename:
            description = "[Photo evidence]"
        if not description and not photo_filename:
            flash("Add a description, voice note or photo.", "error")
            return redirect(url_for("report_details"))

        ref = generate_reference()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        conn = get_db()
        conn.execute(
            "INSERT INTO reports (reference, submission_channel, category, description, location, phone, language, status, created_at, voice_note, photo) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (ref, 'Website', category, description, location, phone, lang, "received", now, voice_filename, photo_filename)
        )
        conn.commit()
        conn.close()

        session.clear()
        return render_template("report_success.html", ref=ref, lang=lang)

    return render_template("report_details.html", lang=lang, category=category, categories=CATEGORIES)

def normalize_status_filter(status_value):
    if status_value in STATUS_LABELS:
        return status_value
    return "all"

@app.route("/dashboard")
@role_required("partner", "admin")
def dashboard():
    status_filter = normalize_status_filter(request.args.get("status", "all"))
    conn = get_db()
    all_reports = conn.execute("SELECT reference, submission_channel, category, status, created_at FROM reports").fetchall()
    if status_filter == "all":
        rows = conn.execute("SELECT * FROM reports ORDER BY created_at DESC").fetchall()
    else:
        rows = conn.execute("SELECT * FROM reports WHERE status=? ORDER BY created_at DESC", (status_filter,)).fetchall()
    message_rows = conn.execute("SELECT report_ref, COUNT(*) AS total FROM conversations GROUP BY report_ref").fetchall()
    conversation_counts = {row["report_ref"]: row["total"] for row in message_rows}
    conn.close()

    status_counts = {key: 0 for key in STATUS_LABELS}
    category_counts = {key: 0 for key in CATEGORIES}
    channel_counts = {"Website": 0, "USSD": 0}
    month_counts = {}
    month_website_counts = {}
    month_ussd_counts = {}
    month_message_counts = {}
    for row in all_reports:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
        category_counts[row["category"]] = category_counts.get(row["category"], 0) + 1
        channel = row["submission_channel"] or "Website"
        channel_counts[channel] = channel_counts.get(channel, 0) + 1
        month = (row["created_at"] or "")[:7]
        if month:
            month_counts[month] = month_counts.get(month, 0) + 1
            target = month_ussd_counts if channel.lower() == "ussd" else month_website_counts
            target[month] = target.get(month, 0) + 1

    conn = get_db()
    reply_month_rows = conn.execute(
        "SELECT substr(created_at, 1, 7) AS month, COUNT(*) AS total "
        "FROM conversations WHERE sender_role IN ('citizen', 'partner', 'admin') GROUP BY month"
    ).fetchall()
    conn.close()
    for row in reply_month_rows:
        if row["month"]:
            month_message_counts[row["month"]] = row["total"]
    message_total = sum(month_message_counts.values())

    status_max = max(status_counts.values(), default=0) or 1
    category_max = max(category_counts.values(), default=0) or 1
    channel_max = max(channel_counts.values(), default=0) or 1
    status_chart = [
        {"label": STATUS_LABELS[key]["en"], "count": value, "width": round(value / status_max * 100), "color": color}
        for key, value, color in (("received", status_counts.get("received", 0), "#c99a21"), ("in_progress", status_counts.get("in_progress", 0), "#2365a8"), ("closed", status_counts.get("closed", 0), "#20804c"))
    ]
    category_chart = [
        {"label": CATEGORIES[key]["en"], "count": category_counts.get(key, 0), "width": round(category_counts.get(key, 0) / category_max * 100)}
        for key in CATEGORIES
    ]
    channel_chart = [
        {"label": key, "count": value, "width": round(value / channel_max * 100)}
        for key, value in channel_counts.items()
    ]
    now = datetime.now()
    current_month = datetime(now.year, now.month, 1)
    first_month = min(month_counts) if month_counts else current_month.strftime("%Y-%m")
    start_year, start_month = map(int, first_month.split("-"))
    cursor = datetime(start_year, start_month, 1)
    chart_months = []
    while cursor <= current_month:
        chart_months.append(cursor)
        next_month = cursor.month + 1
        cursor = datetime(cursor.year + (next_month - 1) // 12, (next_month - 1) % 12 + 1, 1)
    # Keep the all-time view readable while preserving up to three years of history.
    chart_months = chart_months[-36:]
    all_months = [month.strftime("%Y-%m") for month in chart_months]
    chart_max = max((month_counts.get(key, 0) for key in all_months), default=0)
    chart_axis_max = max(4, int(math.ceil(chart_max / 4) * 4))
    month_chart = []
    for index, month in enumerate(chart_months):
        key = month.strftime("%Y-%m")
        month_chart.append({
            "key": key,
            "label": month.strftime("%b"),
            "year": month.strftime("%y"),
            "count": month_counts.get(key, 0),
            "height": max(0, round(month_counts.get(key, 0) / chart_axis_max * 100)),
            "index": index,
        })
    axis_ticks = [chart_axis_max, round(chart_axis_max * .75), round(chart_axis_max * .5), round(chart_axis_max * .25), 0]

    def sparkline_points(values):
        values = list(values)[-6:]
        values = [0] * (6 - len(values)) + values
        peak = max(values) or 1
        return " ".join(f"{4 + i * 18.4:.1f},{27 - value / peak * 22:.1f}" for i, value in enumerate(values))

    spark_months = all_months[-6:]
    card_series = [
        {"label": "Total reports", "value": len(all_reports), "note": "Reports across both channels", "points": sparkline_points(month_counts.get(key, 0) for key in spark_months)},
        {"label": "Conversation replies", "value": message_total, "note": "Citizen and staff messages", "points": sparkline_points(month_message_counts.get(key, 0) for key in spark_months)},
        {"label": "Website submissions", "value": channel_counts.get("Website", 0), "note": "Reports created through the website", "points": sparkline_points(month_website_counts.get(key, 0) for key in spark_months)},
        {"label": "USSD submissions", "value": channel_counts.get("USSD", 0), "note": "Includes browser USSD demonstrations", "points": sparkline_points(month_ussd_counts.get(key, 0) for key in spark_months)},
    ]

    return render_template(
        "dashboard.html", reports=rows, categories=CATEGORIES,
        status_labels=STATUS_LABELS, current_filter=status_filter,
        total_reports=len(all_reports), conversation_counts=conversation_counts,
        status_chart=status_chart, category_chart=category_chart,
        channel_chart=channel_chart, month_chart=month_chart,
        card_series=card_series, axis_ticks=axis_ticks,
    )

@app.route("/dashboard/update/<reference>", methods=["POST"])
@role_required("partner", "admin")
def update_status(reference):
    new_status = request.form.get("status")
    current_filter = normalize_status_filter(request.form.get("current_filter") or request.args.get("status") or "all")
    if new_status in STATUS_LABELS:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        conn = get_db()
        report = conn.execute("SELECT status FROM reports WHERE reference=?", (reference,)).fetchone()
        if report:
            conn.execute("UPDATE reports SET status=?, updated_at=? WHERE reference=?", (new_status, now, reference))
            if report["status"] != new_status:
                label = STATUS_LABELS[new_status]["en"]
                conn.execute(
                    "INSERT INTO conversations (report_ref, sender_role, sender_name, message, created_at) VALUES (?, 'system', 'Tsebisa status update', ?, ?)",
                    (reference, f"Report status changed to: {label}.", now),
                )
            conn.commit()
        conn.close()
        flash(f"Report {reference} updated to {new_status}", "success")
    return redirect(url_for("dashboard", status=current_filter))

@app.route("/dashboard/report/<reference>")
@role_required("partner", "admin")
def view_report(reference):
    current_filter = normalize_status_filter(request.args.get("status", "all"))
    conn = get_db()
    report = conn.execute("SELECT * FROM reports WHERE reference=?", (reference,)).fetchone()
    message_count = conn.execute("SELECT COUNT(*) FROM conversations WHERE report_ref=?", (reference,)).fetchone()[0]
    conn.close()
    if not report:
        return "Report not found", 404
    return render_template("report_view.html", report=report, categories=CATEGORIES, status_labels=STATUS_LABELS, current_filter=current_filter, message_count=message_count)


@app.route("/conversation", methods=["GET"])
def conversation_lookup():
    reference = request.args.get("reference", "").strip().upper()
    report = None
    messages = []
    if reference:
        conn = get_db()
        report = conn.execute("SELECT reference, category, description, location, status, created_at FROM reports WHERE reference=?", (reference,)).fetchone()
        conn.close()
        if report and can_view_conversation(reference):
            conn = get_db()
            messages = conn.execute("SELECT sender_role, sender_name, message, created_at FROM conversations WHERE report_ref=? ORDER BY id", (reference,)).fetchall()
            conn.close()
    return render_template(
        "conversation.html", reference=reference, report=report, messages=messages,
        authenticated=bool(report and can_view_conversation(reference)), csrf_token=chat_csrf_token(),
        role_labels=ROLE_LABELS, categories=CATEGORIES, status_labels=STATUS_LABELS,
    )


@app.route("/conversation/access", methods=["POST"])
def conversation_access():
    reference = request.form.get("reference", "").strip().upper()
    phone = request.form.get("phone", "").strip()
    if not chat_csrf_valid(request.form.get("csrf_token")):
        flash("Please refresh the page and try again.", "error")
        return redirect(url_for("conversation_lookup", reference=reference))
    conn = get_db()
    report = conn.execute("SELECT reference, phone FROM reports WHERE reference=?", (reference,)).fetchone()
    conn.close()
    if not report or not report_phone_matches(report["phone"], phone):
        flash("We could not verify that report reference and phone number.", "error")
        return redirect(url_for("conversation_lookup", reference=reference))
    session["citizen_chat_ref"] = reference
    session["citizen_chat_until"] = time.time() + 1800
    return redirect(url_for("conversation_lookup", reference=reference))


@app.route("/conversation/<reference>/reply", methods=["POST"])
def conversation_reply(reference):
    reference = reference.strip().upper()
    if not can_view_conversation(reference):
        flash("Verify the report reference and phone number before replying.", "error")
        return redirect(url_for("conversation_lookup", reference=reference))
    if not chat_csrf_valid(request.form.get("csrf_token")):
        flash("Please refresh the page and try again.", "error")
        return redirect(url_for("conversation_lookup", reference=reference))
    message = request.form.get("message", "").strip()
    if not message or len(message) > 1000:
        flash("Enter a message up to 1,000 characters.", "error")
        return redirect(url_for("conversation_lookup", reference=reference))
    role = current_role()
    if role in ("partner", "admin"):
        sender_role = role
        sender_name = session.get("display_name") or ROLE_LABELS[role]
    else:
        sender_role = "citizen"
        sender_name = "Citizen"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = get_db()
    exists = conn.execute("SELECT 1 FROM reports WHERE reference=?", (reference,)).fetchone()
    if not exists:
        conn.close()
        return "Report not found", 404
    conn.execute(
        "INSERT INTO conversations (report_ref, sender_role, sender_name, message, created_at) VALUES (?, ?, ?, ?, ?)",
        (reference, sender_role, sender_name, message, now),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("conversation_lookup", reference=reference))


@app.route("/api/conversation/<reference>")
def conversation_messages_api(reference):
    reference = reference.strip().upper()
    if not can_view_conversation(reference):
        return jsonify({"error": "Verify the report reference and phone number to view this conversation."}), 403
    conn = get_db()
    exists = conn.execute("SELECT 1 FROM reports WHERE reference=?", (reference,)).fetchone()
    if not exists:
        conn.close()
        return jsonify({"error": "Report not found."}), 404
    rows = conn.execute("SELECT sender_role, sender_name, message, created_at FROM conversations WHERE report_ref=? ORDER BY id", (reference,)).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])

@app.route("/api/reports")
@role_required("partner", "admin")
def api_reports():
    conn = get_db()
    rows = conn.execute("SELECT reference, submission_channel, category, status, created_at FROM reports ORDER BY created_at DESC LIMIT 50").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/admin", methods=["GET", "POST"])
@role_required("admin")
def admin_panel():
    conn = get_db()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "create":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            role = request.form.get("role", "")
            display_name = request.form.get("display_name", "").strip()
            if username and password and role in ROLES and role != "citizen":
                try:
                    conn.execute(
                        "INSERT INTO users (username, password_hash, role, display_name) VALUES (?, ?, ?, ?)",
                        (username, generate_password_hash(password), role, display_name or username),
                    )
                    conn.commit()
                    flash("Account created.", "success")
                except sqlite3.IntegrityError:
                    flash("That username already exists.", "error")
            else:
                flash("Enter a username, password and valid staff role.", "error")
        elif action == "delete":
            user_id = request.form.get("user_id")
            conn.execute(
                "DELETE FROM users WHERE id=? AND username<>? AND role<>?",
                (user_id, "admin", "admin"),
            )
            conn.commit()
            flash("Account deleted.", "success")

    users = conn.execute(
        "SELECT id, username, role, display_name FROM users ORDER BY role, username"
    ).fetchall()
    report_count = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
    conn.close()
    return render_template(
        "admin.html",
        users=users,
        report_count=report_count,
        roles=ROLES,
        role_labels=ROLE_LABELS,
    )

@app.route("/guide")
def guide():
    return render_template("guide.html")

@app.route("/voice-notes/<path:filename>")
@role_required("partner", "admin")
def voice_note(filename):
    return send_from_directory(app.config["VOICE_UPLOAD_FOLDER"], filename)

@app.route("/report-photos/<path:filename>")
@role_required("partner", "admin")
def report_photo(filename):
    return send_from_directory(app.config["PHOTO_UPLOAD_FOLDER"], filename)

@app.route("/ussd-simulator")
def ussd_simulator():
    """Browser-based feature-phone simulator for the USSD callback."""
    return render_template("ussd_simulator.html")

# -------------------------------------------------
# Startup
# -------------------------------------------------
init_db()

if __name__ == "__main__":
    print("=" * 50)
    print("Tsebisa Pilot Server starting...")
    print("=" * 50)
    
    port = int(os.environ.get("PORT", 5002))
    app.run(debug=False, host="0.0.0.0", port=port)
