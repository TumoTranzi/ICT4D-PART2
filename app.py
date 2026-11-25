"""
Tsebisa – Community Service Delivery Reporting System
DIIC3110 ICT4D Group Project (Pilot Prototype)
"""

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
from routes.ussd import ussd_bp
from storage import create_store, DuplicateUserError
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
    return store

def init_db():
    store.initialize()

    default_users = (
        ("partner", os.environ.get("TSEBISA_PARTNER_PASSWORD") or (None if IS_PRODUCTION else "partner123"), "partner", "Minister"),
        ("admin", os.environ.get("TSEBISA_ADMIN_PASSWORD") or (None if IS_PRODUCTION else "admin123"), "admin", "Prime Minister"),
    )
    for username, password, role, display_name in default_users:
        if not password:
            continue
        if not store.get_user(username):
            store.create_user({"username": username, "password_hash": generate_password_hash(password),
                               "role": role, "display_name": display_name})
    for username, label, old_label in (("admin", "Prime Minister", "System Administrator"), ("partner", "Minister", "Community Partner")):
        user = store.get_user(username)
        if user and user.get("display_name") == old_label:
            store.update_user_display_name(username, label)


STORAGE_BACKEND = os.environ.get("TSEBISA_STORAGE_BACKEND", "sqlite").strip().lower()
store = create_store(STORAGE_BACKEND, DB_PATH, os.environ.get("DATABASE_URL"))
app.extensions["tsebisa_store"] = store

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
        user = store.get_user(username)
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

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        for _ in range(10):
            ref = generate_reference()
            saved = store.create_report({
                "reference": ref, "submission_channel": "Website", "category": category,
                "description": description, "location": location, "phone": phone,
                "language": lang, "status": "received", "created_at": now,
                "voice_note": voice_filename, "photo": photo_filename,
            })
            if saved:
                break
        else:
            raise RuntimeError("Could not create a unique report reference")

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
    channel_filter = request.args.get("channel", "all")
    if channel_filter.lower() not in ("all", "website", "ussd"):
        channel_filter = "all"
    category_filter = request.args.get("category", "all")
    if category_filter not in CATEGORIES:
        category_filter = "all"
    month_filter = request.args.get("month", "")
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month_filter):
        month_filter = ""
    conversation_filter = request.args.get("conversation") == "1"
    all_reports = store.list_reports()
    all_messages = store.list_messages()
    conversation_counts = {}
    for message in all_messages:
        ref = message["report_ref"]
        conversation_counts[ref] = conversation_counts.get(ref, 0) + 1

    rows = [row for row in all_reports if
            (status_filter == "all" or row.get("status") == status_filter) and
            (channel_filter == "all" or (row.get("submission_channel") or "Website").lower() == channel_filter.lower()) and
            (category_filter == "all" or row.get("category") == category_filter) and
            (not month_filter or (row.get("created_at") or "").startswith(month_filter)) and
            (not conversation_filter or conversation_counts.get(row.get("reference"), 0) > 0)]

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

    for row in all_messages:
        month = (row.get("created_at") or "")[:7]
        if month and row.get("sender_role") in ("citizen", "partner", "admin"):
            month_message_counts[month] = month_message_counts.get(month, 0) + 1
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
        {"label": "Total reports", "value": len(all_reports), "note": "Open the complete report list", "href": url_for("dashboard", _anchor="report-list"), "points": sparkline_points(month_counts.get(key, 0) for key in spark_months)},
        {"label": "Conversation replies", "value": message_total, "note": "Open reports with conversations", "href": url_for("dashboard", conversation="1", _anchor="report-list"), "points": sparkline_points(month_message_counts.get(key, 0) for key in spark_months)},
        {"label": "Website submissions", "value": channel_counts.get("Website", 0), "note": "Open website reports", "href": url_for("dashboard", channel="website", _anchor="report-list"), "points": sparkline_points(month_website_counts.get(key, 0) for key in spark_months)},
        {"label": "USSD submissions", "value": channel_counts.get("USSD", 0), "note": "Open USSD reports", "href": url_for("dashboard", channel="ussd", _anchor="report-list"), "points": sparkline_points(month_ussd_counts.get(key, 0) for key in spark_months)},
    ]

    return render_template(
        "dashboard.html", reports=rows, categories=CATEGORIES,
        status_labels=STATUS_LABELS, current_filter=status_filter,
        total_reports=len(all_reports), conversation_counts=conversation_counts,
        status_chart=status_chart, category_chart=category_chart,
        channel_chart=channel_chart, month_chart=month_chart,
        card_series=card_series, axis_ticks=axis_ticks,
        latest_report_id=max((int(row.get("id") or 0) for row in all_reports), default=0),
        channel_filter=channel_filter, category_filter=category_filter,
        month_filter=month_filter, conversation_filter=conversation_filter,
    )

