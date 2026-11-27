"""Payment rails end to end: the hosted card page, Africa's Talking and Daraja M-Pesa callbacks, Paystack webhooks."""

import hashlib
import hmac
import json
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.bookings import services as bookings
from apps.bookings.models import Booking
from apps.messaging.models import Message
from apps.payments import services as payments
from apps.payments.models import Payment, Refund
from apps.safety.models import Alert

from .conftest import days

pytestmark = pytest.mark.django_db

JSON = "application/json"


def hold(unit, guest, ci=10, nights=2, **kw):
    kw.setdefault("channel", "web")
    return bookings.create_hold(unit=unit, guest=guest, check_in=days(ci), check_out=days(ci + nights), **kw)


def pending(b, method=None, checkout_id=None, **kw):
    """Start a payment; for M-Pesa give it the provider's id, as Daraja / AT do when the STK push is accepted."""
    p = Payment.objects.get(pk=payments.start_payment(b, method=method, **kw)["payment_id"])
    if checkout_id:
        Payment.objects.filter(pk=p.pk).update(transaction_id=checkout_id)
        p.refresh_from_db()
    return p


def fresh(*objs):
    for o in objs:
        o.refresh_from_db()


def guest_messages(guest, kind):
    return Message.objects.filter(phone=guest.phone, kind=kind)


# ---------- the simulated hosted card page (/pay/card/<token>) ----------


def test_card_page_shows_the_charge_and_pays_once(api, unit, foreign_guest):
    b = hold(unit, foreign_guest)
    p = pending(b)  # card is the default for a non-Kenyan number
    assert p.method == "card" and p.checkout_token
    r = api.get(f"/api/pay/card/{p.checkout_token}")
    assert r.status_code == 200
    assert (r.data["ref"], r.data["amount"], r.data["currency"], r.data["status"]) == (b.ref, b.total, "KES", "pending")
    assert r.data["booking_status"] == "held" and r.data["expired"] is False and r.data["simulated"] is True
    assert r.data["expires_at"] == b.hold_expires_at

    r = api.post(f"/api/pay/card/{p.checkout_token}", {"action": "pay"}, format="json")
    assert r.data["status"] == "success" and r.data["booking_status"] == "confirmed" and r.data["expires_at"] is None
    fresh(p, b)
    assert p.transaction_id == f"CARD-SIM-{p.pk}" and p.provider_ref == f"AUTH{p.pk:06d}" and p.completed_at
    assert (b.status, b.amount_paid, b.payment_status) == ("confirmed", b.total, "paid")
    api.post(f"/api/pay/card/{p.checkout_token}", {"action": "pay"}, format="json")  # double click / back button
    b.refresh_from_db()
    assert b.amount_paid == b.total and guest_messages(foreign_guest, "booking_confirmed").count() == 1


def test_card_declined_then_paid_on_the_same_page(api, unit, foreign_guest):
    b = hold(unit, foreign_guest)
    p = pending(b)
    r = api.post(f"/api/pay/card/{p.checkout_token}", {"action": "decline"}, format="json")
    assert r.data["status"] == "failed" and r.data["booking_status"] == "held"
    fresh(p, b)
    assert p.failure_reason == "card declined" and b.amount_paid == 0
    assert b.events.filter(kind="payment_failed").exists()
    r = api.post(f"/api/pay/card/{p.checkout_token}", {"action": "pay"}, format="json")
    assert r.data["status"] == "success" and r.data["booking_status"] == "confirmed"


def test_card_page_cannot_pay_a_lapsed_hold(api, unit, foreign_guest):
    b = hold(unit, foreign_guest)
    p = pending(b)
    Booking.objects.filter(pk=b.pk).update(hold_expires_at=timezone.now() - timedelta(seconds=1))
    r = api.post(f"/api/pay/card/{p.checkout_token}", {"action": "pay"}, format="json")
    assert r.data["status"] == "pending" and r.data["expired"] is True
    fresh(b)
    assert b.status == "held" and b.amount_paid == 0
    assert api.get("/api/pay/card/not-a-real-token").status_code == 404


def test_real_card_payments_are_not_settled_by_the_test_page(api, unit, foreign_guest):
    b = hold(unit, foreign_guest)
    p = pending(b)
    Payment.objects.filter(pk=p.pk).update(provider="paystack")
    r = api.post(f"/api/pay/card/{p.checkout_token}", {"action": "pay"}, format="json")
    assert r.data["status"] == "pending" and r.data["simulated"] is False
    assert Booking.objects.get(pk=b.pk).status == "held"


