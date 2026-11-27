"""Payment providers. Each takes a pending Payment and starts collection; results arrive by callback.

M-Pesa:  off (default: guests pay by card) | simulate (auto-succeeds, for demos)
         | daraja (Safaricom Daraja STK push, the production path once Safaricom's Go-Live is done)
         | africastalking (AT Mobile Checkout — now onboarding-gated, kept for accounts that have it)
Card:    simulate (hosted test page, no card data) | stripe (Stripe Checkout; picked as soon as STRIPE_SECRET_KEY is
         set) | paystack (hosted checkout; webhook HMAC-verified, then confirmed with Verify Transaction)
Card numbers never touch this server: guests are always sent to a hosted page.
"""

import base64
import hashlib
import hmac
import logging
import os
import re
import secrets
import threading
import time
from urllib.parse import urlsplit

import httpx
from django.conf import settings
from django.core.cache import cache
from django.db import close_old_connections
from django.utils import timezone

from apps.core.utils import today

log = logging.getLogger("amina.payments")

TOKEN_KEY = "daraja_token"
# Safaricom: "Do not use public URL testers e.g. ngrok ... especially on production ... usually blocked by the API"
TUNNEL_HOSTS = ("ngrok", "trycloudflare", "requestbin", "mockbin")
SETUP_FAILED = "We couldn't start the M-Pesa payment - Amina has been alerted. Please try again later or pay by card."


class PaymentError(Exception):
    """A payment that couldn't start. failure_code is the M-Pesa result code when there is one; suggest is the
    next step for the guest (retry | card | deposit | wait | paybill)."""

    def __init__(self, message="", *, failure_code=None, suggest=None):
        super().__init__(message)
        self.failure_code = failure_code or None
        self.suggest = suggest or None

    def as_dict(self):
        return {"error": str(self), "failure_code": self.failure_code, "suggest": self.suggest}


class DarajaSetupError(PaymentError):
    """Daraja refused us because of how M-Pesa is set up here (keys, shortcode, passkey), not anything the guest did."""


def _callback_base():
    return settings.PUBLIC_URL.rstrip("/")


def callback_secret():
    """The path secret Daraja calls back on, for the M-Pesa prompt (STK) callback and the Paybill (C2B) ones alike:
    DARAJA_CALLBACK_SECRET, else AT_WEBHOOK_SECRET, else the placeholder "cb"."""
    return (
        getattr(settings, "DARAJA_CALLBACK_SECRET", "")
        or os.environ.get("DARAJA_CALLBACK_SECRET", "")
        or settings.AT_WEBHOOK_SECRET
        or "cb"
    )


def tunnel_host(url):
    """A tunnel or public URL tester (ngrok, trycloudflare, ...): fine for a sandbox demo, blocked by Safaricom live."""
    host = urlsplit(url).hostname or ""
    return any(name in host for name in TUNNEL_HOSTS)


def setup_alert(booking, detail):
    """Tell Amina (once a day) that M-Pesa payments fail because Daraja is misconfigured."""
    from apps.safety.services import raise_alert

    raise_alert(
        "payment",
        f"Daraja is misconfigured, so M-Pesa payments are failing ({detail}). Check the DARAJA_* settings: env, "
        "shortcode, passkey, consumer key and secret, transaction type and PartyB.",
        severity="high",
        booking=booking,
        dedupe=f"daraja-setup:{today()}",
    )


# ---------- M-Pesa ----------


class SimulatedMpesa:
    name, simulated = "simulate", True

    def request(self, payment):
        delay = settings.SIM_PAY_DELAY_SECONDS
        if delay > 0:
            timer = threading.Timer(delay, _simulate_success, args=(payment.pk,))
            timer.daemon = True
            timer.start()
        return {"status": "pending", "message": f"Simulated STK push to {payment.phone}"}

    def query(self, payment):
        return None


