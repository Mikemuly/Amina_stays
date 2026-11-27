"""New payment flows: M-Pesa failure UX (result codes, deposit switch, one prompt at a time), change payments,
Paystack verification, the ledger's balances due / unmatched queue / CSV, eTIMS-ready invoices and credit notes,
and the Lipa na M-Pesa Paybill fallback (Daraja C2B, "I've paid" claims, SMS PAID)."""

import base64
import csv
import io
import json
import threading
from datetime import UTC, datetime, timedelta
from unittest import mock

import pytest
from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.db import connection
from django.urls import resolve
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bookings import services as bookings
from apps.bookings.models import Booking
from apps.comms import deferred
from apps.core.models import SiteSettings
from apps.core.utils import kes, today
from apps.messaging.models import Message
from apps.payments import c2b, invoices
from apps.payments import services as payments
from apps.payments.models import C2BTransaction, CreditNote, Invoice, Payment, Refund
from apps.payments.providers import SETUP_FAILED, DarajaMpesa, PaymentError, PaystackCard
from apps.safety.models import Alert

from .conftest import days
from .flowkit import frozen, sms

pytestmark = pytest.mark.django_db

JSON = "application/json"
DARAJA = "/api/payments/daraja/callback/cb"
C2B = "/api/payments/daraja/c2b/{}/cb"


def hold(unit, guest, ci=10, nights=2, **kw):
    kw.setdefault("channel", "web")
    return bookings.create_hold(unit=unit, guest=guest, check_in=days(ci), check_out=days(ci + nights), **kw)


def prompt(b, checkout_id=None, **kw):
    """An M-Pesa prompt the phone has been sent (with Daraja's CheckoutRequestID when given)."""
    p = Payment.objects.get(pk=payments.start_payment(b, **kw)["payment_id"])
    if checkout_id:
        Payment.objects.filter(pk=p.pk).update(transaction_id=checkout_id)
        p.refresh_from_db()
    return p


def settle(b, **kw):
    p = prompt(b, **kw)
    payments.on_success(p, transaction_id=f"T{p.pk}", provider_ref=f"QREC{p.pk:06d}")
    b.refresh_from_db()
    return b


def daraja_result(p, code, desc="The service request is processed successfully.", receipt="QDR4XKJ9P2"):
    cb = {"MerchantRequestID": "1-2-3", "CheckoutRequestID": p.transaction_id, "ResultCode": code, "ResultDesc": desc}
    if code == 0:
        cb["CallbackMetadata"] = {
            "Item": [{"Name": "Amount", "Value": float(p.amount)}, {"Name": "MpesaReceiptNumber", "Value": receipt}]
        }
    return json.dumps({"Body": {"stkCallback": cb}})


def c2b_payload(ref, amount, trans_id="SKL3X7QW2P", msisdn="254711000001"):
    return {
        "TransactionType": "Pay Bill",
        "TransID": trans_id,
        "TransTime": timezone.localtime().strftime("%Y%m%d%H%M%S"),
        "TransAmount": f"{amount}.00",
        "BusinessShortCode": "174379",
        "BillRefNumber": ref,
        "MSISDN": msisdn,
        "FirstName": "Wanjiru",
        "LastName": "Test",
    }


def failure(p):
    p.refresh_from_db()
    return payments.public_failure(p)


# ---------- C2: M-Pesa result codes -> reason, guest message, next step ----------


@pytest.mark.parametrize(
    ("code", "reason", "suggest", "words"),
    [
        (1032, "cancelled on the phone", "retry", "Your home is still held for"),
        (1037, "the phone didn't respond in time", "paybill", "pay with Paybill"),
        (1025, "we couldn't reach the phone", "paybill", "Check your signal"),
        (1019, "the M-Pesa prompt expired", "retry", "Tap Resend"),
        (1001, "another M-Pesa request was open on the phone", "wait", "wait a minute"),
        (2001, "wrong M-Pesa PIN", "retry", "repeated wrong PINs"),
        (1, "insufficient M-Pesa balance", "deposit", "pay only the 30% deposit"),
    ],
)
def test_daraja_result_codes_become_a_reason_a_message_and_a_next_step(
    client, unit, guest, code, reason, suggest, words
):
    b = hold(unit, guest)
    p = prompt(b, checkout_id=f"ws_CO_{code}")
    client.post(DARAJA, daraja_result(p, code, desc="Raw Daraja text"), content_type=JSON)
    info = failure(p)
    assert (p.status, p.failure_code, p.failure_reason) == ("failed", str(code), reason)
    assert info["failure_code"] == str(code) and info["suggest"] == suggest and info["retryable"] is True
    assert words in info["failure_message"]
    assert p.raw[-1]["callback"]["ResultDesc"] == "Raw Daraja text"  # Daraja's own words are kept for Amina


def test_unknown_codes_keep_darajas_words_and_a_safe_message(client, unit, guest):
    b = hold(unit, guest)
    p = prompt(b, checkout_id="ws_CO_8006")
    client.post(DARAJA, daraja_result(p, 8006, desc="The security credential is locked."), content_type=JSON)
    info = failure(p)
    assert (p.failure_code, p.failure_reason) == ("8006", "The security credential is locked.")
    assert info["suggest"] == "retry" and "don't pay again" in info["failure_message"]
    assert payments.public_failure(Payment(status="success", booking=b)) == {
        "failure_code": None,
        "failure_message": None,
        "retryable": False,
        "suggest": None,
    }