# ---------- Africa's Talking mobile checkout ----------


def at_body(p, status="Success", value=None, **extra):
    return json.dumps(
        {
            "transactionId": p.transaction_id,
            "status": status,
            "value": f"KES {p.amount if value is None else value}.0000",
            "providerRefId": "QAT1234XYZ",
            "requestMetadata": {"paymentId": str(p.pk)},
            **extra,
        }
    )


def test_at_callback_confirms_the_booking_once(client, unit, guest, host):
    b = hold(unit, guest)
    p = pending(b, checkout_id="ATPid_one")
    r = client.post("/api/payments/at/callback", at_body(p), content_type=JSON)
    assert r.status_code == 200 and r.content == b"OK"
    fresh(p, b)
    assert p.status == "success" and p.provider_ref == "QAT1234XYZ" and p.raw[-1]["callback"]["status"] == "Success"
    assert (b.status, b.amount_paid, b.payment_status) == ("confirmed", b.total, "paid")
    assert client.post("/api/payments/at/callback", at_body(p), content_type=JSON).status_code == 200  # AT retries
    b.refresh_from_db()
    assert b.amount_paid == b.total and guest_messages(guest, "booking_confirmed").count() == 1


def test_at_callback_finds_the_payment_by_its_metadata(client, unit, guest):
    b = hold(unit, guest)
    p = pending(b)  # the request's response never recorded AT's transaction id
    r = client.post("/api/payments/at/callback", at_body(p, transactionId="ATPid_late"), content_type=JSON)
    assert r.status_code == 200
    fresh(p, b)
    assert p.status == "success" and p.transaction_id == "ATPid_late" and b.status == "confirmed"


def test_at_callback_secret(client, unit, guest, settings):
    settings.AT_WEBHOOK_SECRET = "s3cret-path"
    b = hold(unit, guest)
    p = pending(b, checkout_id="ATPid_secret")
    for url in ("/api/payments/at/callback", "/api/payments/at/callback/wrong", "/api/payments/at/callback?key=nope"):
        assert client.post(url, at_body(p), content_type=JSON).status_code == 403
    fresh(p)
    assert p.status == "pending"
    assert client.post("/api/payments/at/callback?key=s3cret-path", at_body(p), content_type=JSON).status_code == 200
    fresh(p, b)
    assert p.status == "success" and b.status == "confirmed"
    other = hold(unit, guest, ci=20)
    q = pending(other, checkout_id="ATPid_secret2")
    assert client.post("/api/payments/at/callback/s3cret-path", at_body(q), content_type=JSON).status_code == 200
    assert Booking.objects.get(pk=other.pk).status == "confirmed"


def test_at_callback_failure_keeps_the_hold_and_tells_a_remote_guest(client, unit, guest):
    b = hold(unit, guest, channel="ussd")
    p = pending(b, checkout_id="ATPid_fail")
    body = at_body(p, status="Failed", description="Insufficient funds")
    assert client.post("/api/payments/at/callback", body, content_type=JSON).status_code == 200
    fresh(p, b)
    assert p.status == "failed" and p.failure_reason == "Insufficient funds"
    assert b.status == "held" and b.amount_paid == 0
    assert "Insufficient funds" in guest_messages(guest, "payment_failed").get().body
    retry = pending(b, checkout_id="ATPid_retry")  # the guest replies PAY and tries again
    client.post("/api/payments/at/callback", at_body(retry), content_type=JSON)
    assert Booking.objects.get(pk=b.pk).status == "confirmed"


def test_at_callback_underpayment_is_rejected(client, unit, guest, host):
    b = hold(unit, guest)
    p = pending(b, checkout_id="ATPid_short")
    client.post("/api/payments/at/callback", at_body(p, value=p.amount - 100), content_type=JSON)
    fresh(p, b)
    assert p.status == "failed" and "Amount mismatch" in p.failure_reason
    assert b.status == "held" and b.amount_paid == 0 and b.payment_status == "unpaid"
    assert Alert.objects.filter(kind="payment", booking=b, summary__contains="mismatch").exists()


def test_at_callback_for_an_unknown_or_garbled_transaction_is_ignored(client, unit, guest):
    b = hold(unit, guest)
    p = pending(b, checkout_id="ATPid_known")
    unknown = json.dumps({"transactionId": "ATPid_nope", "status": "Success", "value": "KES 1.00"})
    garbled = json.dumps({"status": "Success", "requestMetadata": {"paymentId": "drop table"}})
    for body in (unknown, garbled, "not json", "[1, 2]"):
        assert client.post("/api/payments/at/callback", body, content_type=JSON).status_code == 200
    fresh(p, b)
    assert p.status == "pending" and b.status == "held"


