"""New booking flows: the web waitlist (C1), deposit switch and payment-failure fields on the trip (C2), the overdue
balance flag (C3), changing / extending a reservation on the web, by SMS and through Amina (C4), and manual host
bookings with a deposit or an agreed price (C8)."""

import threading
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import timedelta
from unittest import mock

import pytest
from django.conf import settings as django_settings
from django.db import connection, transaction
from django.db.models import F
from django.utils import timezone

from apps.accounts.models import User
from apps.bookings import services as bookings
from apps.bookings.models import Addon, Booking, ChangeRequest, Waitlist
from apps.core.models import SiteSettings
from apps.core.utils import at_local, kes
from apps.messaging.models import Message
from apps.operations.models import Task
from apps.payments import services as payments
from apps.payments.models import Payment, Refund
from apps.properties.services import quote as price_quote
from apps.safety.models import Alert

from .conftest import days
from .flowkit import bodies, frozen, last_id, make_user, sms, stay

pytestmark = pytest.mark.django_db

HOST = "+254700000001"  # conftest's AMINA_PHONE: a developer's .env may set their own number


def settle(p):
    """The provider's success callback for a payment (payments then applies the change it paid for)."""
    payments.on_success(p, transaction_id=f"QF{p.pk}", provider_ref=f"QF{p.pk}")
    p.refresh_from_db()
    return p


def instant_changes_off(monkeypatch):
    s = SiteSettings.load()
    if any(f.name == "instant_changes" for f in SiteSettings._meta.get_fields()):
        s.instant_changes = False
        s.save()
    else:
        monkeypatch.setattr(SiteSettings, "instant_changes", False, raising=False)


def guest_sms(user, kind, after=0):
    return bodies(user.phone, after, kind=kind)


# ---------- C1: the web waitlist ----------


def test_waitlist_join_list_and_leave(unit, guest, guest_api, api):
    other = make_user("+254733000111", name="Early Bird")
    stay(unit, other, days(10), days(13))
    body = {"slug": unit.slug, "check_in": days(10).isoformat(), "check_out": days(12).isoformat(), "adults": 2}
    before = last_id()

    r = guest_api.post("/api/waitlist", {**body, "children": 1}, format="json")
    assert r.status_code == 201, r.data
    entry = r.data
    assert entry == {
        "id": entry["id"],
        "status": "waiting",
        "unit": {"slug": unit.slug, "name": "Palm Suite", "area": "Diani", "photo": ""},
        "area": {"slug": "diani", "name": "Diani"},
        "check_in": days(10),
        "check_out": days(12),
        "nights": 2,
        "guests": 3,
        "created_at": entry["created_at"],
        "offered_at": None,
        "book_url": None,
    }
    w = Waitlist.objects.get(pk=entry["id"])
    assert (w.adults, w.children, w.guests, w.channel) == (2, 1, 3, "web")
    [joined] = guest_sms(guest, "waitlist_joined", before)
    assert joined == "You're on the waitlist for Palm Suite, " + bookings.dates_text(days(10), days(12)) + (
        ". We'll text you the moment it opens up."
    )

    again = guest_api.post("/api/waitlist", {**body, "children": 1}, format="json")
    assert again.status_code == 200 and again.data["id"] == entry["id"]
    assert len(guest_sms(guest, "waitlist_joined", before)) == 1  # asking twice doesn't text twice

    assert [e["id"] for e in guest_api.get("/api/me/waitlist").data] == [entry["id"]]
    outsider = api
    outsider.force_authenticate(other)
    assert outsider.get("/api/me/waitlist").data == []
    assert outsider.delete(f"/api/me/waitlist/{entry['id']}").status_code == 404
    assert guest_api.delete(f"/api/me/waitlist/{entry['id']}").status_code == 204
    assert guest_api.get("/api/me/waitlist").data == []


def test_waitlist_rejects_free_past_and_impossible_requests(unit, guest, guest_api, api):
    def join(ci, co, **extra):
        return guest_api.post(
            "/api/waitlist",
            {"slug": unit.slug, "check_in": ci.isoformat(), "check_out": co.isoformat(), "adults": 1, **extra},
            format="json",
        )

    r = join(days(5), days(7))
    assert r.status_code == 400
    assert r.data == {"error": "Good news - those dates are free. You can book them now.", "code": "available"}
    assert join(days(-2), days(1)).status_code == 400
    assert join(days(5), days(5)).status_code == 400
    stay(unit, make_user("+254733000112"), days(5), days(8))
    r = join(days(5), days(7), adults=5)
    assert r.status_code == 400 and "sleeps up to 4" in r.data["error"]
    assert guest_api.post("/api/waitlist", {"slug": "nowhere", "check_in": days(5).isoformat()}).status_code == 404
    assert api.post("/api/waitlist", {"slug": unit.slug}, format="json").status_code in (401, 403)
    assert not Waitlist.objects.exists()


def test_waitlist_offer_texts_a_booking_link_and_clears_once_booked(unit, guest, guest_api):
    taken = stay(unit, make_user("+254733000113", name="First Guest"), days(20), days(23))
    r = guest_api.post(
        "/api/waitlist",
        {
            "slug": unit.slug,
            "check_in": days(20).isoformat(),
            "check_out": days(22).isoformat(),
            "adults": 2,
            "children": 1,
        },
        format="json",
    )
    before = last_id()
    bookings.cancel(taken, by="guest")
    path = f"/book/{unit.slug}?check_in={days(20).isoformat()}&check_out={days(22).isoformat()}&adults=2&children=1"
    [offer] = guest_sms(guest, "waitlist_offer", before)
    assert offer.startswith("Good news! Palm Suite") and f"{django_settings.FRONTEND_URL}{path}" in offer

    [entry] = guest_api.get("/api/me/waitlist").data
    assert entry["id"] == r.data["id"] and entry["status"] == "offered" and entry["book_url"] == path
    assert entry["offered_at"] is not None

    # someone else got there first: the entry goes back to waiting for the next opening
    rival = stay(unit, make_user("+254733000114"), days(20), days(22))
    [entry] = guest_api.get("/api/me/waitlist").data
    assert (entry["status"], entry["book_url"]) == ("waiting", None)

    bookings.cancel(rival, by="guest")
    assert Waitlist.objects.get(pk=entry["id"]).status == "offered"
    stay(unit, guest, days(20), days(22), adults=2)
    assert Waitlist.objects.get(pk=entry["id"]).status == "booked"
    assert guest_api.get("/api/me/waitlist").data == []


