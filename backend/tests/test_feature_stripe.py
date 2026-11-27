"""Card payments through Stripe Checkout, and a site with M-Pesa switched off: going live needs only the
Africa's Talking and Stripe keys."""

import hashlib
import hmac
import json
import time
from datetime import timedelta
from unittest import mock
from urllib.parse import urlsplit

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone

from apps.bookings import services as bookings
from apps.bookings.models import Booking
from apps.messaging import services as messaging
from apps.payments import services as payments
from apps.payments.models import Payment, Refund
from apps.payments.providers import PaymentError, stripe_session_id
from apps.safety.models import Alert

from .conftest import days
from .flowkit import bodies, build_catalogue, ddmm, last_id, ussd

pytestmark = pytest.mark.django_db

JSON = "application/json"
WEBHOOK = "/api/payments/stripe/webhook"
SECRET = "whsec_test_amina"


class FakeStripe:
    """Stands in for httpx.Client: answers Stripe's API from in-memory Checkout Sessions and records every call."""

    def __init__(self):
        self.calls, self.sessions, self.refund_answer = [], {}, None

    def __call__(self, timeout):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def request(self, method, url, data=None, headers=None):
        path = urlsplit(url).path
        self.calls.append({"method": method, "path": path, "data": dict(data or {}), "headers": dict(headers or {})})
        if method == "POST" and path == "/v1/checkout/sessions":
            sid = f"cs_test_{len(self.sessions) + 1:04d}{'a' * 58}"  # real ids are ~66 characters
            self.sessions[sid] = {
                "id": sid,
                "object": "checkout.session",
                "url": f"https://checkout.stripe.com/c/pay/{sid}#fidkdWxOYHwnPyd1blpxYHZxWjA0",
                "status": "open",
                "payment_status": "unpaid",
                "amount_total": int(data["line_items[0][price_data][unit_amount]"]),
                "currency": data["line_items[0][price_data][currency]"],
                "client_reference_id": data["client_reference_id"],
                "payment_intent": None,
                "expires_at": int(data["expires_at"]),
            }
            return self._answer(200, self.sessions[sid])
        if method == "GET" and path.startswith("/v1/checkout/sessions/"):
            s = self.sessions.get(path.rsplit("/", 1)[1])
            return self._answer(200, s) if s else self._answer(404, {"error": {"message": "No such session"}})
        if method == "POST" and path == "/v1/refunds":
            default = (
                200,
                {"id": "re_test_1", "object": "refund", "status": "succeeded", "amount": int(data["amount"])},
            )
            return self._answer(*(self.refund_answer or default))
        return self._answer(404, {"error": {"message": f"unexpected {method} {path}"}})

    @staticmethod
    def _answer(status, body):
        return mock.Mock(status_code=status, json=lambda: body)

    def pay(self, payment, **over):
        """The guest pays on Stripe's page."""
        session = self.sessions[stripe_session_id(payment)]
        session.update(status="complete", payment_status="paid", payment_intent=f"pi_test_{payment.pk}", **over)
        return dict(session)


@pytest.fixture
def stripe(settings):
    settings.CARD_PROVIDER, settings.STRIPE_SECRET_KEY, settings.STRIPE_WEBHOOK_SECRET = (
        "stripe",
        "sk_test_amina",
        SECRET,
    )
    fake = FakeStripe()
    with mock.patch("apps.payments.providers.httpx.Client", fake):
        yield fake


@pytest.fixture
def card_only(settings):
    settings.MPESA_PROVIDER = "off"  # the default: no Safaricom Go-Live yet, so every guest pays by card


def hold(unit, guest, ci=10, nights=2, **kw):
    kw.setdefault("channel", "web")
    return bookings.create_hold(unit=unit, guest=guest, check_in=days(ci), check_out=days(ci + nights), **kw)


def card_payment(b):
    return Payment.objects.get(pk=payments.start_payment(b, method="card")["payment_id"])


def signed(kind, session, *, t=None, secret=SECRET):
    body = json.dumps({"id": "evt_test_1", "object": "event", "type": kind, "data": {"object": session}}).encode()
    t = int(time.time()) if t is None else t
    v1 = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return body, f"t={t},v1={v1}"


# ---------- Stripe Checkout ----------