def _simulate_success(payment_id):
    from .services import on_success

    try:
        from .models import Payment

        p = Payment.objects.filter(pk=payment_id, status="pending").first()
        if p:
            on_success(
                p,
                transaction_id=f"SIM{secrets.token_hex(4).upper()}",
                provider_ref=f"SIM{secrets.token_hex(4).upper()}",
            )
    except Exception:
        log.exception("simulated payment failed")
    finally:
        close_old_connections()


class DarajaMpesa:
    """Safaricom Daraja Lipa na M-Pesa Online (STK push)."""

    name, simulated = "daraja", False

    @property
    def base(self):
        return (
            "https://api.safaricom.co.ke" if settings.DARAJA_ENV == "production" else "https://sandbox.safaricom.co.ke"
        )

    def _token(self):
        token = cache.get(TOKEN_KEY)
        if token:
            return token
        if not (settings.DARAJA_CONSUMER_KEY and settings.DARAJA_CONSUMER_SECRET):
            raise DarajaSetupError("Daraja credentials are not configured")
        with httpx.Client(timeout=15) as c:
            r = c.get(
                f"{self.base}/oauth/v1/generate",
                params={"grant_type": "client_credentials"},
                auth=(settings.DARAJA_CONSUMER_KEY, settings.DARAJA_CONSUMER_SECRET),
            )
        if r.status_code != 200:
            error = DarajaSetupError if r.status_code in (400, 401, 403) else PaymentError
            raise error(f"Daraja auth failed (HTTP {r.status_code})")
        data = r.json()
        cache.set(TOKEN_KEY, data["access_token"], int(data.get("expires_in", 3599)) - 60)
        return data["access_token"]

    def _post(self, path, body, timeout=20):
        """POST with the cached token. Each new token invalidates the previous one, so a token another process has
        replaced comes back as HTTP 401 or 404.001.03 "Invalid Access Token": drop it and try once more."""
        for last_try in (False, True):
            with httpx.Client(timeout=timeout) as c:
                r = c.post(f"{self.base}{path}", json=body, headers={"Authorization": f"Bearer {self._token()}"})
            if last_try or not _stale_token(r):
                return r
            cache.delete(TOKEN_KEY)

    def _password(self):
        ts = timezone.localtime().strftime("%Y%m%d%H%M%S")  # Kenya time on any server
        raw = f"{settings.DARAJA_SHORTCODE}{settings.DARAJA_PASSKEY}{ts}"
        return base64.b64encode(raw.encode()).decode(), ts

    def request(self, payment):
        password, ts = self._password()
        body = {
            "BusinessShortCode": settings.DARAJA_SHORTCODE,
            "Password": password,
            "Timestamp": ts,
            "TransactionType": settings.DARAJA_TRANSACTION_TYPE,
            "Amount": int(payment.amount),
            "PartyA": payment.phone.lstrip("+"),
            "PartyB": settings.DARAJA_PARTY_B or settings.DARAJA_SHORTCODE,
            "PhoneNumber": payment.phone.lstrip("+"),
            "CallBackURL": f"{_callback_base()}/api/payments/daraja/callback/{callback_secret()}",
            "AccountReference": payment.booking.ref[:12],
            "TransactionDesc": "Amina Stays",
        }
        try:
            r = self._post("/mpesa/stkpush/v1/processrequest", body)
            if r.status_code in (401, 403):  # refused even with a fresh token: the keys or the Daraja app are wrong
                raise DarajaSetupError(f"HTTP {r.status_code} from the STK push API")
            data = r.json()
        except DarajaSetupError as e:
            setup_alert(payment.booking, str(e))
            raise PaymentError(SETUP_FAILED) from e
        except (httpx.HTTPError, ValueError) as e:
            raise PaymentError(f"M-Pesa is unreachable ({e})") from e
        payment.raw = [*payment.raw, {"request": data}]
        if str(data.get("ResponseCode")) != "0":
            raise _rejected(payment, data)
        payment.transaction_id = data["CheckoutRequestID"]
        payment.save(update_fields=["transaction_id", "raw"])
        return {"status": "pending", "message": data.get("CustomerMessage", "")}

    def query(self, payment):
        password, ts = self._password()
        try:
            r = self._post(
                "/mpesa/stkpushquery/v1/query",
                {
                    "BusinessShortCode": settings.DARAJA_SHORTCODE,
                    "Password": password,
                    "Timestamp": ts,
                    "CheckoutRequestID": payment.transaction_id,
                },
                timeout=15,
            )
            return r.json()
        except Exception as e:
            log.warning("Daraja query failed: %s", e)
            return None