def test_sms_waitlist_offers_carry_the_link_too(unit, other_unit):
    sms_guest = make_user("+254733000115")
    stay(other_unit, make_user("+254733000116"), days(4), days(6))
    w = bookings.add_to_waitlist(sms_guest, days(4), days(6), area=other_unit.area, guests=2, channel="sms")
    unit.status = "paused"
    unit.save()
    before = last_id()
    assert bookings.notify_waitlist(unit) == 0  # a paused home is never offered
    other_unit.bookings.update(status="cancelled")
    assert bookings.notify_waitlist(other_unit) == 1
    [offer] = bodies(sms_guest.phone, before, kind="waitlist_offer")
    link = f"/book/{other_unit.slug}?check_in={days(4).isoformat()}&check_out={days(6).isoformat()}&adults=2"
    assert f"{django_settings.FRONTEND_URL}{link}" in offer
    w.refresh_from_db()
    assert (w.status, w.offered_unit) == ("offered", other_unit)


# ---------- C3: overdue balance flag ----------


def test_balance_overdue_once_the_due_date_passes(unit, guest, guest_api, site):
    b = stay(unit, guest, days(10), days(12), plan="deposit")
    assert b.balance_due > 0
    due = b.check_in - timedelta(days=site.balance_due_days)
    trip = guest_api.get(f"/api/bookings/{b.ref}").data
    assert trip["price"]["balance_due_date"] == due and trip["price"]["balance_overdue"] is False
    with frozen(at_local(due, "23:00")):
        assert guest_api.get(f"/api/bookings/{b.ref}").data["price"]["balance_overdue"] is False
    with frozen(at_local(due + timedelta(days=1), "07:00")):
        assert guest_api.get(f"/api/bookings/{b.ref}").data["price"]["balance_overdue"] is True
        payments.record_manual_payment(b, b.balance_due)
        assert guest_api.get(f"/api/bookings/{b.ref}").data["price"]["balance_overdue"] is False


# ---------- C2: pay a deposit instead, payment failure fields ----------