def test_insufficient_balance_offers_the_deposit_only_where_one_is_allowed(client, unit, other_unit, guest):
    far = hold(unit, guest, ci=20)
    p = prompt(far, checkout_id="ws_CO_far")
    client.post(DARAJA, daraja_result(p, 1), content_type=JSON)
    deposit = -(-far.total * 30 // 100)
    info = failure(p)
    assert (
        info["suggest"] == "deposit"
        and kes(deposit) in info["failure_message"]
        and kes(far.total) in info["failure_message"]
    )

    tomorrow = hold(other_unit, guest, ci=1, nights=1)  # the balance would be due already: no deposit
    q = prompt(tomorrow, checkout_id="ws_CO_soon")
    client.post(DARAJA, daraja_result(q, 1), content_type=JSON)
    assert failure(q)["suggest"] == "card" and "deposit" not in failure(q)["failure_message"]

    on_deposit = hold(unit, guest, ci=40, payment_plan="deposit")  # already paying only the deposit
    r = prompt(on_deposit, checkout_id="ws_CO_dep")
    client.post(DARAJA, daraja_result(r, 1), content_type=JSON)
    assert failure(r)["suggest"] == "card"


def test_two_wrong_pins_in_a_row_suggest_card(client, unit, guest):
    b = hold(unit, guest)
    first = prompt(b, checkout_id="ws_CO_pin1")
    client.post(DARAJA, daraja_result(first, 2001), content_type=JSON)
    second = prompt(b, checkout_id="ws_CO_pin2")
    client.post(DARAJA, daraja_result(second, 2001), content_type=JSON)
    assert failure(first)["suggest"] == "retry" and failure(second)["suggest"] == "card"


def test_paybill_is_only_suggested_when_one_is_configured(client, unit, guest, settings):
    settings.DEMO = False  # simulated M-Pesa and no shortcode: nothing to pay into
    b = hold(unit, guest)
    p = prompt(b, checkout_id="ws_CO_nopb")
    client.post(DARAJA, daraja_result(p, 1037), content_type=JSON)
    assert payments.paybill_config() is None and failure(p)["suggest"] == "retry"
    with mock.patch.dict("os.environ", {"MPESA_SHORTCODE": "522533"}):
        assert payments.paybill_config() == {"number": "522533", "account_hint": "Your booking ref, e.g. AMS-1234"}
        assert failure(p)["suggest"] == "paybill"


def test_a_lapsed_hold_is_no_longer_retryable(client, unit, guest):
    b = hold(unit, guest)
    p = prompt(b, checkout_id="ws_CO_late")
    client.post(DARAJA, daraja_result(p, 1032), content_type=JSON)
    Booking.objects.filter(pk=b.pk).update(hold_expires_at=timezone.now() - timedelta(minutes=1))
    info = failure(p)
    assert info["retryable"] is False and "still held" not in info["failure_message"]


def test_remote_guests_get_the_reason_in_swahili_with_the_paybill(client, unit):
    juma = User.objects.create_user("+254722000777", name="Juma", lang="sw")
    b = hold(unit, juma, channel="sms")
    p = prompt(b, checkout_id="ws_CO_sw")
    client.post(DARAJA, daraja_result(p, 1037), content_type=JSON)
    [body] = Message.objects.filter(phone=juma.phone, kind="payment_failed").values_list("body", flat=True)
    assert "simu haikujibu kwa wakati" in body
    assert f"Paybill 174379, akaunti {b.ref}" in body and kes(p.amount) in body


def test_africas_talking_failures_keep_their_text_and_gain_a_code(client, unit, guest):
    b = hold(unit, guest)
    p = prompt(b, checkout_id="ATPid_x")
    body = {"transactionId": "ATPid_x", "status": "Failed", "description": "Request cancelled by user"}
    client.post("/api/payments/at/callback", json.dumps(body), content_type=JSON)
    p.refresh_from_db()
    assert (p.failure_code, p.failure_reason) == ("1032", "Request cancelled by user")


def test_stk_query_reconciliation_stores_the_code(unit, guest, settings):
    b = hold(unit, guest, channel="ussd")
    p = prompt(b, checkout_id="ws_CO_q")
    Payment.objects.filter(pk=p.pk).update(created_at=timezone.now() - timedelta(minutes=3), provider="daraja")
    settings.MPESA_PROVIDER = "daraja"
    with mock.patch.object(DarajaMpesa, "query", return_value={"ResultCode": "1037", "ResultDesc": "DS timeout."}):
        payments.reconcile_pending()
    assert failure(p)["failure_code"] == "1037" and p.failure_reason == "the phone didn't respond in time"


def test_a_late_success_clears_the_failure(client, unit, guest):
    b = hold(unit, guest)
    p = prompt(b, checkout_id="ws_CO_ls")
    client.post(DARAJA, daraja_result(p, 1037), content_type=JSON)
    client.post(DARAJA, daraja_result(p, 0), content_type=JSON)
    p.refresh_from_db()
    assert (p.status, p.failure_code, p.failure_reason) == ("success", "", "")


# ---------- C2: one prompt at a time, the deposit switch, immediate failures ----------


def test_a_prompt_younger_than_two_minutes_is_reused_not_resent(unit, guest):
    b = hold(unit, guest)
    first = payments.start_payment(b, method="mpesa")
    again = payments.start_payment(b, method="mpesa")
    assert again["payment_id"] == first["payment_id"] and again["status"] == "pending"
    assert "already waiting" in again["message"] and Payment.objects.filter(booking=b).count() == 1
    Payment.objects.filter(pk=first["payment_id"]).update(created_at=timezone.now() - timedelta(minutes=2, seconds=5))
    later = payments.start_payment(b, method="mpesa")
    assert later["payment_id"] != first["payment_id"] and Payment.objects.filter(booking=b).count() == 2
    other_amount = payments.start_payment(b, method="mpesa", amount=b.total - 1)  # a different request
    assert other_amount["payment_id"] not in (first["payment_id"], later["payment_id"])


def test_a_busy_phone_returns_the_open_prompt_instead_of_a_new_payment(unit, guest, settings):
    settings.MPESA_PROVIDER = "daraja"
    b = hold(unit, guest)
    busy = PaymentError("Unable to lock subscriber, a transaction is already in process", failure_code="1001")
    with mock.patch.object(DarajaMpesa, "request", side_effect=busy):
        with pytest.raises(PaymentError) as e:  # nothing of ours is open: the phone is busy with someone else's
            payments.start_payment(b, method="mpesa")
    assert e.value.as_dict() == {"error": str(busy), "failure_code": "1001", "suggest": "wait"}
    open_one = Payment.objects.create(
        booking=b, amount=b.total, method="mpesa", purpose="full", phone="+254711000999", provider="daraja"
    )
    with mock.patch.object(DarajaMpesa, "request", side_effect=busy):
        r = payments.start_payment(b, method="mpesa")
    assert r["payment_id"] == open_one.pk and r["status"] == "pending" and "already waiting" in r["message"]
    assert Payment.objects.filter(booking=b, status="pending").count() == 1


def test_immediate_failures_carry_a_code_and_a_next_step(unit, guest, foreign_guest, settings):
    with pytest.raises(PaymentError) as e:
        payments.start_payment(hold(unit, foreign_guest), method="mpesa")
    assert e.value.as_dict()["suggest"] == "card"
    settings.MPESA_PROVIDER = "daraja"
    b = hold(unit, guest, ci=30)
    with mock.patch.object(DarajaMpesa, "request", side_effect=PaymentError("M-Pesa is unreachable (timeout)")):
        with pytest.raises(PaymentError) as e:
            payments.start_payment(b, method="mpesa")
    assert e.value.as_dict() == {"error": "M-Pesa is unreachable (timeout)", "failure_code": None, "suggest": "retry"}
    assert Payment.objects.get(booking=b).status == "failed"


def test_switching_a_hold_to_the_deposit(unit, guest):
    b = hold(unit, guest, ci=20)
    deposit = payments.deposit_amount(b)
    r = payments.start_payment(b, method="mpesa", plan="deposit")
    b.refresh_from_db()
    assert (b.payment_plan, b.amount_due_now) == ("deposit", deposit)
    assert (r["amount"], r["purpose"]) == (deposit, "deposit")
    assert b.events.filter(kind="plan").exists()
    payments.on_success(Payment.objects.get(pk=r["payment_id"]), provider_ref="QDEP1")
    b.refresh_from_db()
    assert (b.status, b.payment_status, b.balance_due) == ("confirmed", "deposit_paid", b.total - deposit)

    soon = hold(unit, guest, ci=1, nights=1)
    with pytest.raises(PaymentError, match="deposit isn't available"):
        payments.start_payment(soon, method="mpesa", plan="deposit")
    soon.refresh_from_db()
    assert soon.payment_plan == "full" and not soon.payments.exists()


# ---------- C2: the Demo Lab fails a prompt through the callback path ----------


def test_demo_pay_with_a_result_code_fails_the_prompt_like_daraja_would(api, unit, guest):
    b = hold(unit, guest, channel="sms")
    r = api.post(f"/api/demo/pay/{b.ref}", {"result": 1032}, format="json")
    p = Payment.objects.get(booking=b)  # no prompt was open: the demo made one first
    assert r.status_code == 200 and r.json()["ok"] is True
    assert (r.json()["status"], r.json()["failure_code"]) == ("held", "1032")
    assert (p.status, p.failure_reason) == ("failed", "cancelled on the phone")
    assert Message.objects.filter(phone=guest.phone, kind="payment_failed").exists()
    assert api.post(f"/api/demo/pay/{b.ref}", {"result": "nope"}, format="json").status_code == 400
    r = api.post(f"/api/demo/pay/{b.ref}", {}, format="json")
    b.refresh_from_db()
    assert r.json() == {"ref": b.ref, "status": "confirmed", "paid": b.total}


# ---------- reservation changes are paid with purpose "change" ----------


def test_a_change_payment_charges_exactly_the_delta_and_hands_over_to_bookings(unit, guest, monkeypatch):
    calls = []
    monkeypatch.setattr(bookings, "on_change_paid", calls.append, raising=False)
    b = settle(hold(unit, guest))
    assert b.balance_due == 0
    r = payments.start_payment(b, method="mpesa", purpose="change", amount=7_500)
    assert (r["amount"], r["purpose"]) == (7_500, "change")
    p = Payment.objects.get(pk=r["payment_id"])
    payments.on_success(p, provider_ref="QCHG1")
    payments.on_success(p, provider_ref="QCHG1")  # Daraja retries
    b.refresh_from_db()
    assert [c.pk for c in calls] == [p.pk] and b.amount_paid == b.total + 7_500
    assert not Refund.objects.filter(booking=b).exists()  # not an overpayment: the new total isn't applied yet
    assert not Message.objects.filter(phone=guest.phone, kind__in=("payment_received", "refund_queued")).exists()


def test_a_change_payment_without_the_bookings_hook_is_kept_safely(unit, guest, monkeypatch):
    monkeypatch.delattr(bookings, "on_change_paid", raising=False)
    b = settle(hold(unit, guest))
    p = prompt(b, method="mpesa", purpose="change", amount=3_000)
    payments.on_success(p)
    b.refresh_from_db()
    assert p.booking.payments.get(pk=p.pk).status == "success" and b.amount_paid == b.total + 3_000
    assert not Refund.objects.filter(booking=b).exists()


# ---------- C5: Paystack is verified before money counts ----------

PAYSTACK = "/api/payments/paystack/webhook"


def _paystack_card(unit, foreign_guest, settings):
    import hashlib
    import hmac

    settings.PAYSTACK_SECRET_KEY = "sk_test_amina"
    b = hold(unit, foreign_guest)
    p = prompt(b)
    Payment.objects.filter(pk=p.pk).update(provider="paystack")
    p.refresh_from_db()
    body = json.dumps(
        {
            "event": "charge.success",
            "data": {
                "id": 77,
                "status": "success",
                "reference": p.checkout_token,
                "amount": p.amount * 100,
                "currency": "KES",
            },
        }
    ).encode()
    sig = hmac.new(b"sk_test_amina", body, hashlib.sha512).hexdigest()
    return b, p, body, sig


def verified(p, **over):
    data = {"id": 77, "status": "success", "reference": p.checkout_token, "amount": p.amount * 100, "currency": "KES"}
    return {"status": True, "message": "Verification successful", "data": {**data, **over}}


def test_paystack_webhook_settles_only_what_verify_transaction_confirms(client, unit, foreign_guest, settings):
    b, p, body, sig = _paystack_card(unit, foreign_guest, settings)
    with mock.patch.object(PaystackCard, "query", return_value=None):  # Paystack unreachable: wait for reconcile
        assert client.post(PAYSTACK, body, content_type=JSON, HTTP_X_PAYSTACK_SIGNATURE=sig).status_code == 200
    p.refresh_from_db()
    assert p.status == "pending"
    with mock.patch.object(PaystackCard, "query", return_value=verified(p)) as verify:
        client.post(PAYSTACK, body, content_type=JSON, HTTP_X_PAYSTACK_SIGNATURE=sig)
    p.refresh_from_db()
    b.refresh_from_db()
    verify.assert_called_once()
    assert (p.status, p.transaction_id, b.status) == ("success", "77", "confirmed")


@pytest.mark.parametrize(
    ("over", "why"), [({"amount": 100}, "Amount mismatch"), ({"currency": "USD"}, "Paid in USD, expected KES")]
)
def test_paystack_wrong_amount_or_currency_is_refused(client, unit, foreign_guest, settings, over, why):
    b, p, body, sig = _paystack_card(unit, foreign_guest, settings)
    with mock.patch.object(PaystackCard, "query", return_value=verified(p, **over)):
        client.post(PAYSTACK, body, content_type=JSON, HTTP_X_PAYSTACK_SIGNATURE=sig)
    p.refresh_from_db()
    b.refresh_from_db()
    assert p.status == "failed" and why in p.failure_reason and b.status == "held"
    assert Alert.objects.filter(kind="payment", booking=b, severity="high").exists()


def test_pending_paystack_checkouts_are_reconciled(unit, foreign_guest, settings):
    b, p, _, _ = _paystack_card(unit, foreign_guest, settings)
    Payment.objects.filter(pk=p.pk).update(created_at=timezone.now() - timedelta(minutes=3))
    with mock.patch.object(PaystackCard, "query", return_value=verified(p, status="abandoned")):
        payments.reconcile_pending()
    assert Payment.objects.get(pk=p.pk).status == "pending"  # still on the checkout page
    with mock.patch.object(PaystackCard, "query", return_value=verified(p)):
        payments.reconcile_pending()
    assert Payment.objects.get(pk=p.pk).status == "success" and Booking.objects.get(pk=b.pk).status == "confirmed"

    other = hold(unit, foreign_guest, ci=30)
    q = prompt(other)
    Payment.objects.filter(pk=q.pk).update(provider="paystack", created_at=timezone.now() - timedelta(minutes=40))
    q.refresh_from_db()
    with mock.patch.object(
        PaystackCard, "query", return_value=verified(q, status="failed", gateway_response="Declined")
    ):
        payments.reconcile_pending()
    assert (Payment.objects.get(pk=q.pk).status, Payment.objects.get(pk=q.pk).failure_reason) == ("failed", "Declined")


def test_paystack_query_calls_verify_transaction(unit, foreign_guest, settings):
    settings.PAYSTACK_SECRET_KEY = "sk_test_amina"
    p = prompt(hold(unit, foreign_guest))
    seen = {}

    class FakeClient:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, url, headers):
            seen.update(url=url, auth=headers["Authorization"])
            return mock.Mock(json=lambda: {"status": True, "data": {"status": "success"}})

    with mock.patch("apps.payments.providers.httpx.Client", FakeClient):
        assert PaystackCard().query(p)["data"]["status"] == "success"
    assert seen == {
        "url": f"https://api.paystack.co/transaction/verify/{p.checkout_token}",
        "auth": "Bearer sk_test_amina",
    }