def test_a_card_payment_opens_stripe_checkout_in_kes_and_returns_to_our_page(stripe, unit, foreign_guest, settings):
    b = hold(unit, foreign_guest)
    r = payments.start_payment(b, method="card")
    p = Payment.objects.get(pk=r["payment_id"])
    [call] = stripe.calls
    d, page = call["data"], f"{settings.FRONTEND_URL.rstrip('/')}/pay/card/{p.checkout_token}"
    assert (call["method"], call["path"]) == ("POST", "/v1/checkout/sessions")
    assert call["headers"]["Authorization"] == "Bearer sk_test_amina"
    assert d["mode"] == "payment" and d["line_items[0][price_data][currency]"] == "kes"
    assert d["line_items[0][price_data][unit_amount]"] == str(p.amount * 100)  # KES has two decimals at Stripe
    assert d["client_reference_id"] == p.checkout_token and d["metadata[ref]"] == b.ref
    assert d["success_url"] == f"{page}?session_id={{CHECKOUT_SESSION_ID}}" and d["cancel_url"] == f"{page}?cancelled=1"
    assert 30 * 60 < int(d["expires_at"]) - time.time() <= 31 * 60  # a hold: Stripe's 30-minute minimum
    assert (p.provider, p.status, p.transaction_id) == ("stripe", "pending", None)
    assert r["checkout_url"].startswith("https://checkout.stripe.com/c/pay/cs_test_") and r["pay_link"] == page


def test_the_stay_confirms_when_the_guest_comes_back_from_stripe(stripe, client, unit, foreign_guest):
    b = hold(unit, foreign_guest)
    p = card_payment(b)
    page = f"/api/pay/card/{p.checkout_token}"
    r = client.get(page)  # an SMS link opened: the page sends the guest on to Stripe
    assert r.data["status"] == "pending" and r.data["checkout_url"].startswith("https://checkout.stripe.com/")
    assert (r.data["provider"], r.data["test_mode"], r.data["simulated"]) == ("stripe", True, False)

    stripe.pay(p)
    cache.clear()  # the page asks Stripe at most every 3 seconds
    r = client.get(f"{page}?session_id=cs_from_the_url")  # only a hint: we look up the session we opened
    b.refresh_from_db()
    p.refresh_from_db()
    assert r.data["status"] == "success" and r.data["checkout_url"] is None
    assert b.status == "confirmed" and b.amount_paid == p.amount
    assert p.transaction_id == p.provider_ref == f"pi_test_{p.pk}"
    lookups = sum(c["method"] == "GET" for c in stripe.calls)
    cache.clear()
    client.get(page)
    assert sum(c["method"] == "GET" for c in stripe.calls) == lookups  # settled: Stripe isn't asked again


def test_the_webhook_settles_once_and_only_with_a_fresh_valid_signature(stripe, client, unit, foreign_guest):
    b = hold(unit, foreign_guest)
    p = card_payment(b)
    session = stripe.pay(p)
    body, header = signed("checkout.session.completed", session)
    assert client.post(WEBHOOK, body, content_type=JSON, HTTP_STRIPE_SIGNATURE=f"{header}0").status_code == 400
    stale_body, stale = signed("checkout.session.completed", session, t=int(time.time()) - 301)
    assert client.post(WEBHOOK, stale_body, content_type=JSON, HTTP_STRIPE_SIGNATURE=stale).status_code == 400
    assert client.post(WEBHOOK, body, content_type=JSON).status_code == 400  # unsigned
    assert Payment.objects.get(pk=p.pk).status == "pending"

    # Stripe may send a second v1 (a rolled secret), v0 and debug entries, in any order
    noisy = f"secret=whsec_****Vt,v1={'0' * 64},{header},v0=abc,destination=we_1,payload=a25aefc6"
    for _ in range(2):  # a duplicate delivery changes nothing
        assert client.post(WEBHOOK, body, content_type=JSON, HTTP_STRIPE_SIGNATURE=noisy).status_code == 200
    b.refresh_from_db()
    assert b.status == "confirmed" and b.amount_paid == p.amount
    assert b.payments.filter(status="success").count() == 1