def _stale_token(r):
    if r.status_code == 401:
        return True
    try:
        return str(r.json().get("errorCode") or "") == "404.001.03"
    except (ValueError, AttributeError):
        return False


BUSY_PHONE = re.compile(r"lock subscriber|already in process", re.IGNORECASE)
GUEST_FIELDS = re.compile(r"amount|phone|partya", re.IGNORECASE)


def _rejected(payment, data):
    """The PaymentError for a push Daraja turned down, e.g. {"errorCode": "500.001.1001", "errorMessage": ...}.
    500.001.1001 is also "Merchant does not exist" and "Wrong credentials", so only "Unable to lock subscriber, a
    transaction is already in process" means another prompt is open on the phone. Errors about our setup (the access
    token, 500.001.1001, a bad request field other than the guest's amount or number) give the guest a plain message
    and alert Amina."""
    message = data.get("errorMessage") or data.get("ResponseDescription") or "STK push rejected"
    error = str(data.get("errorCode") or "")
    code = error.rsplit(".", 1)[-1]
    if code == "1001" and BUSY_PHONE.search(message):
        return PaymentError(message, failure_code="1001")
    if code in ("1025", "1037"):
        return PaymentError(message, failure_code=code)
    if error.startswith(("404.001.", "500.001.1001")) or (
        error.startswith("400.002.") and not GUEST_FIELDS.search(message)
    ):
        setup_alert(payment.booking, f"{error} {message}")
        return PaymentError(SETUP_FAILED)
    return PaymentError(message)


class ATMobileCheckout:
    """Africa's Talking Mobile Checkout (legacy; activated per account on request)."""

    name, simulated = "africastalking", False

    def request(self, payment):
        url = "https://payments.africastalking.com/mobile/checkout/request"
        body = {
            "username": settings.AT_USERNAME,
            "productName": settings.AT_PAYMENT_PRODUCT,
            "phoneNumber": payment.phone,
            "currencyCode": "KES",
            "amount": int(payment.amount),
            "metadata": {"ref": payment.booking.ref, "paymentId": str(payment.pk)},
        }
        try:
            with httpx.Client(timeout=20) as c:
                r = c.post(url, json=body, headers={"apiKey": settings.AT_API_KEY, "Accept": "application/json"})
            data = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise PaymentError(f"Payment service unreachable ({e})") from e
        payment.raw = [*payment.raw, {"request": data}]
        if data.get("status") != "PendingConfirmation":
            payment.save(update_fields=["raw"])
            raise PaymentError(data.get("description") or data.get("errorMessage") or str(data.get("status")))
        payment.transaction_id = data.get("transactionId")
        payment.save(update_fields=["transaction_id", "raw"])
        return {"status": "pending", "message": data.get("description", "")}

    def query(self, payment):
        return None


# ---------- cards ----------


class SimulatedCard:
    name, simulated = "simulate", True

    def request(self, payment):
        payment.checkout_token = secrets.token_hex(16)
        payment.save(update_fields=["checkout_token"])
        return {"status": "pending", "checkout_url": f"{settings.FRONTEND_URL}/pay/card/{payment.checkout_token}"}

    def query(self, payment):
        return None