# ---------- C3 + C11: the host ledger's balances due and unmatched queue ----------


def test_ledger_lists_balances_due_soonest_first_and_flags_overdue_ones(
    host_api, unit, other_unit, guest, foreign_guest
):
    later = settle(hold(unit, guest, ci=30, payment_plan="deposit"))
    arriving = hold(other_unit, foreign_guest, ci=0, nights=2)
    payments.record_manual_payment(arriving, 2_000)  # part-paid at the door: confirmed with a balance
    settle(hold(unit, foreign_guest, ci=50))  # fully paid: not listed
    hold(other_unit, guest, ci=60)  # a hold: not listed
    rows = host_api.get("/api/host/payments").data["outstanding"]
    arriving.refresh_from_db()
    assert [(r["ref"], r["overdue"]) for r in rows] == [(arriving.ref, True), (later.ref, False)]
    assert rows[0] == {
        "ref": arriving.ref,
        "guest": "Emma Test",
        "phone": foreign_guest.phone,
        "unit": other_unit.name,
        "check_in": days(0),
        "balance_due": arriving.balance_due,
        "due_on": days(-1),
        "overdue": True,
    }


def test_ledger_csv_for_one_month(host_api, unit, guest, foreign_guest):
    paid = settle(hold(unit, guest))
    bookings.cancel(paid, by="guest")  # flexible: full refund, sent at once (simulated)
    old = settle(hold(unit, foreign_guest, ci=40))
    Payment.objects.filter(booking=old).update(completed_at=timezone.now() - timedelta(days=62))
    month = timezone.localdate().strftime("%Y-%m")
    r = host_api.get(f"/api/host/payments?export=csv&month={month}")
    assert r.status_code == 200 and r["Content-Type"] == "text/csv"
    assert f'filename="ledger-{month}.csv"' in r["Content-Disposition"]
    rows = list(csv.reader(io.StringIO(r.content.decode())))
    assert rows[0] == [
        "date",
        "ref",
        "guest",
        "phone",
        "method",
        "purpose",
        "receipt",
        "gross",
        "refunded",
        "net",
        "status",
    ]
    p = paid.payments.get()
    today_s = today().isoformat()
    assert rows[1:] == [
        [
            today_s,
            paid.ref,
            "Wanjiru Test",
            guest.phone,
            "M-Pesa",
            "Full payment",
            p.provider_ref,
            str(paid.total),
            "0",
            str(paid.total),
            "paid",
        ],
        [
            today_s,
            paid.ref,
            "Wanjiru Test",
            guest.phone,
            "M-Pesa (B2C)",
            "Refund",
            "",
            "0",
            str(paid.total),
            str(-paid.total),
            "refunded",
        ],
    ]
    assert host_api.get("/api/host/payments?export=csv&month=2026-13").status_code == 400


# ---------- C9: eTIMS-ready invoices and credit notes ----------


def test_invoices_are_issued_on_confirmation_with_gap_free_numbers(guest_api, unit, other_unit, guest, breakfast):
    s = SiteSettings.load()
    s.kra_pin, s.tra_licence_number = "P051234567X", "TRA/A/MSA/2026/0417"
    s.save()
    b = settle(hold(unit, guest, adults=2, addons=[{"code": "breakfast"}]))
    second = settle(hold(other_unit, guest))
    year = timezone.localdate().year
    assert Invoice.objects.get(booking=b).number == f"AMS-INV-{year}-00001"
    assert Invoice.objects.get(booking=second).number == f"AMS-INV-{year}-00002"
    hold(unit, guest, ci=40)  # held: no invoice
    assert Invoice.objects.count() == 2

    inv = guest_api.get(f"/api/bookings/{b.ref.lower()}/invoice").data
    assert inv["number"] == f"AMS-INV-{year}-00001" and inv["etims"] == {"status": "not_submitted", "invoice_no": None}
    assert inv["seller"] == {
        "name": "Amina Stays",
        "kra_pin": "P051234567X",
        "address": "Mombasa, Kenya",
        "tra_licence": "TRA/A/MSA/2026/0417",
        "vat_registered": False,
    }
    assert inv["buyer"] == {"name": "Wanjiru Test", "phone": guest.phone, "kra_pin": ""}
    assert [(x["label"].split(", ")[-1], x["qty"], x["unit_price"]) for x in inv["lines"]] == [
        ("per night", 2, 10_000),
        ("Cleaning fee", 1, 2_000),
        ("Breakfast", 4, 650),
    ]
    assert all(x["amount"] == x["qty"] * x["unit_price"] for x in inv["lines"])
    assert inv["subtotal"] == sum(x["amount"] for x in inv["lines"]) and inv["vat"] == 0
    assert inv["subtotal"] + inv["levy"] + inv["vat"] == inv["total"] == b.total
    assert (inv["paid"], inv["balance"], inv["credit_notes"]) == (b.total, 0, [])
    assert [(x["method"], x["amount"]) for x in inv["payments"]] == [("M-Pesa", b.total)]


