"""Interactive USSD reporting callback for Africa's Talking style gateways."""

from datetime import datetime
import re
import secrets

from flask import Blueprint, current_app, request

ussd_bp = Blueprint("ussd", __name__)

CATEGORY_OPTIONS = {
    "1": ("water", "Metsi / Water"),
    "2": ("roads", "Litsela / Roads"),
    "3": ("refuse", "Lithoele / Refuse"),
    "4": ("lights", "Mabone / Street lights"),
    "5": ("other", "Tse ling / Other"),
}


def reply(message, end=False):
    """Return the plain-text format expected by common USSD gateways."""
    return ("END " if end else "CON ") + message, 200, {"Content-Type": "text/plain; charset=utf-8"}


def prompt_language():
    return "Tsebisa\nKhetha puo / Choose language:\n1. Sesotho\n2. English"


def prompt_category(lang):
    if lang == "st":
        return "Khetha bothata:\n1. Metsi\n2. Litsela\n3. Lithoele\n4. Mabone\n5. Tse ling"
    return "Choose a category:\n1. Water\n2. Roads\n3. Refuse\n4. Street lights\n5. Other"


def prompt_for(lang, sesotho, english):
    return sesotho if lang == "st" else english


def valid_phone(value):
    # Allow common human-entered separators, then store a compact number.
    compact = re.sub(r"[\s()-]", "", value)
    digits = compact[1:] if compact.startswith("+") else compact
    if not digits.isdigit() or not 7 <= len(digits) <= 15:
        return None
    return compact


def save_report(category, description, location, phone, lang):
    store = current_app.extensions["tsebisa_store"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    for _ in range(10):
        reference = "TSE-" + secrets.token_hex(2).upper()
        if store.create_report({
            "reference": reference, "submission_channel": "USSD", "category": category,
            "description": description, "location": location, "phone": phone,
            "language": lang, "status": "received", "created_at": now,
            "voice_note": None, "photo": None,
        }):
            return reference
    raise RuntimeError("Could not create a unique report reference")


@ussd_bp.route("/api/ussd", methods=["POST"])
def ussd_api():
    """Advance a stateless USSD menu using the gateway's accumulated `text`."""
    text = request.values.get("text", "").strip()
    parts = text.split("*") if text else []

    if not parts:
        return reply(prompt_language())

    lang = {"1": "st", "2": "en"}.get(parts[0])
    if lang is None:
        return reply("Kgetho ha e a nepahala. Please dial again.\n" + prompt_language(), end=True)
    if len(parts) == 1:
        return reply(prompt_category(lang))

    choice = parts[1]
    if choice not in CATEGORY_OPTIONS:
        return reply(prompt_for(lang, "Kgetho ha e a nepahala. Letsetsa hape.", "Invalid choice. Please dial again."), end=True)
    category, category_label = CATEGORY_OPTIONS[choice]
    if len(parts) == 2:
        return reply(prompt_for(lang, "Kenya sebaka sa bothata:", "Enter the problem location:"))

    location = parts[2].strip()
    if not location or len(location) > 100:
        return reply(prompt_for(lang, "Sebaka ha sea nepahala. Letsetsa hape.", "Invalid location. Please dial again."), end=True)
    if len(parts) == 3:
        return reply(prompt_for(lang, "Hlalosa bothata:", "Describe the problem:"))

    description = parts[3].strip()
    if not description or len(description) > 240:
        return reply(prompt_for(lang, "Tlhaloso ha e a nepahala. Letsetsa hape.", "Invalid description. Please dial again."), end=True)
    if len(parts) == 4:
        return reply(prompt_for(lang, "Kenya nomoro ya hao ya mohala:", "Enter your phone number:"))

    phone = valid_phone(parts[4].strip())
    if phone is None:
        return reply(prompt_for(lang, "Nomoro ha e a nepahala. Letsetsa hape.", "Invalid phone number. Please dial again."), end=True)
    if len(parts) == 5:
        return reply(prompt_for(
            lang,
            f"Netefatsa tlaleho?\n{category_label}\n{location}\n1. Ee  2. Tjhe",
            f"Confirm report?\n{category_label}\n{location}\n1. Yes  2. No",
        ))

    confirmation = parts[5].strip()
    if confirmation == "2":
        return reply(prompt_for(lang, "Tlaleho e hlakotswe.", "Report cancelled."), end=True)
    if confirmation != "1":
        return reply(prompt_for(lang, "Karabo ha e a nepahala. Letsetsa hape.", "Invalid response. Please dial again."), end=True)

    reference = save_report(category, description, location, phone, lang)
    return reply(prompt_for(
        lang,
        f"Re a leboha. Tlaleho e amohetswe. Nomoro: {reference}",
        f"Thank you. Your report was received. Reference: {reference}",
    ), end=True)