class PaystackCard:
    name, simulated = "paystack", False

    def request(self, payment):
        if not settings.PAYSTACK_SECRET_KEY:
            raise PaymentError("Card payments are not configured")
        payment.checkout_token = secrets.token_hex(16)
        guest = payment.booking.guest
        email = guest.email or f"guest{payment.phone.lstrip('+')}@aminastays.co.ke"
        body = {
            "email": email,
            "amount": int(payment.amount) * 100,
            "currency": "KES",
            "reference": payment.checkout_token,
            "callback_url": f"{settings.FRONTEND_URL}/trips/{payment.booking.ref}?paid=1",
            "metadata": {"ref": payment.booking.ref, "payment_id": payment.pk},
        }
        try:
            with httpx.Client(timeout=20) as c:
                r = c.post(
                    "https://api.paystack.co/transaction/initialize",
                    json=body,
                    headers={"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"},
                )
            data = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise PaymentError(f"Card service unreachable ({e})") from e
        if not data.get("status"):
            raise PaymentError(data.get("message", "Card checkout failed"))
        payment.raw = [*payment.raw, {"request": data}]
        payment.save(update_fields=["checkout_token", "raw"])
        return {"status": "pending", "checkout_url": data["data"]["authorization_url"]}

    def query(self, payment):
        """Paystack Verify Transaction: the transaction as Paystack sees it ({"status": true, "data": {...}}),
        or None when it can't be asked."""
        if not settings.PAYSTACK_SECRET_KEY or not payment.checkout_token:
            return None
        try:
            with httpx.Client(timeout=15) as c:
                r = c.get(
                    f"https://api.paystack.co/transaction/verify/{payment.checkout_token}",
                    headers={"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"},
                )
            return r.json()
        except (httpx.HTTPError, ValueError) as e:
            log.warning("Paystack verify failed: %s", e)
            return None


# ---------- Stripe ----------

STRIPE_EVENTS = (
    "checkout.session.completed",
    "checkout.session.async_payment_succeeded",
    "checkout.session.async_payment_failed",
    "checkout.session.expired",
)
STRIPE_TOLERANCE = 300  # seconds, as in Stripe's own libraries: an older signature is a replay
STRIPE_LOCALES = {"en": "en", "it": "it", "de": "de", "fr": "fr"}  # no Kiswahili in Checkout: the browser decides
HELD_SESSION_SECONDS = 31 * 60  # Stripe's minimum is 30 minutes; a hold paid late is handled like any late payment
OPEN_SESSION_SECONDS = 23 * 3600  # balances and changes: a day to pay (Stripe's maximum is 24 hours)


def stripe_signature_ok(payload, header, secret, now=None):
    """The Stripe-Signature check from docs.stripe.com/webhooks ("Verify webhook signatures manually"): an HMAC-SHA256
    of "<t>.<raw body>" with the endpoint's signing secret must equal one of the v1 entries, and t must be under
    5 minutes old. Every other entry (v0, and the secret/destination/payload debug metadata) is ignored, in any order."""
    if not (secret and header):
        return False
    timestamp, signatures = "", []
    for item in str(header).split(","):
        key, _, value = item.strip().partition("=")
        if key == "t":
            timestamp = value
        elif key == "v1":
            signatures.append(value)
    if not re.fullmatch(r"[0-9]{1,12}", timestamp) or not signatures:
        return False
    body = payload if isinstance(payload, bytes) else str(payload).encode()
    expected = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest().encode()
    if not any(hmac.compare_digest(expected, s.encode()) for s in signatures):
        return False
    return int(timestamp) >= (time.time() if now is None else now) - STRIPE_TOLERANCE


def stripe_session_id(payment):
    """The Checkout Session a Stripe payment opened (kept in payment.raw: its id is longer than our token field)."""
    for entry in reversed(payment.raw or []):
        session = (entry.get("request") or {}).get("session")
        if session:
            return session
    return None


def stripe_test_mode():
    return settings.STRIPE_SECRET_KEY.startswith(("sk_test_", "rk_test_"))