def test_the_invoice_follows_the_booking_until_it_goes_to_kra(guest_api, unit, guest, breakfast):
    b = settle(hold(unit, guest, ci=20, payment_plan="deposit"))
    inv = guest_api.get(f"/api/bookings/{b.ref}/invoice").data
    assert inv["balance"] == b.balance_due > 0
    bookings.add_addon(b, "breakfast", quantity=1)
    b.refresh_from_db()
    inv = guest_api.get(f"/api/bookings/{b.ref}/invoice").data
    assert inv["total"] == b.total and inv["lines"][-1]["label"] == "Breakfast" and inv["credit_notes"] == []

    Invoice.objects.filter(booking=b).update(etims_status="synced", etims_invoice_no="KRA0001")
    sent_total = b.total
    bookings.set_breakfast(b, "none")  # after transmission the invoice is frozen: the reduction is a credit note
    b.refresh_from_db()
    inv = guest_api.get(f"/api/bookings/{b.ref}/invoice").data
    assert inv["etims"] == {"status": "synced", "invoice_no": "KRA0001"} and inv["total"] == sent_total > b.total
    assert [c["amount"] for c in inv["credit_notes"]] == [sent_total - b.total]
    assert inv["balance"] == b.balance_due
    r = guest_api.patch(f"/api/bookings/{b.ref}/invoice", {"buyer_name": "X"}, format="json")
    assert r.status_code == 400 and "already been sent to KRA" in r.data["error"]


def test_invoice_access_and_the_buyers_kra_pin(api, guest_api, host_api, unit, guest, foreign_guest):
    b = settle(hold(unit, guest))
    held = hold(unit, guest, ci=40)
    stranger = APIClient()
    stranger.force_authenticate(foreign_guest)
    assert stranger.get(f"/api/bookings/{b.ref}/invoice").status_code == 404
    assert api.get(f"/api/bookings/{b.ref}/invoice").status_code in (401, 403)
    assert host_api.get(f"/api/bookings/{b.ref}/invoice").status_code == 200
    r = guest_api.get(f"/api/bookings/{held.ref}/invoice")
    assert r.status_code == 404 and r.data["error"] == "An invoice is issued once the booking is confirmed."

    r = guest_api.patch(
        f"/api/bookings/{b.ref}/invoice", {"buyer_name": "Acme Ltd", "buyer_kra_pin": "12345"}, format="json"
    )
    assert r.status_code == 400 and "KRA PIN" in r.data["error"]
    r = guest_api.patch(
        f"/api/bookings/{b.ref}/invoice", {"buyer_name": " Acme Ltd ", "buyer_kra_pin": "p051234567x"}, format="json"
    )
    assert r.status_code == 200 and r.data["buyer"] == {
        "name": "Acme Ltd",
        "phone": guest.phone,
        "kra_pin": "P051234567X",
    }
    assert Invoice.objects.get(booking=b).number == r.data["number"]  # reissued in the company's name, same number


def test_a_cancellation_refund_issues_a_credit_note(guest_api, host_api, unit, other_unit, guest):
    b = settle(hold(unit, guest))  # flexible: a full refund, sent at once (simulated)
    bookings.cancel(b, by="guest")
    year = timezone.localdate().year
    inv = guest_api.get(f"/api/bookings/{b.ref}/invoice").data
    assert [(c["number"], c["amount"]) for c in inv["credit_notes"]] == [(f"AMS-CN-{year}-00001", b.total)]
    assert (inv["paid"], inv["balance"]) == (0, 0)
    assert inv["credit_notes"][0]["reason"] == "Cancelled by guest"

    queued = settle(hold(other_unit, guest))  # a real refund waits for Amina to send it
    Payment.objects.filter(booking=queued).update(provider="daraja")
    bookings.cancel(queued, by="host")
    assert not CreditNote.objects.filter(invoice__booking=queued).exists()
    rf = Refund.objects.get(booking=queued)
    host_api.post(f"/api/host/refunds/{rf.pk}/sent", {"reference": "B2C-1"}, format="json")
    assert CreditNote.objects.get(invoice__booking=queued).amount == queued.total
    guest_api.get(f"/api/bookings/{queued.ref}/invoice")  # viewing it again changes nothing
    assert CreditNote.objects.count() == 2


def test_returning_an_overpayment_is_not_a_credit_note(api, unit, guest, host_api):
    b = hold(unit, guest)
    stk = prompt(b, method="mpesa")
    card = prompt(b, method="card")
    api.post(f"/api/pay/card/{card.checkout_token}", {"action": "pay"}, format="json")
    payments.on_success(stk, provider_ref="QDUP1")
    rf = Refund.objects.get(booking=b)
    host_api.post(f"/api/host/refunds/{rf.pk}/sent", {"reference": "B2C-2"}, format="json")
    inv = host_api.get(f"/api/bookings/{b.ref}/invoice").data
    assert inv["credit_notes"] == [] and inv["paid"] == b.total and inv["balance"] == 0
    assert [x["amount"] for x in inv["payments"]] == [b.total, b.total, -b.total]


def test_the_sales_register(host_api, unit, other_unit, guest):
    b = settle(hold(unit, guest))
    settle(hold(other_unit, guest))
    bookings.cancel(b, by="guest")
    month = timezone.localdate().strftime("%Y-%m")
    data = host_api.get(f"/api/host/invoices?month={month}").data
    assert [r["number"][-5:] for r in data["invoices"]] == ["00001", "00002"]
    [cn] = data["credit_notes"]
    assert cn["against_invoice"] == data["invoices"][0]["number"] and cn["total"] == -b.total
    assert cn["net"] + cn["vat"] + cn["levy"] == cn["total"]
    assert data["totals"]["total"] == sum(r["total"] for r in data["invoices"]) - b.total
    r = host_api.get(f"/api/host/invoices?month={month}&export=csv")
    rows = list(csv.reader(io.StringIO(r.content.decode())))
    assert rows[0] == invoices.REGISTER_COLUMNS and [x[0] for x in rows[1:]] == [
        "invoice",
        "invoice",
        "credit_note",
        "total",
    ]
    assert host_api.get("/api/host/invoices?month=last-month").status_code == 400


@pytest.mark.django_db(transaction=True)
def test_invoice_numbers_stay_unique_when_issued_at_the_same_moment(unit, guest):
    stays = []
    for i in range(5):  # confirmed by Amina (pay on arrival): no invoice yet
        b = hold(unit, guest, ci=10 + 3 * i)
        stays.append(bookings.confirm(b))
    barrier, errors = threading.Barrier(len(stays) + 2), []

    def issue(b):
        try:
            barrier.wait(timeout=10)
            invoices.get_or_issue(b)
        except Exception as e:  # pragma: no cover - reported below
            errors.append(e)
        finally:
            connection.close()

    threads = [threading.Thread(target=issue, args=(b,)) for b in [*stays, stays[0], stays[0]]]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert sorted(Invoice.objects.values_list("seq", flat=True)) == [1, 2, 3, 4, 5]
    assert Invoice.objects.filter(booking=stays[0]).count() == 1


# ---------- C11: Lipa na M-Pesa Paybill (Daraja C2B) ----------


@pytest.mark.parametrize("typed", ["AMS-4821", " ams 4821 ", "ams4821", "4821", "Ams - 4821"])
def test_paybill_account_numbers_are_normalised(typed):
    assert c2b.normalise_ref(typed) == "AMS-4821"


def test_config_offers_the_paybill(api, settings):
    assert api.get("/api/config").data["paybill"] == {
        "number": "174379",
        "account_hint": "Your booking ref, e.g. AMS-1234",
    }
    settings.DEMO = False
    assert api.get("/api/config").data["paybill"] is None
    settings.MPESA_PROVIDER = "daraja"
    assert api.get("/api/config").data["paybill"]["number"] == settings.DARAJA_SHORTCODE


def test_a_paybill_payment_confirms_the_hold_once(client, unit, guest):
    b = hold(unit, guest, channel="ussd")
    typed = " " + b.ref.lower().replace("-", " ") + " "  # "ams 4821" - as people type it
    for _ in range(2):  # Safaricom may deliver a confirmation twice
        r = client.post(C2B.format("confirmation"), json.dumps(c2b_payload(typed, b.total)), content_type=JSON)
        assert r.json() == {"ResultCode": 0, "ResultDesc": "Accepted"}
    b.refresh_from_db()
    t = C2BTransaction.objects.get()
    p = Payment.objects.get(booking=b)
    assert (b.status, b.amount_paid) == ("confirmed", b.total)
    assert (t.status, t.booking_id, t.payment_id, t.trans_id) == ("matched", b.pk, p.pk, "SKL3X7QW2P")
    assert (p.provider, p.method, p.transaction_id, p.provider_ref, p.purpose) == (
        "c2b",
        "mpesa",
        "SKL3X7QW2P",
        "SKL3X7QW2P",
        "full",
    )
    assert Message.objects.filter(phone=guest.phone, kind="booking_confirmed").count() == 1