def test_only_a_complete_paid_kes_session_for_the_whole_amount_counts(stripe, unit, other_unit, foreign_guest):
    b = hold(unit, foreign_guest)
    p = card_payment(b)
    session = stripe.pay(p)
    payments.settle_stripe(p, {**session, "client_reference_id": "another-payment"})
    assert Payment.objects.get(pk=p.pk).status == "pending"
    payments.settle_stripe(p, {**session, "currency": "usd"})
    p.refresh_from_db()
    assert p.status == "failed" and "USD" in p.failure_reason
    assert Alert.objects.filter(booking=b, summary__contains="not KES - check it in Stripe").exists()

    short = hold(other_unit, foreign_guest)
    q = card_payment(short)
    payments.settle_stripe(q, stripe.pay(q, amount_total=100))  # KES 1, not the bill
    q.refresh_from_db()
    short.refresh_from_db()
    assert q.status == "failed" and q.failure_reason.startswith("Amount mismatch") and short.status == "held"


def test_the_scheduler_settles_stripe_payments_nobody_came_back_for(stripe, unit, other_unit, foreign_guest):
    b, b2 = hold(unit, foreign_guest), hold(other_unit, foreign_guest)
    paid, gone = card_payment(b), card_payment(b2)
    Payment.objects.filter(pk__in=[paid.pk, gone.pk]).update(created_at=timezone.now() - timedelta(minutes=5))
    stripe.pay(paid)
    stripe.sessions[stripe_session_id(gone)]["status"] = "expired"
    payments.reconcile_pending()
    paid.refresh_from_db()
    gone.refresh_from_db()
    assert paid.status == "success" and Booking.objects.get(pk=b.pk).status == "confirmed"
    assert (gone.status, gone.failure_reason) == ("failed", "card checkout not completed")

    stale = Payment.objects.create(booking=b2, amount=500, method="card", purpose="full", provider="stripe")
    Payment.objects.filter(pk=stale.pk).update(created_at=timezone.now() - timedelta(hours=27))
    asked = len(stripe.calls)
    cache.clear()
    payments.reconcile_pending()
    assert Payment.objects.get(pk=stale.pk).status == "failed" and len(stripe.calls) == asked  # a day on: unpaid


def test_cancelling_a_stay_paid_by_stripe_refunds_the_card_by_itself(stripe, unit, other_unit, foreign_guest):
    b = hold(unit, foreign_guest, ci=40)
    p = card_payment(b)
    payments.settle_stripe(p, stripe.pay(p))
    before = last_id()
    bookings.cancel(Booking.objects.get(pk=b.pk), by="host", reason="Pipe burst")  # Amina cancels: a full refund
    [call] = [c for c in stripe.calls if c["path"] == "/v1/refunds"]
    assert call["data"]["payment_intent"] == f"pi_test_{p.pk}" and call["data"]["amount"] == str(p.amount * 100)
    assert call["headers"]["Idempotency-Key"].startswith("amina-refund-")
    r = Refund.objects.get(booking=b)
    assert (r.status, r.method, r.provider_ref, r.amount) == ("success", "card", "re_test_1", p.amount)
    assert not Alert.objects.filter(booking=b, summary__startswith="Refund to send").exists()
    assert any("re_test_1" in m for m in bodies(foreign_guest.phone, before))

    refused = hold(other_unit, foreign_guest, ci=40)  # Stripe says no: Amina sends it herself
    q = card_payment(refused)
    payments.settle_stripe(q, stripe.pay(q))
    stripe.refund_answer = (402, {"error": {"message": "Charge has been disputed."}})
    bookings.cancel(Booking.objects.get(pk=refused.pk), by="host")
    assert Refund.objects.get(booking=refused).status == "pending"
    alert = Alert.objects.get(booking=refused, summary__startswith="Refund to send")
    assert "Stripe couldn't send it: Charge has been disputed" in alert.summary