# ---------- Safaricom Daraja STK push ----------


def daraja(p, code=0, amount=None, receipt="QDR4XKJ9P2", desc="The service request is processed successfully."):
    cb = {
        "MerchantRequestID": "29115-34620561-1",
        "CheckoutRequestID": p.transaction_id,
        "ResultCode": code,
        "ResultDesc": desc,
    }
    if code == 0:
        cb["CallbackMetadata"] = {
            "Item": [
                {"Name": "Amount", "Value": float(p.amount if amount is None else amount)},
                {"Name": "MpesaReceiptNumber", "Value": receipt},
                {"Name": "TransactionDate", "Value": 20261125223000},
                {"Name": "PhoneNumber", "Value": int(p.phone.lstrip("+"))},
            ]
        }
    return json.dumps({"Body": {"stkCallback": cb}})


DARAJA = "/api/payments/daraja/callback/cb"


def test_daraja_success_confirms_once(client, unit, guest):
    b = hold(unit, guest)
    p = pending(b, checkout_id="ws_CO_251120261030")
    r = client.post(DARAJA, daraja(p), content_type=JSON)
    assert r.status_code == 200 and r.json() == {"ResultCode": 0, "ResultDesc": "Accepted"}
    fresh(p, b)
    assert p.status == "success" and p.provider_ref == "QDR4XKJ9P2"
    assert (b.status, b.payment_status, b.amount_paid) == ("confirmed", "paid", b.total)
    assert "QDR4XKJ9P2" in b.events.get(kind="payment").text
    client.post(DARAJA, daraja(p), content_type=JSON)
    b.refresh_from_db()
    assert b.amount_paid == b.total and guest_messages(guest, "booking_confirmed").count() == 1


@pytest.mark.parametrize(
    ("code", "reason"),
    [
        (1032, "cancelled on the phone"),
        (1, "insufficient M-Pesa balance"),
        (2001, "wrong M-Pesa PIN"),
        (1037, "the phone didn't respond in time"),
        (17, "the same payment was tried again too soon"),
    ],
)
def test_daraja_failures_keep_the_hold(client, unit, guest, code, reason):
    b = hold(unit, guest, channel="sms")
    p = pending(b, checkout_id=f"ws_CO_fail_{code}")
    assert client.post(DARAJA, daraja(p, code=code, desc="Rule limited."), content_type=JSON).status_code == 200
    fresh(p, b)
    assert p.status == "failed" and p.failure_reason == reason
    assert b.status == "held" and b.amount_paid == 0 and b.hold_active
    assert reason in guest_messages(guest, "payment_failed").get().body
    late = daraja(p)  # a success arriving after a failure for the same request still counts
    client.post(DARAJA, late, content_type=JSON)
    assert Booking.objects.get(pk=b.pk).status == "confirmed"


def test_daraja_callback_secret(client, unit, guest, settings):
    settings.AT_WEBHOOK_SECRET = "s3cret-path"
    b = hold(unit, guest)
    p = pending(b, checkout_id="ws_CO_secret")
    for url in (DARAJA, "/api/payments/daraja/callback/wrong"):
        assert client.post(url, daraja(p), content_type=JSON).status_code == 403
    assert Payment.objects.get(pk=p.pk).status == "pending"
    r = client.post("/api/payments/daraja/callback/s3cret-path", daraja(p), content_type=JSON)
    assert r.status_code == 200 and Booking.objects.get(pk=b.pk).status == "confirmed"


def test_daraja_underpayment_and_unknown_requests(client, unit, guest, foreign_guest, host):
    b = hold(unit, guest)
    p = pending(b, checkout_id="ws_CO_short")
    client.post(DARAJA, daraja(p, amount=p.amount - 1), content_type=JSON)
    fresh(p, b)
    assert p.status == "failed" and b.status == "held"
    assert Alert.objects.filter(kind="payment", booking=b).exists()
    stranger = json.dumps({"Body": {"stkCallback": {"CheckoutRequestID": "ws_CO_nobody", "ResultCode": 0}}})
    assert client.post(DARAJA, stranger, content_type=JSON).json()["ResultCode"] == 0
    assert client.post(DARAJA, "{}", content_type=JSON).status_code == 200
    assert client.post(DARAJA, "[]", content_type=JSON).status_code == 200

    # callbacks that name no checkout request must never be matched to some other pending payment
    other = hold(unit, foreign_guest, ci=20)
    victim = pending(other, method="card")
    assert victim.transaction_id is None
    item = [{"Name": "Amount", "Value": 10_000_000}]
    for cb in ({"ResultCode": 0, "CallbackMetadata": {"Item": item}}, {"ResultCode": 1032}):
        r = client.post(DARAJA, json.dumps({"Body": {"stkCallback": cb}}), content_type=JSON)
        assert r.status_code == 200
    fresh(victim, other)
    assert victim.status == "pending" and other.status == "held" and other.amount_paid == 0