def test_c2b_callbacks_need_the_secret(client, unit, guest, settings):
    settings.AT_WEBHOOK_SECRET = "s3cret"
    b = hold(unit, guest)
    body = json.dumps(c2b_payload(b.ref, b.total))
    for url in (C2B.format("confirmation"), "/api/payments/daraja/c2b/confirmation/wrong"):
        assert client.post(url, body, content_type=JSON).status_code == 403
    assert not C2BTransaction.objects.exists()
    assert client.post("/api/payments/daraja/c2b/confirmation/s3cret", body, content_type=JSON).status_code == 200
    assert Booking.objects.get(pk=b.pk).status == "confirmed"
    assert client.post("/api/payments/daraja/c2b/refund/s3cret", body, content_type=JSON).status_code == 404


def test_c2b_validation_rejects_unknown_accounts_and_short_amounts(client, unit, guest):
    b = hold(unit, guest)

    def check(ref, amount):
        return client.post(C2B.format("validation"), json.dumps(c2b_payload(ref, amount)), content_type=JSON).json()

    assert check(b.ref, b.total) == {"ResultCode": "0", "ResultDesc": "Accepted"}
    assert check("AMS-0000", b.total) == {"ResultCode": "C2B00012", "ResultDesc": "Rejected"}
    assert check(b.ref, b.total - 1)["ResultCode"] == "C2B00013"
    confirmed = settle(hold(unit, guest, ci=30, payment_plan="deposit"))
    assert check(confirmed.ref, 500)["ResultCode"] == "0"  # any part of a balance is welcome
    assert not C2BTransaction.objects.exists()  # validation never records money


def test_paybill_payer_numbers_are_normalised_unless_masked(client, unit, guest):
    b = hold(unit, guest)
    client.post(C2B.format("confirmation"), json.dumps(c2b_payload("X1", 500, "TRX0000001")), content_type=JSON)
    masked = c2b_payload("X2", 500, "TRX0000002", msisdn="2547 ***** 126")  # Safaricom may mask the payer
    client.post(C2B.format("confirmation"), json.dumps(masked), content_type=JSON)
    phones = dict(C2BTransaction.objects.values_list("trans_id", "phone"))
    assert phones == {"TRX0000001": "+254711000001", "TRX0000002": "2547 ***** 126"}
    assert Booking.objects.get(pk=b.pk).status == "held"


def test_unmatched_paybill_payments_wait_for_amina(client, host_api, unit, guest, host):
    b = hold(unit, guest)
    client.post(C2B.format("confirmation"), json.dumps(c2b_payload("WANJIRU", b.total)), content_type=JSON)
    t = C2BTransaction.objects.get()
    assert t.status == "unmatched" and Booking.objects.get(pk=b.pk).status == "held"
    assert Alert.objects.filter(kind="payment", summary__contains="SKL3X7QW2P").count() == 1
    [row] = host_api.get("/api/host/payments").data["unmatched"]
    assert {k: row[k] for k in ("id", "trans_id", "amount", "phone", "bill_ref")} == {
        "id": t.pk,
        "trans_id": "SKL3X7QW2P",
        "amount": b.total,
        "phone": "+254711000001",
        "bill_ref": "WANJIRU",
    }
    assert row["received_at"]
    r = host_api.post(f"/api/host/payments/unmatched/{t.pk}/match", {"ref": "AMS-0000"}, format="json")
    assert r.status_code == 400
    r = host_api.post(f"/api/host/payments/unmatched/{t.pk}/match", {"ref": b.ref.lower()}, format="json")
    assert r.status_code == 200 and r.data["ref"] == b.ref and r.data["status"] == "confirmed"
    assert host_api.get("/api/host/payments").data["unmatched"] == []
    alert = Alert.objects.get(kind="payment", summary__contains="SKL3X7QW2P")
    assert alert.status == "resolved" and b.ref in alert.resolution_note  # matching closes its own alert
    r = host_api.post(f"/api/host/payments/unmatched/{t.pk}/match", {"ref": b.ref}, format="json")
    assert r.status_code == 400 and "already matched" in r.data["error"]


def test_short_and_over_payments_follow_the_usual_rules(client, unit, other_unit, guest):
    short = hold(unit, guest)
    client.post(C2B.format("confirmation"), json.dumps(c2b_payload(short.ref, 1_000, "SSHORT0001")), content_type=JSON)
    t = C2BTransaction.objects.get(trans_id="SSHORT0001")
    assert t.status == "unmatched" and t.booking_id == short.pk and "Short payment" in t.note
    assert Booking.objects.get(pk=short.pk).status == "held" and not short.payments.exists()

    paid = settle(hold(other_unit, guest, ci=30))
    client.post(C2B.format("confirmation"), json.dumps(c2b_payload(paid.ref, 2_500, "SOVER00001")), content_type=JSON)
    paid.refresh_from_db()
    rf = Refund.objects.get(booking=paid)
    assert (rf.amount, rf.status, rf.method) == (2_500, "pending", "mpesa_b2c")
    assert paid.amount_paid == paid.total + 2_500 and paid.balance_due == 0


def test_an_stk_payment_echoed_to_the_paybill_counts_once(client, unit, guest):
    b = hold(unit, guest)
    p = prompt(b, checkout_id="ws_CO_echo")
    client.post(DARAJA, daraja_result(p, 0, receipt="SECHO00001"), content_type=JSON)
    client.post(C2B.format("confirmation"), json.dumps(c2b_payload(b.ref, b.total, "SECHO00001")), content_type=JSON)
    b.refresh_from_db()
    assert b.amount_paid == b.total and b.payments.count() == 1
    assert C2BTransaction.objects.get().status == "matched"

    other = hold(unit, guest, ci=30)  # the other way round: the Paybill notice first, then the prompt's callback
    q = prompt(other, checkout_id="ws_CO_echo2")
    client.post(
        C2B.format("confirmation"), json.dumps(c2b_payload(other.ref, other.total, "SECHO00002")), content_type=JSON
    )
    client.post(DARAJA, daraja_result(q, 0, receipt="SECHO00002"), content_type=JSON)
    other.refresh_from_db()
    assert other.amount_paid == other.total and Payment.objects.get(pk=q.pk).status == "cancelled"


def test_claiming_a_payment_with_its_m_pesa_code(client, guest_api, unit, guest, foreign_guest):
    b = hold(unit, guest)
    client.post(C2B.format("confirmation"), json.dumps(c2b_payload("AMS 99999", b.total)), content_type=JSON)
    stranger = APIClient()
    stranger.force_authenticate(foreign_guest)
    assert stranger.post(f"/api/bookings/{b.ref}/claim", {"code": "SKL3X7QW2P"}, format="json").status_code == 404
    r = guest_api.post(f"/api/bookings/{b.ref}/claim", {"code": "skl3x7qw2p"}, format="json")
    assert r.status_code == 200 and r.data["status"] == "matched" and "SKL3X7QW2P" in r.data["message"]
    b.refresh_from_db()
    assert b.status == "confirmed" and C2BTransaction.objects.get().booking_id == b.pk
    again = guest_api.post(f"/api/bookings/{b.ref}/claim", {"code": "SKL3X7QW2P"}, format="json").data
    assert again["status"] == "matched"

    r = guest_api.post(f"/api/bookings/{b.ref}/claim", {"code": "SNOTSEEN01"}, format="json")
    assert r.data == {
        "status": "pending_review",
        "message": f"Thanks - we've passed M-Pesa code SNOTSEEN01 to Amina, who will match it to {b.ref} shortly. "
        "Please don't pay again.",
    }
    guest_api.post(f"/api/bookings/{b.ref}/claim", {"code": "SNOTSEEN01"}, format="json")
    assert Alert.objects.filter(summary__contains="SNOTSEEN01", booking=b).count() == 1
    r = guest_api.post(f"/api/bookings/{b.ref}/claim", {"code": "12"}, format="json")
    assert r.status_code == 400 and "M-Pesa code" in r.data["error"]


def test_a_claim_finds_a_prompt_whose_callback_never_came(guest_api, unit, guest, settings):
    b = hold(unit, guest)
    p = prompt(b, checkout_id="ws_CO_lost")
    Payment.objects.filter(pk=p.pk).update(provider="daraja")
    settings.MPESA_PROVIDER = "daraja"
    with mock.patch.object(DarajaMpesa, "query", return_value={"ResultCode": "0", "ResultDesc": "ok"}):
        r = guest_api.post(f"/api/bookings/{b.ref}/claim", {"code": "SLOST00001"}, format="json")
    assert r.data["status"] == "matched" and Booking.objects.get(pk=b.pk).status == "confirmed"