def test_a_refund_bigger_than_one_card_payment_is_split_across_the_stays_stripe_payments(stripe, unit, foreign_guest):
    b = hold(unit, foreign_guest, ci=40, payment_plan="deposit")
    deposit = card_payment(b)
    payments.settle_stripe(deposit, stripe.pay(deposit))
    balance = card_payment(Booking.objects.get(pk=b.pk))  # the rest, before arrival
    payments.settle_stripe(balance, stripe.pay(balance))
    b.refresh_from_db()
    assert b.balance_due == 0 and deposit.amount + balance.amount == b.total
    bookings.cancel(b, by="host")  # a full refund: more than either payment
    calls = [c["data"] for c in stripe.calls if c["path"] == "/v1/refunds"]
    assert [(c["payment_intent"], int(c["amount"]) // 100) for c in calls] == [
        (f"pi_test_{balance.pk}", balance.amount),
        (f"pi_test_{deposit.pk}", deposit.amount),
    ]
    assert sorted(Refund.objects.filter(booking=b).values_list("status", "amount")) == sorted(
        [("success", balance.amount), ("success", deposit.amount)]
    )
    b.refresh_from_db()
    assert b.amount_refunded == b.amount_paid and not Alert.objects.filter(summary__startswith="Refund to send")


# ---------- M-Pesa off: card only, on every channel ----------


def test_with_mpesa_off_kenyan_guests_pay_by_card_everywhere(card_only, client, host_api, unit, guest):
    b = hold(unit, guest)
    assert payments.default_method(guest.phone) == "card" and payments.paybill_number() is None
    with pytest.raises(PaymentError) as refused:
        payments.start_payment(b, method="mpesa")
    assert refused.value.suggest == "card"
    r = payments.start_payment(b)
    token = Payment.objects.get(pk=r["payment_id"]).checkout_token
    assert r["method"] == "card" and r["pay_link"].endswith(f"/pay/card/{token}")

    cfg = client.get("/api/config").data
    assert cfg["payments"]["mpesa"] == "off" and cfg["paybill"] is None
    products = {p["key"]: p for p in host_api.get("/api/host/channels").data["products"]}
    assert "payments" not in products and products["card"]["name"] == "Card payments"

    ctx = bookings.guest_context(b)
    assert (ctx["pay_by"], ctx["pay_prompt"]) == ("card", "Pay by card here")
    for key in ("balance_due", "balance_reminder_soon", "balance_overdue", "code_waiting_balance"):
        assert "M-Pesa" not in messaging.render(key, "en", **ctx)
    assert bookings.pay_words(guest.phone, "sw")["reply_pay"].startswith("Jibu PAY kupata kiungo")

    assert client.post(f"/api/demo/pay/{b.ref}", {"result": 1032}, content_type=JSON).status_code == 400
    assert client.post("/api/demo/c2b", {"ref": b.ref}, content_type=JSON).status_code == 400


def test_a_ussd_booking_with_mpesa_off_texts_a_short_card_link(card_only):
    homes = build_catalogue()[1]
    phone = "+254799000444"
    ci = days(10)
    done = ussd(f"1*2*5*{ddmm(ci)}*2*2*1*5*1", phone=phone)  # Diani, 2 nights, 2 guests, no breakfast, pay all
    b = Booking.objects.get(guest__phone=phone)
    assert b.unit == homes["Diani Palm Suite"] and b.status == "held"
    assert done.startswith(f"END Holding Diani Palm Suite ({b.ref}).") and "card payment link" in done
    assert "M-Pesa" not in done
    p = Payment.objects.get(booking=b)
    assert (p.method, p.status) == ("card", "pending")
    [sms] = bodies(phone)
    assert f"/pay/card/{p.checkout_token}" in sms and "M-Pesa" not in sms


# ---------- going live ----------


def test_going_live_needs_only_the_africas_talking_and_stripe_keys(settings):
    from apps.core.checks import go_live_check

    settings.DEMO = False
    settings.AT_USERNAME, settings.AT_API_KEY, settings.AT_SANDBOX = "aminastays", "atsk_live", False
    settings.AT_SENDER_ID, settings.AMINA_PHONE = "AMINASTAYS", "+254712345678"
    settings.AT_WEBHOOK_SECRET, settings.PUBLIC_URL = "long-random-secret", "https://aminastays.co.ke"
    settings.ALLOWED_HOSTS = ["aminastays.co.ke"]
    settings.MPESA_PROVIDER = "off"
    settings.CARD_PROVIDER, settings.STRIPE_SECRET_KEY, settings.STRIPE_WEBHOOK_SECRET = (
        "stripe",
        "sk_live_x",
        "whsec_x",
    )
    settings.ID_ENCRYPTION_KEY = "set"
    settings.IGLOOHOME_API_KEY, settings.LOCK_PROVIDER_API_BASE = "set", "https://locks.example"
    assert go_live_check() == []

    def warned(**changes):
        with override_settings(**changes):
            return [w.id for w in go_live_check()]

    assert warned(STRIPE_SECRET_KEY="sk_test_x") == ["amina.W019"]  # test mode: no real money
    assert warned(STRIPE_WEBHOOK_SECRET="") == ["amina.W020"]  # works, but confirms later
    assert warned(STRIPE_SECRET_KEY="") == ["amina.W018"]
    assert warned(CARD_PROVIDER="simulate") == ["amina.W009"]