@app.route("/dashboard/update/<reference>", methods=["POST"])
@role_required("partner", "admin")
def update_status(reference):
    new_status = request.form.get("status")
    current_filter = normalize_status_filter(request.form.get("current_filter") or request.args.get("status") or "all")
    if new_status in STATUS_LABELS:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        previous_status = store.update_report_status(reference, new_status, now)
        if previous_status is not None:
            if previous_status != new_status:
                label = STATUS_LABELS[new_status]["en"]
                store.add_message({"report_ref": reference, "sender_role": "system", "sender_name": "Tsebisa status update",
                                   "message": f"Report status changed to: {label}.", "created_at": now})
        flash(f"Report {reference} updated to {new_status}", "success")
    return redirect(url_for("dashboard", status=current_filter))

@app.route("/dashboard/report/<reference>")
@role_required("partner", "admin")
def view_report(reference):
    current_filter = normalize_status_filter(request.args.get("status", "all"))
    report = store.get_report(reference)
    message_count = len(store.list_messages(reference))
    if not report:
        return "Report not found", 404
    return render_template("report_view.html", report=report, categories=CATEGORIES, status_labels=STATUS_LABELS, current_filter=current_filter, message_count=message_count)


@app.route("/conversation", methods=["GET"])
def conversation_lookup():
    reference = request.args.get("reference", "").strip().upper()
    report = None
    messages = []
    if reference:
        report = store.get_report(reference, ("reference", "category", "description", "location", "status", "created_at"))
        if report and can_view_conversation(reference):
            messages = store.list_messages(reference)
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
    report = store.get_report(reference, ("reference", "phone"))
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
    exists = store.get_report(reference, ("reference",))
    if not exists:
        return "Report not found", 404
    store.add_message({"report_ref": reference, "sender_role": sender_role, "sender_name": sender_name,
                       "message": message, "created_at": now})
    return redirect(url_for("conversation_lookup", reference=reference))


@app.route("/api/conversation/<reference>")
def conversation_messages_api(reference):
    reference = reference.strip().upper()
    if not can_view_conversation(reference):
        return jsonify({"error": "Verify the report reference and phone number to view this conversation."}), 403
    exists = store.get_report(reference, ("reference",))
    if not exists:
        return jsonify({"error": "Report not found."}), 404
    rows = store.list_messages(reference)
    return jsonify([{key: row.get(key) for key in ("sender_role", "sender_name", "message", "created_at")} for row in rows])

@app.route("/api/reports")
@role_required("partner", "admin")
def api_reports():
    try:
        after_id = max(0, int(request.args.get("after_id", "0")))
    except ValueError:
        after_id = 0
    rows = [row for row in store.list_reports(limit=100) if int(row.get("id") or 0) > after_id]
    fields = ("id", "reference", "submission_channel", "category", "location", "status", "created_at")
    payload = []
    for row in rows:
        item = {key: row.get(key) for key in fields}
        item["category_label"] = CATEGORIES.get(row.get("category"), {}).get("en", row.get("category", "Report"))
        payload.append(item)
    return jsonify(payload)


@app.route("/admin", methods=["GET", "POST"])
@role_required("admin")
def admin_panel():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "create":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            role = request.form.get("role", "")
            display_name = request.form.get("display_name", "").strip()
            if username and password and role in ROLES and role != "citizen":
                try:
                    store.create_user({"username": username, "password_hash": generate_password_hash(password),
                                       "role": role, "display_name": display_name or username})
                    flash("Account created.", "success")
                except DuplicateUserError:
                    flash("That username already exists.", "error")
            else:
                flash("Enter a username, password and valid staff role.", "error")
        elif action == "delete":
            user_id = request.form.get("user_id")
            store.delete_user(user_id)
            flash("Account deleted.", "success")

    users = store.list_users()
    report_count = store.count_reports()
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