def test_sms_paid_with_the_code(client, unit, guest):
    b = hold(unit, guest, channel="sms")
    client.post(C2B.format("confirmation"), json.dumps(c2b_payload("typo", b.total)), content_type=JSON)
    replies = sms("PAID SKL3X7QW2P", phone=guest.phone)
    assert any("we found M-Pesa payment SKL3X7QW2P" in body for body in replies)
    assert Booking.objects.get(pk=b.pk).status == "confirmed"
    replies = sms("paid SXXXXXXX99", phone=guest.phone)
    assert any("passed M-Pesa code SXXXXXXX99" in body for body in replies)


def test_demo_c2b(api, unit, guest, settings):
    b = hold(unit, guest)
    r = api.post("/api/demo/c2b", {"ref": b.ref}, format="json")
    assert r.status_code == 200 and r.json()["matched"] is True and len(r.json()["trans_id"]) == 10
    b.refresh_from_db()
    assert b.status == "confirmed" and b.payments.get().amount == b.total  # the amount due now, by default
    r = api.post("/api/demo/c2b", {"ref": "AMS-0001", "amount": 5_000, "phone": "0722000111"}, format="json")
    assert (
        r.json()["matched"] is False
        and C2BTransaction.objects.get(trans_id=r.json()["trans_id"]).phone == "+254722000111"  # stored in E.164
    )
    assert api.post("/api/demo/c2b", {"ref": "AMS-0001"}, format="json").status_code == 400
    settings.DEMO = False
    assert api.post("/api/demo/c2b", {"ref": b.ref}, format="json").status_code == 404


# ---------- C11: registering the Paybill URLs with Daraja ----------


def test_c2b_urls_are_built_from_the_public_address_and_secret(settings):
    settings.PUBLIC_URL, settings.AT_WEBHOOK_SECRET = "https://abc123.ngrok-free.app/", "s3cret"
    urls = c2b.c2b_urls()
    assert urls == {
        "validation": "https://abc123.ngrok-free.app/api/payments/daraja/c2b/validation/s3cret",
        "confirmation": "https://abc123.ngrok-free.app/api/payments/daraja/c2b/confirmation/s3cret",
    }
    for url in urls.values():  # and they reach the C2B endpoint
        assert resolve(url.removeprefix("https://abc123.ngrok-free.app")).func.__name__ == "c2b_callback"


def test_register_c2b_only_prints_the_urls_in_demo_mode(settings):
    out = io.StringIO()
    with mock.patch("apps.payments.c2b.httpx.Client", side_effect=AssertionError("no network in DEMO mode")):
        call_command("register_c2b", stdout=out)
    text = out.getvalue()
    assert c2b.c2b_urls()["validation"] in text and c2b.c2b_urls()["confirmation"] in text
    assert "nothing was registered" in text


def _live_daraja(settings):
    settings.DEMO, settings.MPESA_PROVIDER, settings.DARAJA_ENV = False, "daraja", "sandbox"
    settings.DARAJA_CONSUMER_KEY, settings.DARAJA_CONSUMER_SECRET = "key", "secret"
    settings.PUBLIC_URL, settings.AT_WEBHOOK_SECRET = "https://stays.example.co.ke", "s3cret"


def test_register_c2b_calls_daraja_registerurl(settings):
    _live_daraja(settings)
    sent, answer = {}, {"OriginatorCoversationID": "6e86-45dd", "ResponseCode": "0", "ResponseDescription": "Success"}

    class FakeClient:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, url, json, headers):
            sent.update(url=url, body=json, auth=headers["Authorization"])
            return mock.Mock(status_code=200, json=lambda: answer)

    out = io.StringIO()
    with (
        mock.patch.object(DarajaMpesa, "_token", return_value="tok"),
        mock.patch("apps.payments.c2b.httpx.Client", FakeClient),
    ):
        call_command("register_c2b", "--shortcode", "600981", stdout=out)
    assert sent == {
        "url": "https://sandbox.safaricom.co.ke/mpesa/c2b/v2/registerurl",
        "body": {
            "ShortCode": "600981",
            "ResponseType": "Completed",
            "ConfirmationURL": "https://stays.example.co.ke/api/payments/daraja/c2b/confirmation/s3cret",
            "ValidationURL": "https://stays.example.co.ke/api/payments/daraja/c2b/validation/s3cret",
        },
        "auth": "Bearer tok",
    }
    assert '"ResponseDescription": "Success"' in out.getvalue() and "registered" in out.getvalue()

    answer = {"requestId": "1-2", "errorCode": "500.003.1001", "errorMessage": "Urls are already registered"}
    with (
        mock.patch.object(DarajaMpesa, "_token", return_value="tok"),
        mock.patch("apps.payments.c2b.httpx.Client", FakeClient),
    ):
        with pytest.raises(CommandError, match="Urls are already registered"):
            call_command("register_c2b", stdout=io.StringIO())


def test_register_c2b_says_what_is_missing(settings):
    _live_daraja(settings)
    settings.DARAJA_CONSUMER_SECRET = ""
    with pytest.raises(CommandError, match="Daraja isn't configured - set DARAJA_CONSUMER_SECRET"):
        call_command("register_c2b", stdout=io.StringIO())
    settings.DARAJA_CONSUMER_SECRET, settings.PUBLIC_URL = "secret", "http://localhost:3000"
    with pytest.raises(CommandError, match="HTTPS"):
        call_command("register_c2b", stdout=io.StringIO())


# ---------- Paybill money for a pending date change ----------


def test_a_pending_date_change_gets_first_call_on_paybill_money(client, guest_api, unit, guest, monkeypatch):
    seen = []

    def takes_it(booking, payment):
        seen.append((booking.pk, payment.pk, payment.status, payment.provider, payment.provider_ref))
        return True

    monkeypatch.setattr(bookings, "attach_change_payment", takes_it, raising=False)
    b = settle(hold(unit, guest))
    paid = b.amount_paid
    client.post(C2B.format("confirmation"), json.dumps(c2b_payload(b.ref, 4_000, "SCHANGE001")), content_type=JSON)
    p = Payment.objects.get(transaction_id="SCHANGE001")
    assert seen == [(b.pk, p.pk, "pending", "c2b", "SCHANGE001")]
    b.refresh_from_db()
    assert p.status == "pending" and b.amount_paid == paid  # the change settles it, not the balance allocation
    assert C2BTransaction.objects.get(trans_id="SCHANGE001").status == "matched"
    assert not Refund.objects.filter(booking=b).exists()

    client.post(C2B.format("confirmation"), json.dumps(c2b_payload("typo", 2_000, "SCHANGE002")), content_type=JSON)
    r = guest_api.post(f"/api/bookings/{b.ref}/claim", {"code": "SCHANGE002"}, format="json")  # a claim too
    assert r.data["status"] == "matched" and [x[4] for x in seen] == ["SCHANGE001", "SCHANGE002"]

    monkeypatch.setattr(bookings, "attach_change_payment", lambda booking, payment: False)
    client.post(C2B.format("confirmation"), json.dumps(c2b_payload(b.ref, 1_500, "SCHANGE003")), content_type=JSON)
    b.refresh_from_db()
    assert Payment.objects.get(transaction_id="SCHANGE003").status == "success" and b.amount_paid == paid + 1_500
    assert Refund.objects.get(booking=b).amount == 1_500  # no change wanted it: an overpayment, as usual

    def broken(booking, payment):
        raise RuntimeError("boom")

    monkeypatch.setattr(bookings, "attach_change_payment", broken)
    client.post(C2B.format("confirmation"), json.dumps(c2b_payload(b.ref, 500, "SCHANGE004")), content_type=JSON)
    assert Payment.objects.get(transaction_id="SCHANGE004").status == "success"  # never left pending


# ---------- going live: what Daraja really answers ----------


class FakeDaraja:
    """Stands in for httpx.Client: each POST gets the next (status, json) answer (the last one repeats) and is
    recorded; a GET is the OAuth call and hands out tok1, tok2, ..."""

    def __init__(self, *answers):
        self.answers, self.sent, self.tokens = list(answers), [], 0

    def __call__(self, timeout):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, params, auth):
        self.tokens += 1
        token = f"tok{self.tokens}"
        return mock.Mock(status_code=200, json=lambda: {"access_token": token, "expires_in": "3599"})

    def post(self, url, json, headers):
        self.sent.append({"url": url, "body": json, "auth": headers["Authorization"]})
        status, body = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        return mock.Mock(status_code=status, json=lambda: body)


def daraja_prompt(b):
    return Payment.objects.create(
        booking=b, amount=b.total, method="mpesa", purpose="full", phone=b.guest.phone, provider="daraja"
    )