class StripeCard:
    """Stripe Checkout, Stripe's hosted payment page. Stripe sends the guest back to /pay/card/<token>, which asks
    Stripe how the session ended; the webhook and the scheduler settle it as well, so a payment counts even if the
    guest never comes back. Amounts are KES in cents (KES is a two-decimal currency at Stripe)."""

    name, simulated = "stripe", False

    def _call(self, method, path, data=None, *, idempotency_key=None):
        if not settings.STRIPE_SECRET_KEY:
            raise PaymentError("Card payments are not configured")
        headers = {"Authorization": f"Bearer {settings.STRIPE_SECRET_KEY}"}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        try:
            with httpx.Client(timeout=20) as c:
                r = c.request(method, f"{settings.STRIPE_API_BASE}/v1/{path}", data=data, headers=headers)
            body = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise PaymentError(f"Card service unreachable ({e})") from e
        if r.status_code >= 400 or not isinstance(body, dict) or "error" in body:
            error = body.get("error") if isinstance(body, dict) else None
            message = (error or {}).get("message") if isinstance(error, dict) else None
            raise PaymentError(message or f"Stripe answered HTTP {r.status_code}")
        return body

    def request(self, payment):
        b = payment.booking
        payment.checkout_token = secrets.token_hex(16)
        page = f"{settings.FRONTEND_URL.rstrip('/')}/pay/card/{payment.checkout_token}"
        seconds = HELD_SESSION_SECONDS if b.status == "held" else OPEN_SESSION_SECONDS
        data = {
            "mode": "payment",
            "client_reference_id": payment.checkout_token,
            "success_url": f"{page}?session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": f"{page}?cancelled=1",
            "expires_at": str(int(time.time()) + seconds),
            "locale": STRIPE_LOCALES.get(b.lang, "auto"),
            "line_items[0][quantity]": "1",
            "line_items[0][price_data][currency]": "kes",
            "line_items[0][price_data][unit_amount]": str(int(payment.amount) * 100),
            "line_items[0][price_data][product_data][name]": f"{b.unit.name} ({b.ref})",
            "line_items[0][price_data][product_data][description]": (
                f"{payment.get_purpose_display()}: {b.check_in:%d %b} - {b.check_out:%d %b %Y}"
            ),
            "metadata[ref]": b.ref,
            "metadata[payment_id]": str(payment.pk),
            "payment_intent_data[description]": f"{b.ref} {b.unit.name}",
            "payment_intent_data[metadata][ref]": b.ref,
            "payment_intent_data[metadata][payment_id]": str(payment.pk),
        }
        if b.guest.email:
            data["customer_email"] = b.guest.email
        s = self._call("POST", "checkout/sessions", data)
        if not s.get("id") or not s.get("url"):
            raise PaymentError("Stripe didn't return a checkout page")
        payment.raw = [
            *payment.raw,
            {"request": {"session": s["id"], "url": s["url"], "expires_at": s.get("expires_at")}},
        ]
        payment.save(update_fields=["checkout_token", "raw"])
        return {"status": "pending", "checkout_url": s["url"]}

    def query(self, payment):
        """The Checkout Session as Stripe sees it, or None when it can't be asked."""
        session = stripe_session_id(payment)
        if not session or not settings.STRIPE_SECRET_KEY:
            return None
        try:
            return self._call("GET", f"checkout/sessions/{session}")
        except PaymentError as e:
            log.warning("Stripe session lookup failed for payment %s: %s", payment.pk, e)
            return None

    def refund(self, payment, amount, *, key, note=""):
        """Refund amount (KES) of a settled Checkout payment. key makes a repeated request (after a timeout, say)
        return the same refund instead of a second one. Returns Stripe's Refund object."""
        intent = payment.transaction_id or ""
        if not intent.startswith("pi_"):
            raise PaymentError("This card payment has no Stripe PaymentIntent to refund")
        data = {
            "payment_intent": intent,
            "amount": str(int(amount) * 100),
            "reason": "requested_by_customer",
            "metadata[ref]": payment.booking.ref,
            "metadata[payment_id]": str(payment.pk),
            "metadata[note]": note[:450],
        }
        return self._call("POST", "refunds", data, idempotency_key=key)


def mpesa_provider():
    return {"daraja": DarajaMpesa, "africastalking": ATMobileCheckout}.get(settings.MPESA_PROVIDER, SimulatedMpesa)()


def card_provider():
    return {"stripe": StripeCard, "paystack": PaystackCard}.get(settings.CARD_PROVIDER, SimulatedCard)()