def test_held_booking_can_switch_to_paying_the_deposit(unit, guest, guest_api, site):
    b = bookings.create_hold(unit=unit, guest=guest, check_in=days(10), check_out=days(13), channel="web")
    payments.start_payment(b)
    Payment.objects.filter(booking=b).update(status="failed", failure_reason="insufficient M-Pesa balance")
    r = guest_api.post(f"/api/bookings/{b.ref}/pay", {"method": "mpesa", "plan": "deposit"}, format="json")
    assert r.status_code == 200, r.data
    b.refresh_from_db()
    deposit = -(-b.total * site.deposit_percent // 100)
    assert (b.payment_plan, b.amount_due_now) == ("deposit", deposit)
    assert (r.data["amount"], r.data["purpose"], r.data["status"]) == (deposit, "deposit", "pending")

    trip = guest_api.get(f"/api/bookings/{b.ref}").data
    assert [p["status"] for p in trip["payments"]] == ["pending", "failed"]  # newest first
    for p in trip["payments"]:
        assert {"failure_code", "failure_message", "retryable", "suggest"} <= set(p)

    soon = bookings.create_hold(unit=unit, guest=guest, check_in=days(1), check_out=days(2), channel="web")
    r = guest_api.post(f"/api/bookings/{soon.ref}/pay", {"method": "mpesa", "plan": "deposit"}, format="json")
    assert r.status_code == 400 and r.data["error"] == "A deposit isn't available for this stay."
    assert {"failure_code", "suggest"} <= set(r.data)
    soon.refresh_from_db()
    assert soon.payment_plan == "full"


# ---------- C4: changing a reservation ----------


@pytest.fixture
def booked(unit, guest):
    """Palm Suite (10,000/night, 2,000 cleaning, flexible), three nights in ten days, paid in full."""
    return stay(unit, guest, days(10), days(13), adults=2)


def quote_of(api, b, **params):
    r = api.get(f"/api/bookings/{b.ref}/change", params)
    assert r.status_code == 200, r.data
    return r.data


def test_change_quote_prices_the_new_stay_like_a_new_booking(unit, booked, guest_api):
    q = quote_of(guest_api, booked, check_out=days(14).isoformat())
    longer = price_quote(unit, days(10), days(14), guests=2)
    assert q == {
        "available": True,
        "reason": None,
        "nights": 4,
        "old_total": booked.total,
        "new_total": longer["total"],
        "delta": longer["total"] - booked.total,
        "pay_now": longer["total"] - booked.total,
        "refund": 0,
        "policy_text": bookings.POLICY_TEXT["flexible"],
        "instant": True,
        "lines": [{"label": ln["label"], "amount": ln["amount"]} for ln in longer["lines"]],
    }
    assert sum(ln["amount"] for ln in q["lines"]) == q["new_total"]

    # moving onto nights the booking itself holds is fine; someone else's nights are not
    assert quote_of(guest_api, booked, check_in=days(11).isoformat(), check_out=days(14).isoformat())["available"]
    stay(unit, make_user("+254733000201"), days(13), days(15))
    taken = quote_of(guest_api, booked, check_out=days(14).isoformat())
    assert (taken["available"], taken["reason"]) == (False, "Sorry - Palm Suite isn't free for all of those nights.")

    unit.min_nights, unit.max_guests = 3, 3
    unit.save()
    assert quote_of(guest_api, booked, check_out=days(12).isoformat())["reason"] == (
        "Palm Suite has a minimum stay of 3 nights."
    )
    assert quote_of(guest_api, booked, adults=2, children=2)["reason"] == "Palm Suite sleeps up to 3 guests."
    assert quote_of(guest_api, booked)["reason"] == "That's the same as your current booking."
    past = quote_of(guest_api, booked, check_in=days(-1).isoformat(), check_out=days(3).isoformat())
    assert past["reason"] == "That check-in date has already passed."
    assert guest_api.get(f"/api/bookings/{booked.ref}/change", {"check_in": "soon"}).status_code == 400


def test_dearer_change_waits_for_payment_then_applies(unit, guest, booked, guest_api):
    code = booked.access_codes.get()
    before = last_id()
    r = guest_api.post(
        f"/api/bookings/{booked.ref}/change", {"check_out": days(15).isoformat(), "note": "Flight moved"}, format="json"
    )
    assert r.status_code == 201, r.data
    longer = price_quote(unit, days(10), days(15), guests=2)
    delta = longer["total"] - booked.total
    change = r.data["change"]
    assert change == {
        "id": change["id"],
        "status": "pending_payment",
        "status_label": "Waiting for payment",
        "old": {"check_in": days(10), "check_out": days(13), "adults": 2, "children": 0},
        "new": {"check_in": days(10), "check_out": days(15), "adults": 2, "children": 0},
        "delta": delta,
        "refund_amount": 0,
        "pay_now": delta,
        "requested_by": "guest",
        "created_at": change["created_at"],
        "expires_at": change["expires_at"],
    }
    assert (r.data["payment"]["method"], r.data["payment"]["amount"], r.data["payment"]["purpose"]) == (
        "mpesa",
        delta,
        "change",
    )
    trip = r.data["trip"]
    assert trip["check_out"] == days(13) and trip["can_change"] and trip["changes"][0]["id"] == change["id"]
    assert not guest_sms(guest, "change_requested", before)  # on the web the page and the phone prompt say it all

    p = Payment.objects.get(pk=r.data["payment"]["payment_id"])
    c = ChangeRequest.objects.get(pk=change["id"])
    assert c.payment_id == p.pk and c.note == "Flight moved"
    paid_before = booked.amount_paid
    settle(p)
    bookings.on_change_paid(p)  # payments calls this; a second call changes nothing
    booked.refresh_from_db()
    c.refresh_from_db()
    assert c.status == "applied" and c.applied_at is not None
    assert (booked.check_in, booked.check_out, booked.total) == (days(10), days(15), longer["total"])
    assert (booked.amount_paid, booked.balance_due, booked.payment_status) == (paid_before + delta, 0, "paid")
    assert not booked.refunds.exists()
    code.refresh_from_db()
    assert code.valid_until == at_local(days(15), "11:00") + timedelta(minutes=30)
    [applied] = guest_sms(guest, "change_applied", before)
    assert applied.startswith(f"Done! {booked.ref} at Palm Suite is now {bookings.dates_text(days(10), days(15))}")
    assert any(e.kind == "change" and "Stay changed" in e.text for e in booked.events.all())
    assert any(f"{booked.ref} (Palm Suite) changed by the guest" in m for m in bodies(HOST, before))
    trip = guest_api.get(f"/api/bookings/{booked.ref}").data
    assert trip["changes"][0]["status"] == "applied" and trip["changes"][0]["pay_now"] == 0
    assert any(e["kind"] == "change" for e in trip["timeline"])


@pytest.mark.django_db(transaction=True)
def test_the_money_for_a_change_commits_with_the_change(booked, guest, guest_api):
    c, pay = bookings.request_change(booked, check_in=days(10), check_out=days(15), actor=guest)
    p = Payment.objects.get(pk=pay["payment_id"])
    trips, armed, real_event = [], [], bookings.event

    def event(b, kind, *args, **kw):
        if kind == "payment" and not armed:  # inside the transaction that counts the money:
            armed.append(True)  # read the trip the moment it commits
            transaction.on_commit(lambda: trips.append(guest_api.get(f"/api/bookings/{b.ref}").data))
        return real_event(b, kind, *args, **kw)

    with mock.patch.object(bookings, "event", event):
        settle(p)
    [trip] = trips
    assert (trip["changes"][0]["status"], trip["check_out"], trip["price"]["total"]) == (
        "applied",
        days(15),
        c.new_total,
    )
    assert (trip["price"]["amount_paid"], trip["price"]["balance_due"]) == (c.new_total, 0)
    assert next(x["status"] for x in trip["payments"] if x["id"] == p.pk) == "success"


@pytest.mark.django_db(transaction=True)
def test_a_trip_read_while_the_change_is_being_paid_shows_one_state(booked, guest, guest_api):
    from apps.bookings import serializers

    c, pay = bookings.request_change(booked, check_in=days(10), check_out=days(15), actor=guest)
    p = Payment.objects.get(pk=pay["payment_id"])
    booking_read, carry_on = threading.Event(), threading.Event()
    real_payments = serializers._payments

    def payments_list(b):  # the trip has read the booking row: the payment races the rest of the read
        booking_read.set()
        carry_on.wait(10)
        return real_payments(b)

    def own_connection(fn):
        try:
            return fn()
        finally:
            connection.close()

    with mock.patch.object(serializers, "_payments", payments_list), ThreadPoolExecutor(2) as pool:
        reading = pool.submit(own_connection, lambda: guest_api.get(f"/api/bookings/{booked.ref}").data)
        assert booking_read.wait(10)
        paying = pool.submit(own_connection, lambda: settle(p))
        wait([paying], timeout=1)  # the trip holds the booking, so the payment waits for it
        carry_on.set()
        trip = reading.result(10)
        paying.result(10)
    payment = next(x["status"] for x in trip["payments"] if x["id"] == p.pk)
    assert (trip["changes"][0]["status"], trip["check_out"], payment) == ("pending_payment", days(13), "pending")
    booked.refresh_from_db()
    assert (booked.check_out, ChangeRequest.objects.get(pk=c.pk).status) == (days(15), "applied")


def test_cheaper_change_applies_now_and_refunds_under_the_policy(unit, guest, booked, guest_api):
    shorter = price_quote(unit, days(10), days(12), guests=2)
    q = quote_of(guest_api, booked, check_out=days(12).isoformat())
    assert (q["delta"], q["pay_now"], q["refund"]) == (
        shorter["total"] - booked.total,
        0,
        booked.total - shorter["total"],
    )
    before = last_id()
    r = guest_api.post(f"/api/bookings/{booked.ref}/change", {"check_out": days(12).isoformat()}, format="json")
    assert r.status_code == 201 and r.data["payment"] is None
    assert (r.data["change"]["status"], r.data["change"]["refund_amount"]) == ("applied", q["refund"])
    booked.refresh_from_db()
    assert (booked.check_out, booked.total) == (days(12), shorter["total"])
    [refund] = Refund.objects.filter(booking=booked)
    assert (refund.status, refund.amount) == ("pending", q["refund"])  # Amina's refund queue
    assert bookings.owed(booked) == 0
    [applied] = guest_sms(guest, "change_applied", before)
    assert f"Refund of {kes(q['refund'])} is on its way." in applied
    assert not guest_sms(guest, "refund_queued", before)  # one message, not two


def test_nights_taken_off_late_are_partly_kept(other_unit, guest, guest_api):
    """Reef Studio is on the moderate policy: inside five days, nights taken off are refunded at 50%."""
    b = stay(other_unit, guest, days(2), days(6))
    q = quote_of(guest_api, b, check_out=days(4).isoformat())
    plain = price_quote(other_unit, days(2), days(4), guests=1)["total"]
    removed = b.total - plain
    assert abs(q["refund"] - removed / 2) <= 1 and abs(q["new_total"] - (plain + removed / 2)) <= 1
    assert q["new_total"] + q["refund"] == b.total
    assert any(ln["label"] == "Kept under the cancellation policy" for ln in q["lines"])
    assert sum(ln["amount"] for ln in q["lines"]) == q["new_total"]
    assert "50% refundable" in q["policy_text"]
    r = guest_api.post(f"/api/bookings/{b.ref}/change", {"check_out": days(4).isoformat()}, format="json")
    assert r.data["change"]["refund_amount"] == q["refund"]
    b.refresh_from_db()
    trip = r.data["trip"]
    assert trip["price"]["total"] == q["new_total"] and sum(ln["amount"] for ln in trip["price"]["lines"]) == b.total
    assert {"label": "Kept under the cancellation policy", "amount": bookings.kept_amount(b)} in trip["price"]["lines"]
    # the kept money stays on the bill: a later re-total doesn't hand it back
    bookings.recalc(b)
    assert Refund.objects.filter(booking=b).count() == 1 and bookings.owed(b) == 0


def test_in_house_guests_can_only_extend(unit, guest, guest_api):
    b = stay(unit, guest, days(0), days(2), adults=2, checked_in=True)
    task = Task.objects.create(
        type="turnover", title="Turnover clean", unit=unit, booking=b, due_at=at_local(days(2), "12:00")
    )
    assert quote_of(guest_api, b, check_in=days(1).isoformat(), check_out=days(4).isoformat())["reason"] == (
        "You're already checked in - you can extend your stay, but not move it."
    )
    assert (
        quote_of(guest_api, b, check_out=days(1).isoformat())["reason"]
        == "Leaving early? Just check out, or message Amina."
    )
    assert (
        quote_of(guest_api, b, adults=3)["reason"] == "To change the number of guests during your stay, message Amina."
    )
    r = guest_api.post(f"/api/bookings/{b.ref}/change", {"check_out": days(3).isoformat()}, format="json")
    c = ChangeRequest.objects.get(pk=r.data["change"]["id"])
    assert c.expires_at <= at_local(days(2), "11:00")  # settled before today's checkout or not at all
    settle(Payment.objects.get(pk=r.data["payment"]["payment_id"]))
    b.refresh_from_db()
    code = b.access_codes.get(revoked_at__isnull=True)
    assert (b.status, b.check_out) == ("checked_in", days(3))
    assert code.sent_at and code.valid_until == at_local(days(3), "11:00") + timedelta(minutes=30)
    task.refresh_from_db()
    assert task.due_at == at_local(days(3), "12:00")


def test_change_rules_for_other_bookings(unit, guest, guest_api):
    held = bookings.create_hold(unit=unit, guest=guest, check_in=days(5), check_out=days(7), channel="web")
    trip = guest_api.get(f"/api/bookings/{held.ref}").data
    assert (trip["can_change"], trip["changes"]) == (False, [])
    r = guest_api.post(f"/api/bookings/{held.ref}/change", {"check_out": days(8).isoformat()}, format="json")
    assert r.status_code == 400 and r.data["error"] == "This booking can't be changed any more."
    ota = stay(unit, guest, days(20), days(22), channel="airbnb")
    assert guest_api.get(f"/api/bookings/{ota.ref}").data["can_change"] is False
    assert quote_of(guest_api, ota, check_out=days(23).isoformat())["reason"] == (
        "This booking came through Airbnb - please change it there."
    )


def test_a_new_change_replaces_the_pending_one_and_can_be_withdrawn(unit, guest, booked, guest_api):
    first = guest_api.post(
        f"/api/bookings/{booked.ref}/change", {"check_out": days(14).isoformat()}, format="json"
    ).data
    second = guest_api.post(
        f"/api/bookings/{booked.ref}/change", {"check_out": days(15).isoformat()}, format="json"
    ).data
    old = ChangeRequest.objects.get(pk=first["change"]["id"])
    old_payment = Payment.objects.get(pk=first["payment"]["payment_id"])
    assert old.status == "cancelled" and old_payment.status == "cancelled"
    assert (
        second["payment"]["payment_id"] != old_payment.pk and second["payment"]["amount"] == second["change"]["delta"]
    )
    assert [c["id"] for c in second["trip"]["changes"]] == [second["change"]["id"], old.pk]

    r = guest_api.post(f"/api/bookings/{booked.ref}/change/{second['change']['id']}/cancel")
    assert r.status_code == 200 and r.data["changes"][0]["status"] == "cancelled"
    assert r.data["check_out"] == days(13)
    assert guest_api.post(f"/api/bookings/{booked.ref}/change/{second['change']['id']}/cancel").status_code == 400

    # the guest paid the withdrawn prompt after all: the money is queued to go back and Amina is alerted
    paid = booked.total
    settle(Payment.objects.get(pk=second["payment"]["payment_id"]))
    booked.refresh_from_db()
    assert (booked.check_out, booked.total) == (days(13), paid)
    [refund] = Refund.objects.filter(booking=booked, status="pending")
    assert refund.amount == second["change"]["delta"] and bookings.owed(booked) == 0
    assert Alert.objects.filter(booking=booked, kind="payment", severity="high").exists()


def test_paid_change_whose_dates_went_meanwhile_is_declined_and_refunded(unit, guest, booked, guest_api):
    r = guest_api.post(f"/api/bookings/{booked.ref}/change", {"check_out": days(15).isoformat()}, format="json").data
    stay(unit, make_user("+254733000202"), days(13), days(14))  # booked by someone else before the guest paid
    before = last_id()
    settle(Payment.objects.get(pk=r["payment"]["payment_id"]))
    booked.refresh_from_db()
    c = ChangeRequest.objects.get(pk=r["change"]["id"])
    assert (c.status, c.refund_amount) == ("declined", r["change"]["delta"])
    assert booked.check_out == days(13)
    assert Refund.objects.get(booking=booked).amount == r["change"]["delta"]
    assert Alert.objects.filter(booking=booked, severity="high", summary__contains="couldn't be made").exists()
    [declined] = guest_sms(guest, "change_declined", before)
    assert f"Refund of {kes(c.refund_amount)} is on its way." in declined


def test_change_payment_can_be_sent_again_or_by_card(booked, guest_api):
    r = guest_api.post(f"/api/bookings/{booked.ref}/change", {"check_out": days(14).isoformat()}, format="json").data
    cid = r["change"]["id"]
    card = guest_api.post(f"/api/bookings/{booked.ref}/change/{cid}/pay", {"method": "card"}, format="json")
    assert card.status_code == 200 and card.data["method"] == "card" and card.data["checkout_url"]
    c = ChangeRequest.objects.get(pk=cid)
    assert c.payment_id == card.data["payment_id"]
    # the earlier M-Pesa prompt is still on the phone: paying it applies the change all the same
    settle(Payment.objects.get(pk=r["payment"]["payment_id"]))
    c.refresh_from_db()
    assert c.status == "applied"
    again = guest_api.post(f"/api/bookings/{booked.ref}/change/{cid}/pay", {"method": "mpesa"}, format="json")
    assert again.status_code == 400 and again.data["error"] == "This change isn't waiting for a payment."


def test_foreign_guests_pay_a_change_by_card(unit, foreign_guest):
    b = stay(unit, foreign_guest, days(10), days(12))
    c, pay = bookings.request_change(b, check_in=days(10), check_out=days(13), actor=foreign_guest)
    assert pay["method"] == "card" and pay["checkout_url"] and c.status == "pending_payment"


def test_amina_approves_changes_when_instant_changes_are_off(
    monkeypatch, unit, guest, host, booked, guest_api, host_api
):
    instant_changes_off(monkeypatch)
    Addon.objects.create(code="late_checkout", name="Late checkout", price=1_500, requires_approval=True)
    late = bookings.add_addon(booked, "late_checkout", channel="web")
    before = last_id()
    r = guest_api.post(
        f"/api/bookings/{booked.ref}/change",
        {"check_out": days(14).isoformat(), "note": "One more night please"},
        format="json",
    )
    assert r.status_code == 201 and r.data["payment"] is None
    change = r.data["change"]
    assert (change["status"], change["pay_now"]) == ("pending_host", change["delta"])
    [ask] = bodies(HOST, before, kind="change_request")
    cid = change["id"]
    assert ask.startswith(f"CHANGE C{cid}: Wanjiru Test ({booked.ref}, Palm Suite) asks to change")
    assert ask.endswith(f'Note: "One more night please" Reply YES C{cid} or NO C{cid}.')
    [told] = guest_sms(guest, "change_requested", before)
    assert told.endswith("Amina will confirm by SMS shortly.") and f"(+{kes(change['delta'])})" in told

    requests = host_api.get("/api/host/requests").data
    item = next(x for x in requests if x["kind"] == "change")
    assert item == {
        "id": cid,
        "kind": "change",
        "addon": "Date change",
        "code": "change",
        "ref": booked.ref,
        "unit": "Palm Suite",
        "guest": "Wanjiru Test",
        "details": {"note": "One more night please"},
        "total": change["delta"],
        "created_at": item["created_at"],
        "change": {
            "old": {"check_in": days(10), "check_out": days(13), "adults": 2, "children": 0},
            "new": {"check_in": days(10), "check_out": days(14), "adults": 2, "children": 0},
            "delta": change["delta"],
            "refund_amount": 0,
        },
    }
    addon_item = next(x for x in requests if x["kind"] == "addon")
    assert (addon_item["id"], addon_item["code"]) == (late.pk, "late_checkout")

    # Amina says yes by SMS: the guest gets the M-Pesa prompt and pays, and the change is made
    before = last_id()
    [reply] = sms(f"YES C{cid}", phone=HOST)
    assert reply == f"Approved - waiting for the guest's payment: change C{cid} for {booked.ref}. Guest told."
    p = Payment.objects.get(booking=booked, purpose="change", status="pending")
    assert p.amount == change["delta"]
    [prompt] = guest_sms(guest, "change_requested", before)
    assert prompt.endswith(f"Pay {kes(change['delta'])} to confirm - check your phone for the M-Pesa prompt.")
    settle(p)
    booked.refresh_from_db()
    assert booked.check_out == days(14) and ChangeRequest.objects.get(pk=cid).status == "applied"
    assert sms(f"YES C{cid}", phone=HOST) == [f"C{cid}: This change has already been dealt with."]

    # and no from the console
    r = guest_api.post(f"/api/bookings/{booked.ref}/change", {"check_in": days(11).isoformat()}, format="json")
    cid = r.data["change"]["id"]
    before = last_id()
    r = host_api.post(f"/api/host/changes/{cid}/decide", {"approve": False}, format="json")
    assert r.status_code == 200 and r.data["changes"][0]["status"] == "declined" and r.data["check_in"] == days(10)
    [declined] = guest_sms(guest, "change_declined", before)
    assert declined.startswith(f"Sorry - we couldn't change {booked.ref} to {bookings.dates_text(days(11), days(14))}.")
    assert host_api.post(f"/api/host/changes/{cid}/decide", {"approve": True}, format="json").status_code == 400
    assert not [x for x in host_api.get("/api/host/requests").data if x["kind"] == "change"]


def test_approving_a_cheaper_change_applies_it_and_a_gone_date_declines_it(
    monkeypatch, unit, guest, booked, host_api, guest_api
):
    instant_changes_off(monkeypatch)
    c, _ = bookings.request_change(booked, check_in=days(10), check_out=days(12), actor=guest)
    assert c.status == "pending_host"
    r = host_api.post(f"/api/host/changes/{c.pk}/decide", {"approve": True}, format="json")
    assert r.status_code == 200 and r.data["check_out"] == days(12)
    c.refresh_from_db()
    assert c.status == "applied" and c.refund_amount > 0
    c2, _ = bookings.request_change(booked, check_in=days(10), check_out=days(14), actor=guest)
    stay(unit, make_user("+254733000203"), days(12), days(14))
    r = host_api.post(f"/api/host/changes/{c2.pk}/decide", {"approve": True}, format="json")
    assert r.status_code == 400 and "aren't free any more" in r.data["error"]
    assert ChangeRequest.objects.get(pk=c2.pk).status == "declined"


def test_stale_changes_expire_and_a_missed_payment_hook_is_caught(booked, guest):
    c, pay = bookings.request_change(booked, check_in=days(10), check_out=days(14), actor=guest)
    p = Payment.objects.get(pk=pay["payment_id"])
    with frozen(timezone.now() + timedelta(hours=49)):
        assert bookings.expire_stale_changes() == 1
    c.refresh_from_db()
    p.refresh_from_db()
    assert (c.status, p.status) == ("expired", "cancelled")

    c2, pay2 = bookings.request_change(booked, check_in=days(10), check_out=days(14), actor=guest)
    p2 = Payment.objects.get(pk=pay2["payment_id"])
    Payment.objects.filter(pk=p2.pk).update(status="success")  # money in, but the change was never applied
    Booking.objects.filter(pk=booked.pk).update(amount_paid=booked.amount_paid + p2.amount)
    assert bookings.expire_stale_changes() == 0
    c2.refresh_from_db()
    booked.refresh_from_db()
    assert c2.status == "applied" and booked.check_out == days(14) and booked.balance_due == 0


def test_sms_extend_creates_the_change(monkeypatch, unit, host):
    phone = "+254722000909"
    guest = make_user(phone, name="Juma Guest")
    b = stay(unit, guest, days(0), days(2), checked_in=True)
    delta = price_quote(unit, days(0), days(4), guests=1)["total"] - b.total
    [reply] = sms("EXTEND 2", phone=phone)
    assert f"(+{kes(delta)})" in reply
    assert reply.endswith(f"Pay {kes(delta)} to confirm - check your phone for the M-Pesa prompt.")
    c = ChangeRequest.objects.get(booking=b)
    assert (c.channel, c.new_check_out, c.status, c.delta) == ("sms", days(4), "pending_payment", delta)
    p = Payment.objects.get(booking=b, purpose="change")
    assert (p.method, p.amount) == ("mpesa", delta)
    settle(p)
    b.refresh_from_db()
    assert b.check_out == days(4)

    instant_changes_off(monkeypatch)
    before = last_id()
    [reply] = sms("extend", phone=phone)
    assert reply.endswith("Amina will confirm by SMS shortly.")
    assert ChangeRequest.objects.filter(booking=b, status="pending_host", new_check_out=days(5)).exists()
    assert bodies(HOST, before, kind="change_request")

    stay(unit, make_user("+254733000204"), days(5), days(7))
    before = last_id()
    assert sms("EXTEND 3", phone=phone) == ["We've asked Amina about 3 more nights. You'll hear back shortly."]
    assert "Unit is NOT free" in bodies(HOST, before)[0]


def paybill(b, amount, code, settled=False):
    """A Paybill (C2B) payment as payments offers it to attach_change_payment: new and still pending (settled=True:
    already settled and counted on the booking)."""
    p = Payment.objects.create(
        booking=b,
        amount=amount,
        method="mpesa",
        purpose="balance",
        provider="c2b",
        transaction_id=code,
        provider_ref=code,
        status="success" if settled else "pending",
    )
    if settled:
        Booking.objects.filter(pk=b.pk).update(amount_paid=F("amount_paid") + amount)
    return p


def test_paybill_money_for_a_waiting_change_settles_and_applies_it_once(guest, booked):
    c, prompt = bookings.request_change(booked, check_in=days(10), check_out=days(14), actor=guest)
    paid_before, before = booked.amount_paid, last_id()
    p = paybill(booked, c.delta, "PB10001")
    assert bookings.attach_change_payment(booked, p) is True
    booked.refresh_from_db()
    c.refresh_from_db()
    p.refresh_from_db()
    assert (p.status, p.purpose, p.provider_ref) == ("success", "change", "PB10001")  # settled by the hook
    assert (c.status, c.payment_id) == ("applied", p.pk)
    assert booked.check_out == days(14) and booked.total == c.new_total
    assert (booked.amount_paid, booked.balance_due) == (paid_before + c.delta, 0)  # counted once
    assert not Refund.objects.filter(booking=booked).exists()
    assert Payment.objects.get(pk=prompt["payment_id"]).status == "cancelled"  # the M-Pesa prompt isn't needed
    assert guest_sms(guest, "change_applied", before)
    assert bookings.attach_change_payment(booked, p) is True  # a repeated hook changes nothing
    booked.refresh_from_db()
    assert (booked.amount_paid, booked.total) == (paid_before + c.delta, c.new_total)


def test_paybill_already_settled_is_not_counted_twice(guest, booked):
    c, _ = bookings.request_change(booked, check_in=days(10), check_out=days(15), actor=guest)
    paid_before = booked.amount_paid
    p = paybill(booked, c.delta, "PB10009", settled=True)
    assert bookings.attach_change_payment(booked, p) is True
    booked.refresh_from_db()
    c.refresh_from_db()
    assert c.status == "applied" and (booked.amount_paid, booked.balance_due) == (paid_before + c.delta, 0)


def test_paybill_overpayment_for_a_change_refunds_the_rest(guest, booked):
    c, _ = bookings.request_change(booked, check_in=days(10), check_out=days(14), actor=guest)
    before = last_id()
    p = paybill(booked, c.delta + 1_000, "PB10002")
    assert bookings.attach_change_payment(booked, p) is True
    booked.refresh_from_db()
    c.refresh_from_db()
    assert c.status == "applied" and booked.check_out == days(14)
    assert [r.amount for r in Refund.objects.filter(booking=booked, status="pending")] == [1_000]
    assert c.refund_amount == 1_000 and bookings.owed(booked) == 0
    [applied] = guest_sms(guest, "change_applied", before)
    assert "Refund of KES 1,000 is on its way." in applied


def test_paybill_money_that_isnt_plainly_for_the_change_is_left_alone(unit, guest):
    b = stay(unit, guest, days(10), days(13), plan="deposit")  # a balance is still due
    assert bookings.attach_change_payment(b, paybill(b, 5_000, "PB10003")) is False  # no change waiting
    c, prompt = bookings.request_change(b, check_in=days(10), check_out=days(14), actor=guest)
    b.refresh_from_db()
    for p in (paybill(b, b.balance_due + c.delta, "PB10004"), paybill(b, c.delta - 1, "PB10005")):
        assert bookings.attach_change_payment(b, p) is False
        p.refresh_from_db()
        assert (p.status, p.purpose) == ("pending", "balance")  # payments settles these as usual
    c.refresh_from_db()
    assert (c.status, c.payment_id) == ("pending_payment", prompt["payment_id"])
    assert Payment.objects.get(pk=prompt["payment_id"]).status == "pending"

    # exactly the change's price is the change's, even with a balance still due
    balance = b.balance_due
    assert bookings.attach_change_payment(b, paybill(b, c.delta, "PB10006")) is True
    b.refresh_from_db()
    c.refresh_from_db()
    assert c.status == "applied" and b.check_out == days(14) and b.balance_due == balance


def test_paybill_confirmation_pays_a_waiting_change_end_to_end(guest, booked):
    from apps.payments import c2b

    c, _ = bookings.request_change(booked, check_in=days(10), check_out=days(14), actor=guest)
    t = c2b.receive(
        {
            "TransID": "SKL4H2XY9P",
            "TransAmount": str(c.delta),
            "BillRefNumber": booked.ref.lower(),
            "MSISDN": "2547***444",
        }
    )
    assert t.status == "matched"
    booked.refresh_from_db()
    c.refresh_from_db()
    p = Payment.objects.get(provider="c2b", booking=booked)
    assert (p.status, p.purpose, c.payment_id, c.status) == ("success", "change", p.pk, "applied")
    assert booked.check_out == days(14) and booked.balance_due == 0 and not booked.refunds.exists()


# ---------- C8: manual bookings with a deposit or Amina's own price ----------


def _walk_in(host_api, unit, **extra):
    body = {
        "unit": unit.pk,
        "check_in": days(12).isoformat(),
        "check_out": days(15).isoformat(),
        "phone": "0722 111 444",
        "name": "Baraka Deal",
        "adults": 2,
        **extra,
    }
    return host_api.post("/api/host/reservations", body, format="json")


def test_host_booking_with_an_agreed_price_and_a_deposit(unit, host, host_api, site):
    r = _walk_in(
        host_api,
        unit,
        payment="mpesa",
        payment_plan="deposit",
        price_override=24_000,
        override_reason="Returning guest",
    )
    assert r.status_code == 201, r.data
    b = Booking.objects.get(ref=r.data["booking"]["ref"])
    taxable = 24_000 + unit.cleaning_fee
    assert (b.accommodation_amount, b.discount_amount, b.cleaning_fee) == (24_000, 0, unit.cleaning_fee)
    assert (b.levy_amount, b.total) == (round(taxable * 0.02), taxable + round(taxable * 0.02))
    assert sum(n["price"] for n in b.nightly) == 24_000 and {n["label"] for n in b.nightly} == {"Agreed price"}
    deposit = -(-b.total * site.deposit_percent // 100)
    assert (b.payment_plan, b.amount_due_now) == ("deposit", deposit)
    assert (r.data["payment"]["amount"], r.data["payment"]["purpose"]) == (deposit, "deposit")
    override = b.events.get(kind="price_override")
    assert override.actor == host and override.text.endswith(": Returning guest")
    assert override.data == {"listed": 30_000, "price": 24_000, "reason": "Returning guest"}
    assert r.data["booking"]["price"]["lines"][0] == {"label": "KES 8,000 x 3 nights", "amount": 24_000}

    # a change keeps the agreed rate
    b = bookings.confirm(b)
    q = bookings.change_quote(b, days(12), days(16))
    assert q["available"] and q["lines"][0] == {"label": "KES 8,000 x 4 nights", "amount": 32_000}


def test_the_new_reservation_quote_shows_the_agreed_price_total_to_hosts_only(unit, host_api, guest_api):
    body = {"check_in": days(12).isoformat(), "check_out": days(15).isoformat(), "adults": 2, "price_override": 24_000}
    agreed = host_api.post(f"/api/listings/{unit.slug}/quote", body, format="json").data
    booked = _walk_in(host_api, unit, price_override=24_000, override_reason="Returning guest").data["booking"]
    assert (agreed["accommodation"], agreed["total"]) == (24_000, booked["price"]["total"])
    listed = guest_api.post(f"/api/listings/{unit.slug}/quote", body, format="json").data
    assert listed["accommodation"] == 30_000 and listed["total"] > agreed["total"]


def test_host_booking_by_card_charges_the_deposit_and_validates_the_override(unit, host_api, site):
    r = _walk_in(host_api, unit, phone="+44 7700 900999", payment="card", payment_plan="deposit")
    b = Booking.objects.get(ref=r.data["booking"]["ref"])
    deposit = -(-b.total * site.deposit_percent // 100)
    assert r.data["payment"]["amount"] == deposit
    token = Payment.objects.get(booking=b).checkout_token
    [link] = Message.objects.filter(phone="+447700900999", kind="hold_card")
    assert token in link.body and kes(deposit) in link.body
    r = _walk_in(host_api, unit, check_in=days(30).isoformat(), check_out=days(31).isoformat(), price_override=5000)
    assert r.status_code == 400 and "Say why" in r.data["error"]
    r = _walk_in(
        host_api,
        unit,
        check_in=days(30).isoformat(),
        check_out=days(31).isoformat(),
        price_override="lots",
        override_reason="x",
    )
    assert r.status_code == 400 and r.data["error"] == "Enter the price for the whole stay in KES."
    assert not Booking.objects.filter(check_in=days(30)).exists()
    assert not User.objects.filter(phone="+254722111444").exists()  # rejected before anyone is created


# ---------- found by the channels tests ----------


def test_late_checkout_or_early_checkin_left_blank_uses_the_extras_own_time(unit, other_unit, guest):
    from apps.core.scheduler import run_due

    Addon.objects.create(
        code="late_checkout", name="Late checkout", price=1_500, requires_approval=True, options={"time": "14:00"}
    )
    Addon.objects.create(
        code="early_checkin", name="Early check-in", price=1_500, requires_approval=True, options={"time": "11:00"}
    )
    b = stay(unit, guest, days(0), days(2), checked_in=True)
    late = bookings.add_addon(b, "late_checkout", details={"time": ""}, channel="web")  # the web form left blank
    bookings.decide_addon(late, True)
    assert bookings.effective_checkout_time(b) == "14:00"
    code = b.access_codes.get(revoked_at__isnull=True)
    assert code.valid_until == at_local(days(2), "14:00") + timedelta(minutes=30)
    with frozen(at_local(days(2), "12:00")):
        run_due(only=["auto_checkout"])
    b.refresh_from_db()
    assert b.status == "checked_in"  # not thrown out at the usual 11:30
    with frozen(at_local(days(2), "14:31")):
        run_due(only=["auto_checkout"])
    b.refresh_from_db()
    assert b.status == "completed"

    later = stay(other_unit, guest, days(5), days(7))
    early = bookings.add_addon(later, "early_checkin", details={"time": "first thing"}, channel="web")
    bookings.decide_addon(early, True)
    assert bookings.effective_checkin_time(later) == "11:00"  # not a time: the extra's own 11am
    assert later.access_codes.get().valid_from == at_local(days(5), "11:00") - timedelta(hours=1)
    assert bookings.details_reveal_at(later) == at_local(days(5), "11:00") - timedelta(hours=48)


def test_wifi_and_directions_wait_for_the_same_reveal_as_the_trip_page(unit, guest, guest_api, host_api):
    from apps.messaging.models import FAQ

    FAQ.objects.create(
        category="wifi", question="Wi-Fi password?", keywords="wifi,password", answer_en="Wi-Fi at {unit}: {wifi}"
    )
    FAQ.objects.create(
        category="check_in",
        question="Where is it?",
        keywords="where,directions",
        answer_en="{unit}: {directions} Landmark: {landmark}. Map: {map_link}",
    )
    unit.landmark, unit.map_link = "Opposite the big baobab", "https://maps.example/palm"
    unit.save()
    b = stay(unit, guest, days(10), days(12))
    ctx = bookings.guest_context(b)
    assert (ctx["wifi"], ctx["directions"], ctx["landmark"]) == (
        "shared 2 days before you arrive",
        "Full directions are shared 2 days before you arrive.",
        "Diani",
    )
    assert ctx["address"] == "Plot 7, Beach Road"  # the trip page shows the address from confirmation
    [answer] = sms("WIFI", phone=guest.phone)
    assert answer == "Wi-Fi at Palm Suite: shared 2 days before you arrive"
    [where] = sms("directions please", phone=guest.phone)
    assert "Past the baobab" not in where and "Full directions are shared 2 days before you arrive." in where
    trip = guest_api.get(f"/api/bookings/{b.ref}").data["checkin"]
    assert not trip["details_visible"] and trip["reveal_at"] == bookings.details_reveal_at(b)

    with frozen(bookings.details_reveal_at(b) + timedelta(minutes=1)):
        assert bookings.details_visible(b)
        assert bookings.guest_context(b)["wifi"] == "PalmWifi / coconut-7"
        assert guest_api.get(f"/api/bookings/{b.ref}").data["checkin"]["wifi_password"] == "coconut-7"
        assert sms("WIFI", phone=guest.phone) == ["Wi-Fi at Palm Suite: PalmWifi / coconut-7"]

    sw = make_user("+254733000301", name="Baraka", lang="sw")
    arriving = stay(make_unit_like(unit, "Coral Cottage"), sw, days(0), days(1))
    assert bookings.guest_context(arriving)["directions"] == "Past the baobab"  # arrival day
    soon = stay(unit, sw, days(20), days(21))
    assert bookings.guest_context(soon)["wifi"] == "itatumwa siku 2 kabla ya kufika"

    # Amina resending the directions from the console shares them whatever the date
    before = last_id()
    assert (
        host_api.post(f"/api/host/reservations/{b.ref}/resend", {"template": "directions"}, format="json").status_code
        == 200
    )
    [sent] = guest_sms(guest, "directions", before)
    assert "Past the baobab" in sent and "coconut-7" in sent


def make_unit_like(unit, name):
    from apps.properties.models import Unit

    return Unit.objects.create(
        name=name,
        area=unit.area,
        base_price=8_000,
        max_guests=2,
        wifi_name="CoralNet",
        wifi_password="reef-22",
        directions="Past the baobab",
        address="Plot 9, Beach Road",
    )


def test_web_search_only_lists_homes_whose_stay_rules_fit_the_dates(unit, other_unit, api):
    from apps.properties.services import available_units

    unit.min_nights = 3  # Palm Suite: 3 nights or more
    unit.save()
    other_unit.max_nights = 2  # Reef Studio: 2 nights at most
    other_unit.save()

    def names(nights):
        r = api.get("/api/listings", {"check_in": days(5).isoformat(), "check_out": days(5 + nights).isoformat()})
        return sorted(c["name"] for c in r.data["results"])

    assert names(2) == ["Reef Studio"]
    assert names(3) == ["Palm Suite"]
    assert sorted(c["name"] for c in api.get("/api/listings").data["results"]) == ["Palm Suite", "Reef Studio"]
    # the phone channels still get every free home, to offer a longer stay where one is needed
    assert {u.name for u in available_units(days(5), days(7))} == {"Palm Suite", "Reef Studio"}
    assert [u.name for u in available_units(days(5), days(7), bookable=True)] == ["Reef Studio"]