BUSY = "Unable to lock subscriber, a transaction is already in process for the current subscriber"


@pytest.mark.parametrize(
    ("error", "message", "code"),
    [
        ("500.001.1001", BUSY, "1001"),
        ("500.001.1001", "Merchant does not exist", None),
        ("500.001.1001", "Wrong credentials", None),
        ("400.002.02", "Bad Request - Invalid BusinessShortCode", None),
        ("404.001.03", "Invalid Access Token", None),  # still refused with a fresh token
    ],
)
def test_only_a_busy_phone_is_blamed_on_the_guest_and_a_setup_error_alerts_amina(
    unit, guest, host, settings, error, message, code
):
    _live_daraja(settings)
    b = hold(unit, guest)
    fake = FakeDaraja((int(error[:3]), {"requestId": "29115-1", "errorCode": error, "errorMessage": message}))
    with mock.patch("apps.payments.providers.httpx.Client", fake):
        for _ in range(2):  # the guest tries again
            with pytest.raises(PaymentError) as e:
                payments.start_payment(b, method="mpesa")
    p = b.payments.latest("id")
    if code:
        assert e.value.as_dict() == {"error": message, "failure_code": "1001", "suggest": "wait"}
        assert not Alert.objects.exists()
        return
    assert e.value.as_dict() == {"error": SETUP_FAILED, "failure_code": None, "suggest": "retry"}
    assert p.failure_code == "" and "already open on your phone" not in failure(p)["failure_message"]
    [alert] = Alert.objects.filter(kind="payment")  # once, however many guests try
    assert alert.severity == "high" and alert.summary.startswith("Daraja is misconfigured") and message in alert.summary
    assert Message.objects.filter(phone=host.phone, kind="alert").count() == 1


def test_a_token_another_worker_replaced_is_fetched_again_once(unit, guest, settings):
    _live_daraja(settings)
    b = hold(unit, guest)
    stale = (404, {"requestId": "1", "errorCode": "404.001.03", "errorMessage": "Invalid Access Token"})
    cache.set("daraja_token", "old")  # each new token invalidates the previous one
    fake = FakeDaraja(stale, (200, {"ResponseCode": "0", "CheckoutRequestID": "ws_CO_fresh"}))
    with mock.patch("apps.payments.providers.httpx.Client", fake):
        payments.start_payment(b, method="mpesa")
    assert [s["auth"] for s in fake.sent] == ["Bearer old", "Bearer tok1"] and cache.get("daraja_token") == "tok1"
    p = Payment.objects.get(booking=b)
    assert (p.status, p.transaction_id) == ("pending", "ws_CO_fresh")

    cache.set("daraja_token", "old")
    fake = FakeDaraja((401, {}), (200, {"ResponseCode": "0", "ResultCode": "1032", "ResultDesc": "Cancelled"}))
    with mock.patch("apps.payments.providers.httpx.Client", fake):
        assert DarajaMpesa().query(p)["ResultCode"] == "1032"
    assert [s["auth"] for s in fake.sent] == ["Bearer old", "Bearer tok1"]

    cache.set("daraja_token", "old")
    fake = FakeDaraja(stale, (200, {"ResponseCode": "0", "ResponseDescription": "Success"}))
    with mock.patch("apps.payments.providers.httpx.Client", fake):
        assert c2b.register_c2b_urls("600981")["response"]["ResponseDescription"] == "Success"
    assert [s["auth"] for s in fake.sent] == ["Bearer old", "Bearer tok1"]


def test_the_stk_push_for_a_till_with_a_kenya_time_stamp_and_the_shared_secret(unit, guest, settings):
    _live_daraja(settings)
    settings.DARAJA_SHORTCODE, settings.DARAJA_PASSKEY, settings.DARAJA_CALLBACK_SECRET = "4123456", "pk", "d4r4j4"
    settings.DARAJA_TRANSACTION_TYPE, settings.DARAJA_PARTY_B = "CustomerBuyGoodsOnline", "5123456"
    p = daraja_prompt(hold(unit, guest))
    fake = FakeDaraja((200, {"ResponseCode": "0", "CheckoutRequestID": "ws_CO_till"}))
    with (
        mock.patch("apps.payments.providers.httpx.Client", fake),
        frozen(datetime(2026, 11, 25, 21, 30, tzinfo=UTC)),
    ):
        DarajaMpesa().request(p)
    body = fake.sent[0]["body"]
    assert (body["BusinessShortCode"], body["TransactionType"], body["PartyB"]) == (
        "4123456",
        "CustomerBuyGoodsOnline",
        "5123456",
    )
    assert body["Timestamp"] == "20261126003000"  # 00:30 in Nairobi, whatever zone the server runs in
    assert base64.b64decode(body["Password"]).decode() == "4123456pk20261126003000"
    assert body["CallBackURL"] == "https://stays.example.co.ke/api/payments/daraja/callback/d4r4j4"
    assert payments.paybill_number() is None  # a Till takes no account number: no Paybill to fall back on

    settings.DARAJA_TRANSACTION_TYPE, settings.DARAJA_PARTY_B = "CustomerPayBillOnline", ""
    fake = FakeDaraja((200, {"ResponseCode": "0", "CheckoutRequestID": "ws_CO_paybill"}))
    with mock.patch("apps.payments.providers.httpx.Client", fake):
        DarajaMpesa().request(daraja_prompt(hold(unit, guest, ci=30)))
    assert (fake.sent[0]["body"]["TransactionType"], fake.sent[0]["body"]["PartyB"]) == (
        "CustomerPayBillOnline",
        "4123456",
    )
    assert payments.paybill_number() == "4123456"


def test_one_secret_guards_the_stk_and_paybill_callbacks(client, unit, guest, settings):
    settings.DARAJA_CALLBACK_SECRET = "d4r4j4"  # and no AT_WEBHOOK_SECRET
    b = hold(unit, guest)
    p = prompt(b, checkout_id="ws_CO_shared")
    for secret in ("cb", "guess", "caf%C3%A9"):
        url = f"/api/payments/daraja/callback/{secret}"
        assert client.post(url, daraja_result(p, 0), content_type=JSON).status_code == 403
    assert Payment.objects.get(pk=p.pk).status == "pending"
    r = client.post("/api/payments/daraja/callback/d4r4j4", daraja_result(p, 0), content_type=JSON)
    assert r.status_code == 200 and Booking.objects.get(pk=b.pk).status == "confirmed"
    assert c2b.c2b_urls()["confirmation"].endswith("/c2b/confirmation/d4r4j4")


def test_a_non_ascii_secret_or_signature_is_refused_not_a_server_error(client, unit, foreign_guest, settings):
    settings.AT_WEBHOOK_SECRET = "s3cret"
    for url in ("/api/payments/at/callback/caf%C3%A9", "/api/payments/daraja/c2b/confirmation/caf%C3%A9"):
        assert client.post(url, "{}", content_type=JSON).status_code == 403
    _, _, body, _ = _paystack_card(unit, foreign_guest, settings)
    assert client.post(PAYSTACK, body, content_type=JSON, HTTP_X_PAYSTACK_SIGNATURE="é").status_code == 403


def test_a_paybill_notice_for_a_prompt_settled_by_stk_query_is_the_same_money(client, unit, guest, settings):
    b = hold(unit, guest)
    p = prompt(b, checkout_id="ws_CO_query")
    Payment.objects.filter(pk=p.pk).update(provider="daraja", created_at=timezone.now() - timedelta(minutes=3))
    settings.MPESA_PROVIDER = "daraja"
    with mock.patch.object(DarajaMpesa, "query", return_value={"ResultCode": "0", "ResultDesc": "Processed"}):
        payments.reconcile_pending()
    b.refresh_from_db()
    assert b.amount_paid == b.total and Payment.objects.get(pk=p.pk).provider_ref == ""  # Query has no receipt

    later = c2b_payload(b.ref, b.total, "SLATE00001")  # the same amount hours away from the prompt: more money
    later["TransTime"] = (timezone.localtime() + timedelta(hours=2)).strftime("%Y%m%d%H%M%S")
    client.post(C2B.format("confirmation"), json.dumps(later), content_type=JSON)
    b.refresh_from_db()
    assert b.amount_paid == 2 * b.total and Refund.objects.get(booking=b).amount == b.total

    echo = c2b_payload(b.ref, b.total, "SQRY000001")  # the prompt's own payment, echoed to the Paybill
    client.post(C2B.format("confirmation"), json.dumps(echo), content_type=JSON)
    b.refresh_from_db()
    t = C2BTransaction.objects.get(trans_id="SQRY000001")
    assert (t.status, t.payment_id) == ("matched", p.pk) and Payment.objects.get(pk=p.pk).provider_ref == "SQRY000001"
    assert b.amount_paid == 2 * b.total and b.payments.count() == 2 and Refund.objects.filter(booking=b).count() == 1
    # matched by amount and time, not by M-Pesa code: Amina checks her statement
    alert = Alert.objects.get(booking=b, summary__startswith="Check M-Pesa")
    assert "SQRY000001" in alert.summary and f"refund {kes(b.total)}" in alert.summary


