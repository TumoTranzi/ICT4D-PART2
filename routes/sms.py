"""Inbound SMS webhook for citizens replying with a report reference."""
from datetime import datetime
import hmac
import os
import re

from flask import Blueprint, current_app, request

from sms_gateway import normalize_phone

sms_bp = Blueprint("sms", __name__)
REFERENCE_MESSAGE = re.compile(r"^(TSE-[A-Z0-9]{4})\s+(.+)$", re.IGNORECASE | re.DOTALL)


def _plain(message, status=200):
    return message, status, {"Content-Type": "text/plain; charset=utf-8"}


@sms_bp.route("/api/sms/inbound", methods=["POST"])
def sms_inbound():
    token = os.environ.get("SMS_INBOUND_TOKEN", "")
    supplied = request.args.get("token", "") or request.form.get("token", "")
    if not token or not supplied or not hmac.compare_digest(token, supplied):
        return _plain("Not authorised", 403)

    phone = normalize_phone(request.form.get("from", ""))
    text = request.form.get("text", "").strip()
    match = REFERENCE_MESSAGE.fullmatch(text)
    if not phone or not match:
        return _plain("Send your report reference followed by your message, e.g. TSE-AB12 Please update me.")

    reference, message = match.group(1).upper(), match.group(2).strip()
    if not message or len(message) > 1000:
        return _plain("Message must contain 1 to 1,000 characters.")

    store = current_app.extensions["tsebisa_store"]
    report = store.get_report(reference, ("reference", "phone"))
    if not report:
        return _plain("We could not find that report reference.")
    stored_phone = normalize_phone(report.get("phone", ""))
    if not stored_phone or not hmac.compare_digest(stored_phone, phone):
        return _plain("The phone number does not match that report.")

    store.add_message({
        "report_ref": reference,
        "sender_role": "citizen",
        "sender_name": "Citizen (SMS)",
        "message": message,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
    return _plain("Your reply has been added to the Tsebisa report conversation.")