def test_deposit_then_balance_to_fully_paid(client, unit, guest, host_api):
    b = hold(unit, guest, ci=30, nights=3, payment_plan="deposit")
    deposit = pending(b, checkout_id="ws_CO_deposit")
    assert deposit.purpose == "deposit" and deposit.amount == b.amount_due_now == -(-b.total * 30 // 100)
    client.post(DARAJA, daraja(deposit, receipt="QDEP0001"), content_type=JSON)
    b.refresh_from_db()
    assert (b.status, b.payment_status, b.balance_due) == ("confirmed", "deposit_paid", b.total - deposit.amount)
    assert "Balance" in guest_messages(guest, "booking_confirmed").get().body

    r = host_api.post(f"/api/host/reservations/{b.ref}/request-payment", {"method": "mpesa"}, format="json")
    assert r.status_code == 200
    balance = Payment.objects.get(booking=b, status="pending")
    assert balance.purpose == "balance" and balance.amount == b.total - deposit.amount
    Payment.objects.filter(pk=balance.pk).update(transaction_id="ws_CO_balance")
    balance.refresh_from_db()
    client.post(DARAJA, daraja(balance, receipt="QBAL0002"), content_type=JSON)
    b.refresh_from_db()
    assert (b.payment_status, b.balance_due, b.amount_paid) == ("paid", 0, b.total)
    assert "fully paid" in guest_messages(guest, "payment_received").get().body
    assert sorted(b.payments.values_list("provider_ref", flat=True)) == ["QBAL0002", "QDEP0001"]


def test_payment_after_the_dates_were_re_let_is_queued_for_refund(client, host_api, unit, guest, foreign_guest):
    first = hold(unit, guest, channel="ussd")
    p = pending(first, checkout_id="ws_CO_late")
    Booking.objects.filter(pk=first.pk).update(hold_expires_at=timezone.now() - timedelta(minutes=1))
    second = hold(unit, foreign_guest)  # takes the dates once the first hold lapses
    client.post(DARAJA, daraja(p), content_type=JSON)
    fresh(first, second, p)
    assert p.status == "success" and first.status == "refund_due" and second.status == "held"
    assert guest_messages(guest, "late_payment_refund").exists()
    assert Alert.objects.filter(kind="payment", booking=first, severity="high").exists()
    rf = Refund.objects.get(booking=first)
    assert (rf.amount, rf.status, rf.method) == (p.amount, "pending", "mpesa_b2c")
    assert host_api.post(f"/api/host/refunds/{rf.pk}/sent", {"reference": "B2C-77"}, format="json").status_code == 200
    first.refresh_from_db()
    assert (first.status, first.payment_status, first.amount_refunded) == ("cancelled", "refunded", p.amount)


def test_a_duplicate_payment_is_queued_for_refund(client, api, unit, guest, host):
    """The guest got an M-Pesa prompt, switched to card and paid, then also entered their PIN."""
    b = hold(unit, guest)
    stk = pending(b, method="mpesa", checkout_id="ws_CO_dupe")
    card = pending(b, method="card")
    api.post(f"/api/pay/card/{card.checkout_token}", {"action": "pay"}, format="json")
    client.post(DARAJA, daraja(stk), content_type=JSON)
    b.refresh_from_db()
    assert b.status == "confirmed" and b.amount_paid == 2 * b.total
    rf = Refund.objects.get(booking=b)
    assert (rf.amount, rf.status) == (b.total, "pending") and b.balance_due == 0
    assert guest_messages(guest, "refund_queued").filter(body__contains="will be refunded").exists()
    bookings.recalc(b)
    assert Refund.objects.filter(booking=b).count() == 1


# ---------- Paystack (cards, production) ----------

PAYSTACK = "/api/payments/paystack/webhook"


def paystack(settings, p, *, event="charge.success", status="success", amount=None, reference=None):
    body = json.dumps(
        {
            "event": event,
            "data": {
                "id": 4099260516,
                "status": status,
                "reference": reference or p.checkout_token,
                "amount": (p.amount if amount is None else amount) * 100,
                "currency": "KES",
            },
        }
    ).encode()
    return body, hmac.new(settings.PAYSTACK_SECRET_KEY.encode(), body, hashlib.sha512).hexdigest()


def test_paystack_webhook_verifies_the_signature_and_settles_once(client, unit, foreign_guest, settings):
    settings.PAYSTACK_SECRET_KEY = "sk_test_amina"
    b = hold(unit, foreign_guest)
    p = pending(b)
    body, sig = paystack(settings, p)
    assert client.post(PAYSTACK, body, content_type=JSON).status_code == 403
    assert client.post(PAYSTACK, body, content_type=JSON, HTTP_X_PAYSTACK_SIGNATURE="0" * 128).status_code == 403
    tampered = body.replace(b"4099260516", b"4099260517")
    assert client.post(PAYSTACK, tampered, content_type=JSON, HTTP_X_PAYSTACK_SIGNATURE=sig).status_code == 403
    fresh(p)
    assert p.status == "pending"

    assert client.post(PAYSTACK, body, content_type=JSON, HTTP_X_PAYSTACK_SIGNATURE=sig).status_code == 200
    fresh(p, b)
    assert p.status == "success" and p.transaction_id == "4099260516" and p.provider_ref == p.checkout_token
    assert (b.status, b.amount_paid) == ("confirmed", b.total)
    assert client.post(PAYSTACK, body, content_type=JSON, HTTP_X_PAYSTACK_SIGNATURE=sig).status_code == 200
    b.refresh_from_db()
    assert b.amount_paid == b.total and guest_messages(foreign_guest, "booking_confirmed").count() == 1


def test_paystack_webhook_ignores_other_events_and_rejects_short_amounts(client, unit, foreign_guest, settings, host):
    settings.PAYSTACK_SECRET_KEY = "sk_test_amina"
    b = hold(unit, foreign_guest)
    p = pending(b)
    for kw in ({"event": "charge.dispute.create"}, {"status": "failed"}, {"reference": "someone-else"}):
        body, sig = paystack(settings, p, **kw)
        assert client.post(PAYSTACK, body, content_type=JSON, HTTP_X_PAYSTACK_SIGNATURE=sig).status_code == 200
    assert Payment.objects.get(pk=p.pk).status == "pending"
    body, sig = paystack(settings, p, amount=p.amount - 500)
    client.post(PAYSTACK, body, content_type=JSON, HTTP_X_PAYSTACK_SIGNATURE=sig)
    fresh(p, b)
    assert p.status == "failed" and b.status == "held" and b.amount_paid == 0
    assert Alert.objects.filter(kind="payment", booking=b).exists()


def test_paystack_webhook_is_closed_without_a_secret_key(client, unit, foreign_guest, settings):
    settings.PAYSTACK_SECRET_KEY = "sk_test_amina"
    b = hold(unit, foreign_guest)
    p = pending(b)
    body, sig = paystack(settings, p)
    settings.PAYSTACK_SECRET_KEY = ""
    assert client.post(PAYSTACK, body, content_type=JSON, HTTP_X_PAYSTACK_SIGNATURE=sig).status_code == 403
    assert Payment.objects.get(pk=p.pk).status == "pending"


def test_host_payment_ledger_lists_payments_and_refunds(host_api, unit, guest, foreign_guest):
    paid = hold(unit, guest)
    payments.on_success(pending(paid, checkout_id="ws_CO_led"), provider_ref="QLEDGER1")
    bookings.cancel(paid, by="guest")
    waiting = hold(unit, foreign_guest, ci=20)
    pending(waiting)
    data = host_api.get("/api/host/payments").data
    rows = {(r["ref"], r["status"]) for r in data["payments"]}
    assert rows == {(paid.ref, "success"), (waiting.ref, "pending")}
    assert [(r["ref"], r["amount"], r["status"]) for r in data["refunds"]] == [(paid.ref, paid.total, "success")]
    assert [r["ref"] for r in host_api.get("/api/host/payments?status=pending").data["payments"]] == [waiting.ref]
    assert [r["reference"] for r in host_api.get("/api/host/payments?q=QLEDGER").data["payments"]] == ["QLEDGER1"]