def test_a_prompt_settled_by_stk_query_after_its_paybill_echo_counts_once(client, unit, guest, settings):
    b = hold(unit, guest)
    p = prompt(b, checkout_id="ws_CO_rev")
    Payment.objects.filter(pk=p.pk).update(provider="daraja", created_at=timezone.now() - timedelta(minutes=3))
    # the prompt's callback never comes, but its money is echoed to the Paybill and confirms the stay
    client.post(C2B.format("confirmation"), json.dumps(c2b_payload(b.ref, b.total, "SREV000001")), content_type=JSON)
    b.refresh_from_db()
    assert b.status == "confirmed" and b.amount_paid == b.total
    before = Message.objects.order_by("-id").values_list("id", flat=True).first()
    settings.MPESA_PROVIDER = "daraja"
    with mock.patch.object(DarajaMpesa, "query", return_value={"ResultCode": "0", "ResultDesc": "Processed"}):
        payments.reconcile_pending()  # STK Query: paid, with no M-Pesa code to tell the two apart
    b.refresh_from_db()
    assert b.amount_paid == b.total and not Refund.objects.filter(booking=b).exists()
    assert Payment.objects.get(pk=p.pk).status == "cancelled"
    assert not Message.objects.filter(id__gt=before, phone=guest.phone, kind__in=("refund_queued", "payment_received"))
    alert = Alert.objects.get(booking=b, summary__startswith="Check M-Pesa")
    assert "SREV000001" in alert.summary and f"refund {kes(b.total)}" in alert.summary


def test_a_same_amount_prompt_that_the_stay_still_needs_is_flagged_to_be_recorded(client, unit, guest, settings):
    b = hold(unit, guest, payment_plan="deposit")
    deposit = b.amount_due_now
    client.post(C2B.format("confirmation"), json.dumps(c2b_payload(b.ref, deposit, "SDEP000001")), content_type=JSON)
    b.refresh_from_db()
    assert b.status == "confirmed" and b.balance_due >= deposit
    p = prompt(b, checkout_id="ws_CO_bal", amount=deposit)  # a second payment of the same amount, for the balance
    Payment.objects.filter(pk=p.pk).update(provider="daraja", created_at=timezone.now() - timedelta(minutes=3))
    settings.MPESA_PROVIDER = "daraja"
    with mock.patch.object(DarajaMpesa, "query", return_value={"ResultCode": "0", "ResultDesc": "Processed"}):
        payments.reconcile_pending()
    alert = Alert.objects.get(booking=b, summary__startswith="Check M-Pesa")
    assert "record the second one on the reservation" in alert.summary and "refund" not in alert.summary


def test_a_late_receipt_for_a_prompt_settled_by_stk_query_is_kept(client, unit, guest, settings):
    b = hold(unit, guest)
    p = prompt(b, checkout_id="ws_CO_late")
    Payment.objects.filter(pk=p.pk).update(provider="daraja", created_at=timezone.now() - timedelta(minutes=3))
    settings.MPESA_PROVIDER = "daraja"
    with mock.patch.object(DarajaMpesa, "query", return_value={"ResultCode": "0", "ResultDesc": "Processed"}):
        payments.reconcile_pending()
    client.post(DARAJA, daraja_result(p, 0, receipt="SLATERCPT1"), content_type=JSON)
    assert Payment.objects.get(pk=p.pk).provider_ref == "SLATERCPT1"
    client.post(C2B.format("confirmation"), json.dumps(c2b_payload(b.ref, b.total, "SLATERCPT1")), content_type=JSON)
    b.refresh_from_db()
    assert b.amount_paid == b.total and C2BTransaction.objects.get().status == "matched"
    assert not Alert.objects.filter(summary__startswith="Check M-Pesa").exists()  # matched by its M-Pesa code


@pytest.mark.parametrize(
    ("public_url", "secret", "why"),
    [
        ("http://aminastays.co.ke", "s3cret", "own https:// domain"),
        ("https://abc123.ngrok-free.app", "s3cret", "tunnel hosts like abc123.ngrok-free.app"),
        ("https://amina.trycloudflare.com", "s3cret", "tunnel hosts"),
        ("https://mpesa.aminastays.co.ke", "s3cret", "containing 'mpesa'"),
        ("https://aminastays.co.ke", "SqlQuery", "containing 'sql' or 'query'"),
        ("https://aminastays.co.ke", "exec", "containing 'exe' or 'exec'"),
    ],
)
def test_register_c2b_refuses_urls_safaricom_blocks_in_production(settings, public_url, secret, why):
    _live_daraja(settings)
    settings.DARAJA_ENV, settings.PUBLIC_URL, settings.AT_WEBHOOK_SECRET = "production", public_url, secret
    with mock.patch("apps.payments.providers.httpx.Client", side_effect=AssertionError("nothing is registered")):
        with pytest.raises(PaymentError, match=why):
            c2b.register_c2b_urls("522533")


def test_a_tunnel_is_fine_for_a_sandbox_registration(settings):
    _live_daraja(settings)
    settings.PUBLIC_URL = "https://abc123.ngrok-free.app"
    with mock.patch("apps.payments.providers.httpx.Client", FakeDaraja((200, {"ResponseCode": "0"}))):
        assert c2b.register_c2b_urls("600981")["shortcode"] == "600981"


# ---------- going live: the rest of Daraja's result codes ----------


@pytest.mark.parametrize(
    ("code", "suggest", "retryable", "words"),
    [
        (17, "wait", True, "Wait 2 minutes, then resend"),
        (2, "card", False, "Please pay by card"),
        (3, "deposit", False, "Pay by card, or pay only the 30% deposit"),
        (4, "deposit", False, "daily M-Pesa limit"),
        (8, "deposit", False, "balance limit"),
    ],
)
def test_limit_and_repeat_codes_get_their_own_next_step(client, unit, guest, code, suggest, retryable, words):
    b = hold(unit, guest, ci=20)  # far enough ahead for a deposit
    p = prompt(b, checkout_id=f"ws_CO_rule{code}")
    client.post(DARAJA, daraja_result(p, code, desc="Declined due to limit rule"), content_type=JSON)
    info = failure(p)
    assert (info["failure_code"], info["suggest"], info["retryable"]) == (str(code), suggest, retryable)
    assert words in info["failure_message"] and "don't pay again" not in info["failure_message"]
    assert not Alert.objects.exists()


@pytest.mark.parametrize("code", ["2028", "SFC_IC0003"])
def test_a_wrong_transaction_type_or_party_b_alerts_amina(client, unit, host, code):
    juma = User.objects.create_user("+254722000778", name="Juma", lang="sw")
    b = hold(unit, juma, channel="sms")
    p = prompt(b, checkout_id=f"ws_CO_{code}")
    client.post(DARAJA, daraja_result(p, code, desc="The request is not permitted"), content_type=JSON)
    info = failure(p)
    assert (info["suggest"], info["retryable"]) == ("card", False) and "Amina has been told" in info["failure_message"]
    alert = Alert.objects.get(kind="payment")
    assert alert.severity == "high" and "DARAJA_TRANSACTION_TYPE" in alert.summary
    [body] = Message.objects.filter(phone=juma.phone, kind="payment_failed").values_list("body", flat=True)
    assert "tatizo la mipangilio yetu ya M-Pesa" in body


# ---------- going live: Paystack is answered before Verify Transaction runs ----------


def test_the_paystack_webhook_answers_before_verify_transaction_runs(
    client, unit, foreign_guest, settings, django_capture_on_commit_callbacks
):
    b, p, body, sig = _paystack_card(unit, foreign_guest, settings)
    settings.PAYMENTS_INLINE = False  # production: no Paystack call inside the webhook
    with mock.patch.object(PaystackCard, "query", return_value=verified(p)) as verify:
        with django_capture_on_commit_callbacks() as callbacks:
            r = client.post(PAYSTACK, body, content_type=JSON, HTTP_X_PAYSTACK_SIGNATURE=sig)
        assert r.status_code == 200 and not verify.called and Payment.objects.get(pk=p.pk).status == "pending"
        with (
            mock.patch.object(deferred._executor, "submit", side_effect=lambda fn, *args: fn(*args)),
            mock.patch("apps.comms.deferred.close_old_connections"),
        ):
            for callback in callbacks:
                callback()
    verify.assert_called_once()
    assert Payment.objects.get(pk=p.pk).status == "success" and Booking.objects.get(pk=b.pk).status == "confirmed"
