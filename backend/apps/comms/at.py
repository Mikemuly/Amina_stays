"""Thin Africa's Talking REST client (SMS, Voice, Airtime, Mobile Data, Insights SIM-swap, WhatsApp).

We call the REST endpoints directly rather than the Python SDK: the SDK no longer ships Payments,
its Voice.call drops clientRequestId and its Airtime client leaks Idempotency-Key headers between calls.
With no API key configured every call is a dry run, so the whole system works offline for demos.
"""

import json
import logging

import httpx
from django.conf import settings

from apps.core.utils import normalize_phone

log = logging.getLogger("amina.at")


class ATError(Exception):
    pass


def configured():
    return bool(settings.AT_API_KEY)


def _url(live, sandbox=None):
    if settings.AT_SANDBOX:
        if not sandbox:
            raise ATError("This Africa's Talking product has no sandbox — use live credentials")
        return sandbox
    return live


def _post(url, *, data=None, json_body=None, headers=None):
    h = {"apiKey": settings.AT_API_KEY, "Accept": "application/json", **(headers or {})}
    try:
        with httpx.Client(timeout=settings.AT_HTTP_TIMEOUT) as client:
            r = client.post(url, data=data, json=json_body, headers=h)
    except httpx.HTTPError as e:
        raise ATError(f"network error: {e}") from e
    try:
        body = r.json()
    except ValueError:
        body = {"raw": r.text[:500]}
    if r.status_code >= 400:
        raise ATError(f"HTTP {r.status_code}: {str(body)[:300]}")
    return body


# ---------- SMS ----------


def send_sms(to, message, sender_id=None):
    """Bulk SMS (legacy form endpoint — the only one with a sandbox).
    Returns {"recipients": [{number, status, statusCode, messageId, cost}], "dry_run": bool}."""
    if not configured():
        log.info("[dry-run SMS] -> %s: %s", to, message)
        return {"dry_run": True, "recipients": []}
    data = {"username": settings.AT_USERNAME, "to": to, "message": message, "bulkSMSMode": 1}
    # AT's default sender only reaches Airtel numbers in Kenya: without an approved sender ID, send from the
    # two-way shortcode (which also lets guests reply to "Ask Amina")
    sender = sender_id or settings.AT_SENDER_ID or settings.AT_SMS_NUMBER
    if sender:
        data["from"] = sender
    body = _post(
        _url(
            "https://api.africastalking.com/version1/messaging",
            "https://api.sandbox.africastalking.com/version1/messaging",
        ),
        data=data,
    )
    sms = body.get("SMSMessageData", {}) if isinstance(body, dict) else {}
    return {"dry_run": False, "recipients": sms.get("Recipients", []), "message": sms.get("Message", "")}


# ---------- Voice (no sandbox) ----------


def voice_call(to, client_request_id=""):
    if not configured() or not settings.AT_VOICE_NUMBER:
        log.info("[dry-run CALL] -> %s (%s)", to, client_request_id)
        return {"dry_run": True, "entries": [{"phoneNumber": to, "status": "NotConfigured"}]}
    numbers = to.split(",") if isinstance(to, str) else to
    callees = ",".join(p for p in (normalize_phone(n) for n in numbers) if p)  # AT only dials +E.164 numbers
    if not callees:
        raise ATError(f"no valid phone number to call: {to!r}")
    data = {
        "username": settings.AT_USERNAME,
        "from": normalize_phone(settings.AT_VOICE_NUMBER) or settings.AT_VOICE_NUMBER,
        "to": callees,
    }
    if client_request_id:
        data["clientRequestId"] = client_request_id
    return _post("https://voice.africastalking.com/call", data=data)


# ---------- Airtime ----------


def send_airtime(phone, amount_kes, idempotency_key, metadata=None):
    """Always send a unique Idempotency-Key: AT rejects 'similar' airtime requests within 5 minutes otherwise."""
    if not configured():
        log.info("[dry-run AIRTIME] KES %s -> %s", amount_kes, phone)
        return {"dry_run": True, "numSent": 0}
    data = {
        "username": settings.AT_USERNAME,
        "recipients": json.dumps([{"phoneNumber": phone, "amount": f"KES {int(amount_kes)}"}]),
        "maxNumRetry": 2,
    }
    if metadata:
        data["requestMetadata"] = json.dumps(metadata)
    return _post(
        _url(
            "https://api.africastalking.com/version1/airtime/send",
            "https://api.sandbox.africastalking.com/version1/airtime/send",
        ),
        data=data,
        headers={"Idempotency-Key": idempotency_key},
    )


# ---------- Mobile Data (welcome bundle for guests) ----------


def send_mobile_data(phone, megabytes, metadata=None, idempotency_key=""):
    if not configured() or not settings.AT_DATA_PRODUCT:
        log.info("[dry-run DATA] %sMB -> %s", megabytes, phone)
        return {"dry_run": True}
    body = {
        "username": settings.AT_USERNAME,
        "productName": settings.AT_DATA_PRODUCT,
        "recipients": [
            {
                "phoneNumber": phone,
                "quantity": int(megabytes),
                "unit": "MB",
                "validity": "Week",
                "metadata": metadata or {},
            }
        ],
    }
    headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
    return _post(
        _url(
            "https://bundles.africastalking.com/mobile/data/request",
            "https://bundles.sandbox.africastalking.com/mobile/data/request",
        ),
        json_body=body,
        headers=headers,
    )


# ---------- Insights: SIM swap ----------


def sim_swap_check(phones):
    """Async: AT answers per number with Queued/Swapped/NoSwapDate…, then posts the result to the Insights callback."""
    if not configured():
        return {"dry_run": True}
    return _post(
        _url(
            "https://insights.africastalking.com/v1/sim-swap", "https://insights.sandbox.africastalking.com/v1/sim-swap"
        ),
        json_body={"username": settings.AT_USERNAME, "phoneNumbers": list(phones)},
    )


# ---------- WhatsApp (AT Chat, preview) ----------


def send_whatsapp(phone, text):
    if not configured() or not settings.AT_WHATSAPP_NUMBER:
        log.info("[dry-run WHATSAPP] -> %s: %s", phone, text)
        return {"dry_run": True}
    return _post(
        _url("https://chat.africastalking.com/whatsapp/message/send"),
        json_body={
            "username": settings.AT_USERNAME,
            "waNumber": settings.AT_WHATSAPP_NUMBER,
            "phoneNumber": phone,
            "body": {"message": text},
        },
    )


def balance():
    if not configured():
        return None
    try:
        with httpx.Client(timeout=settings.AT_HTTP_TIMEOUT) as client:
            r = client.get(
                _url(
                    "https://api.africastalking.com/version1/user",
                    "https://api.sandbox.africastalking.com/version1/user",
                ),
                params={"username": settings.AT_USERNAME},
                headers={"apiKey": settings.AT_API_KEY, "Accept": "application/json"},
            )
        data = r.json()
        return (data.get("UserData") or data.get("userData") or {}).get("balance")  # AT's docs show both spellings
    except Exception:  # status panel only
        return None
