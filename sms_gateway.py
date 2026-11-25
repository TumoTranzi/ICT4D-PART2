"""Africa's Talking SMS gateway integration (outbound + inbound helper)."""
from __future__ import annotations

import json
import logging
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


def normalize_phone(value: str) -> str:
    """Normalize Lesotho local numbers and international E.164-style numbers."""
    raw = (value or "").strip()
    digits = "".join(char for char in raw if char.isdigit())
    if raw.startswith("+"):
        return "+" + digits
    if raw.startswith("00"):
        return "+" + digits[2:]
    if digits.startswith("266"):
        return "+" + digits
    if len(digits) == 8:
        return "+266" + digits
    return digits


def send_sms(phone: str, message: str) -> dict:
    """Submit SMS to Africa's Talking; accepted does not mean handset-delivered."""
    api_key = os.environ.get("AT_API_KEY", "").strip()
    configured_username = os.environ.get("AT_USERNAME", "").strip()
    environment = os.environ.get("AT_SMS_ENVIRONMENT", "sandbox").strip().lower()
    if not api_key or not configured_username:
        return {"status": "not_configured", "accepted": False, "message": "SMS gateway is not configured."}

    recipient = normalize_phone(phone)
    if not recipient.startswith("+") or not recipient[1:].isdigit() or not 7 <= len(recipient[1:]) <= 15:
        return {"status": "invalid_phone", "accepted": False, "message": "Recipient number must include its country code, for example +266..."}

    username = "sandbox" if environment == "sandbox" else configured_username
    base_url = "https://api.sandbox.africastalking.com" if environment == "sandbox" else "https://api.africastalking.com"
    fields = {"username": username, "to": recipient, "message": message}
    sender_id = os.environ.get("AT_SENDER_ID", "").strip()
    if sender_id:
        fields["from"] = sender_id
    request = Request(
        f"{base_url}/version1/messaging",
        data=urlencode(fields).encode("utf-8"),
        headers={"apiKey": api_key, "Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
        recipients = payload.get("SMSMessageData", {}).get("Recipients", [])
        result = recipients[0] if recipients else {}
        code = int(result.get("statusCode", 500))
        accepted = code in (100, 101, 102)
        return {
            "status": "accepted" if accepted else "rejected",
            "accepted": accepted,
            "message_id": result.get("messageId"),
            "gateway_status": result.get("status"),
            "status_code": code,
            "message": payload.get("SMSMessageData", {}).get("Message", ""),
        }
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        logger.warning("Africa's Talking rejected SMS (HTTP %s): %s", exc.code, detail)
        return {"status": "failed", "accepted": False, "message": "Gateway rejected the SMS request."}
    except (URLError, TimeoutError, ValueError, KeyError) as exc:
        logger.warning("Africa's Talking SMS request failed: %s", exc)
        return {"status": "failed", "accepted": False, "message": "Could not reach the SMS gateway."}


def send_report_confirmation(phone: str, reference: str, language: str = "en") -> dict:
    if language == "st":
        body = f"Tsebisa: Tlaleho ya hao e amohetswe. Nomoro ya referense: {reference}. Boloka nomoro ena bakeng sa ho botsa ka tlaleho ya hao."
    else:
        body = f"Tsebisa: Your service report was received. Reference: {reference}. Keep this number to ask about your report."
    return send_sms(phone, body)
