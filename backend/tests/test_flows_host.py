"""Host console API end to end: who may use it, the Today/Insights/compliance screens, the calendar, every
reservation action, requests, the listing/price/block/iCal/amenity/add-on managers, refunds and reviews."""

import csv
import io
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bookings import services as bookings
from apps.bookings.models import AccessCode, Addon, Booking, BookingAddon, BookingGuest
from apps.core.utils import kes, today
from apps.messaging.models import Message
from apps.operations.models import Task
from apps.payments import services as payments
from apps.payments.models import Payment, Refund
from apps.properties import services as property_services
from apps.properties.models import Amenity, CalendarBlock, ICalFeed, PriceOverride, PriceRule, Unit
from apps.properties.services import quote as price_quote
from apps.reviews.models import Review
from apps.safety.models import Alert

from .conftest import days

pytestmark = pytest.mark.django_db


# ---------- helpers ----------


def hold(unit, guest, ci=10, nights=2, **kw):
    kw.setdefault("channel", "web")
    return bookings.create_hold(unit=unit, guest=guest, check_in=days(ci), check_out=days(ci + nights), **kw)


def confirmed(unit, guest, ci=10, nights=2, **kw):
    b = hold(unit, guest, ci, nights, **kw)
    r = payments.start_payment(b)
    payments.on_success(Payment.objects.get(pk=r["payment_id"]), transaction_id=f"T{r['payment_id']}")
    b.refresh_from_db()
    return b


def checked_in(unit, guest, ci=0, nights=2, **kw):
    b = confirmed(unit, guest, ci, nights, **kw)
    assert bookings.release_code(b, force=True) == "released"
    b.refresh_from_db()
    return b


def stay(unit, guest, start, nights, status="completed", **kw):
    """A booking on any dates (past ones too), priced the way the engine prices it."""
    q = price_quote(unit, start, start + timedelta(days=nights), guests=kw.get("adults", 1))
    b = Booking.objects.create(
        ref=Booking.new_ref(),
        unit=unit,
        guest=guest,
        check_in=start,
        check_out=start + timedelta(days=nights),
        status=status,
        channel=kw.pop("channel", "web"),
        nightly=q["nightly"],
        accommodation_amount=q["accommodation"],
        cleaning_fee=q["cleaning_fee"],
        levy_amount=q["levy"],
        total=q["total"],
        amount_paid=q["total"],
        payment_status="paid",
        cancellation_policy=unit.cancellation_policy,
        **kw,
    )
    BookingGuest.objects.create(booking=b, full_name=guest.name, nationality=guest.nationality, is_lead=True)
    return b


def as_user(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def act(host_api, b, action, **body):
    return host_api.post(f"/api/host/reservations/{b.ref}/{action}", body, format="json")


def guest_messages(guest, kind):
    return Message.objects.filter(phone=guest.phone, kind=kind)


@pytest.fixture
def nyali_unit(area):
    return Unit.objects.create(name="Baobab House", area=area, base_price=12_000, max_guests=6)


# ---------- who may use the console ----------

HOST_READS = [
    "/api/host/today",
    "/api/host/insights",
    "/api/host/compliance/tra-return",
    "/api/host/calendar",
    "/api/host/reservations",
    "/api/host/requests",
    "/api/host/listings",
    "/api/host/price-rules",
    "/api/host/blocks",
    "/api/host/ical-feeds",
    "/api/host/amenities",
    "/api/host/addons",
    "/api/host/payments",
    "/api/host/reviews",
]


@pytest.mark.parametrize("role", ["anonymous", "guest", "cleaner", "cook", "caretaker", "security", "driver"])
def test_only_owners_and_managers_can_use_the_console(role, unit, guest):
    b = confirmed(unit, guest)
    if role == "anonymous":
        client = APIClient()
    else:
        client = as_user(User.objects.create_user(f"+25473300{len(role):04d}", name=role.title(), role=role))
    denied = (401, 403)
    for url in HOST_READS + [f"/api/host/reservations/{b.ref}"]:
        assert client.get(url).status_code in denied, url
    writes = [
        ("post", f"/api/host/reservations/{b.ref}/cancel", {}),
        ("post", f"/api/host/reservations/{b.ref}/record-payment", {"amount": 100}),
        ("post", "/api/host/reservations", {"unit": unit.pk}),
        ("patch", f"/api/host/reservations/{b.ref}", {"host_notes": "x"}),
        ("put", "/api/host/prices", {"unit": unit.pk, "dates": [days(3).isoformat()], "price": 1}),
        ("post", "/api/host/blocks", {"unit": unit.pk, "start_date": days(3), "end_date": days(4)}),
        ("patch", f"/api/host/listings/{unit.pk}", {"base_price": 1}),
        ("post", "/api/host/refunds/1/sent", {}),
        ("post", "/api/host/reviews/1/respond", {"text": "x"}),
        ("post", "/api/host/requests/1/decide", {"approve": True}),
    ]
    for method, url, body in writes:
        assert getattr(client, method)(url, body, format="json").status_code in denied, url
    b.refresh_from_db()
    unit.refresh_from_db()
    assert b.status == "confirmed" and unit.base_price == 10_000 and not PriceOverride.objects.exists()
    assert not CalendarBlock.objects.exists() and Booking.objects.count() == 1


@pytest.mark.parametrize("who", ["owner", "manager", "superuser"])
def test_owner_manager_and_superuser_see_everything(who, unit):
    if who == "superuser":
        user = User.objects.create_superuser("+254733999000", name="Admin")
        user.role = "guest"
        user.save()
    else:
        user = User.objects.create_user("+254733999001", name=who.title(), role=who)
    client = as_user(user)
    for url in HOST_READS:
        assert client.get(url).status_code == 200, url


# ---------- Today, Insights, TRA return ----------


def test_today_screen(host_api, unit, other_unit, nyali_unit, guest, foreign_guest, breakfast):
    arriving = confirmed(unit, guest, ci=0)
    in_house = checked_in(other_unit, foreign_guest, ci=0)
    regular = User.objects.create_user("+254733000111", name="Baraka")
    leaving = stay(nyali_unit, regular, days(-3), 3, status="checked_in")
    upcoming = confirmed(unit, regular, ci=3)
    held = hold(nyali_unit, guest, ci=12)
    lapsed = hold(unit, foreign_guest, ci=20)
    Booking.objects.filter(pk=lapsed.pk).update(hold_expires_at=timezone.now() - timedelta(minutes=1))
    BookingAddon.objects.create(
        booking=in_house, addon=breakfast, quantity=2, total=0, details={"style": "swahili", "time": "08:00"}
    )
    task = Task.objects.create(type="maintenance", title="Fix the gate", unit=unit)
    alert = Alert.objects.create(kind="security", summary="Gate left open", severity="medium")

    r = host_api.get("/api/host/today")
    assert r.status_code == 200 and r.data["date"] == today().isoformat()
    refs = {k: [x["ref"] for x in r.data[k]] for k in ("arrivals", "departures", "in_house", "upcoming", "holds")}
    assert sorted(refs["arrivals"]) == sorted([arriving.ref, in_house.ref])
    assert refs["departures"] == [leaving.ref]
    assert sorted(refs["in_house"]) == sorted([in_house.ref, leaving.ref])
    assert refs["upcoming"] == [upcoming.ref] and refs["holds"] == [held.ref]
    assert [t["id"] for t in r.data["tasks"]] == [task.pk] and alert.pk in [a["id"] for a in r.data["alerts"]]
    assert set(r.data["kpis"]) == {"week", "month"} and "occupancy" in r.data["kpis"]["week"]
    assert r.data["activity"] and isinstance(r.data["breakfasts"], list)


def test_insights_kpis(host_api, unit, other_unit, guest, foreign_guest):
    stay(unit, guest, days(-10), 3)
    stay(other_unit, foreign_guest, days(-5), 2, channel="airbnb")
    CalendarBlock.objects.create(unit=other_unit, start_date=days(-20), end_date=days(-18), reason="maintenance")
    r = host_api.get("/api/host/insights")
    assert r.status_code == 200 and r.data["days"] == 30
    k = r.data["kpis"]
    assert (k["booked_nights"], k["available_nights"]) == (5, 2 * 30 - 2)  # maintenance nights aren't for sale
    assert k["occupancy"] == round(100 * 5 / 58)
    assert k["room_revenue"] == 3 * 10_000 + 2 * 5_000 and k["adr"] == 8_000
    assert k["bookings"] == 2 and k["direct_share"] == 50 and k["by_channel"]["airbnb"]["bookings"] == 1
    assert len(r.data["series"]) == 30 and len(r.data["forward"]) == 8
    assert r.data["previous"]["booked_nights"] == 0
    assert host_api.get("/api/host/insights?days=1").data["days"] == 7
    assert host_api.get("/api/host/insights?days=9999").data["days"] == 365


def test_tra_monthly_return_json_and_csv(host_api, unit, other_unit, guest, foreign_guest):
    first = today().replace(day=1)
    last_month = (first - timedelta(days=1)).replace(day=1)
    guest.nationality = "KE"
    guest.save()
    a = stay(unit, guest, last_month + timedelta(days=2), 3, adults=2)
    BookingGuest.objects.create(booking=a, full_name="Otieno", nationality="KE")
    stay(other_unit, foreign_guest, last_month + timedelta(days=10), 2)
    stay(unit, guest, first + timedelta(days=40), 2)  # another month entirely
    r = host_api.get("/api/host/compliance/tra-return")  # defaults to last month
    assert r.status_code == 200 and r.data["month"] == f"{last_month:%Y-%m}"
    d = r.data
    assert (d["units"], d["room_nights_sold"], d["arrivals"]) == (2, 5, 2)
    assert d["guest_nights"] == 2 * 3 + 1 * 2 and d["visitors_by_country"] == {"KE": 2, "GB": 1}
    assert d["room_revenue"] == 3 * 10_000 + 2 * 5_000
    nights_in_month = (first - last_month).days
    assert d["room_nights_available"] == 2 * nights_in_month

    r = host_api.get(f"/api/host/compliance/tra-return?month={last_month:%Y-%m}&export=csv")
    assert r.status_code == 200 and r["Content-Type"].startswith("text/csv")
    assert f"tra-return-{last_month:%Y-%m}.csv" in r["Content-Disposition"]
    rows = list(csv.reader(io.StringIO(r.content.decode())))
    assert ["Room nights sold", "5"] in rows and ["KE", "2"] in rows and ["GB", "1"] in rows
    for bad in ("2026-13", "garbage", "2026-00"):
        assert host_api.get(f"/api/host/compliance/tra-return?month={bad}").status_code == 400


# ---------- calendar & prices ----------


def test_host_calendar(host_api, unit, other_unit, guest, foreign_guest):
    b = confirmed(unit, guest, ci=2, nights=3)
    live_hold = hold(other_unit, foreign_guest, ci=1)
    lapsed = hold(other_unit, guest, ci=8)
    Booking.objects.filter(pk=lapsed.pk).update(hold_expires_at=timezone.now() - timedelta(minutes=1))
    feed = ICalFeed.objects.create(unit=other_unit, name="Airbnb", url="https://example.com/a.ics")
    CalendarBlock.objects.create(unit=other_unit, start_date=days(4), end_date=days(6), reason="external", feed=feed)
    owner = CalendarBlock.objects.create(
        unit=unit, start_date=days(9), end_date=days(10), reason="owner", note="Family"
    )
    PriceOverride.objects.create(unit=unit, date=days(6), price=18_000)
    Unit.objects.create(name="Unfinished", area=unit.area, base_price=1, status="draft")
    Unit.objects.create(name="Resting", area=unit.area, base_price=1, status="paused")

    r = host_api.get(f"/api/host/calendar?start={days(0)}&days=14")
    assert r.status_code == 200 and len(r.data["days"]) == 14 and r.data["days"][0] == days(0).isoformat()
    by_name = {u["name"]: u for u in r.data["units"]}
    assert set(by_name) == {"Palm Suite", "Reef Studio", "Resting"}
    palm, reef = by_name["Palm Suite"], by_name["Reef Studio"]
    assert [x["ref"] for x in palm["bookings"]] == [b.ref] and palm["bookings"][0]["guest"] == "Wanjiru Test"
    assert [x["ref"] for x in reef["bookings"]] == [live_hold.ref]  # the lapsed hold is gone
    assert reef["blocks"][0]["source"] == "Airbnb" and reef["blocks"][0]["external"] is True
    assert palm["blocks"][0]["id"] == owner.pk and palm["blocks"][0]["source"] is None
    assert palm["prices"][days(6).isoformat()] == 18_000 and palm["overrides"] == [days(6).isoformat()]
    assert len(host_api.get("/api/host/calendar?days=1").data["days"]) == 7
    assert len(host_api.get("/api/host/calendar?days=500").data["days"]) == 62


def test_set_nightly_prices(host_api, api, unit):
    def nightly(ci, co):
        return price_quote(unit, days(ci), days(co))["accommodation"]

    r = host_api.put(
        "/api/host/prices",
        {"unit": unit.pk, "dates": [days(5).isoformat(), days(6).isoformat()], "price": 15_000, "note": "Easter"},
        format="json",
    )
    assert r.status_code == 200 and r.data == {"updated": 2}
    assert nightly(5, 7) == 30_000
    q = api.post(
        f"/api/listings/{unit.slug}/quote",
        {"check_in": days(5).isoformat(), "check_out": days(7).isoformat()},
        format="json",
    ).data
    assert q["nightly"][0] == {"date": days(5).isoformat(), "price": 15_000, "label": "Easter"}
    r = host_api.put(
        "/api/host/prices",
        {"unit": unit.pk, "start": days(10).isoformat(), "end": days(13).isoformat(), "price": "8000"},
        format="json",
    )
    assert r.data == {"updated": 3} and nightly(10, 13) == 24_000
    host_api.put("/api/host/prices", {"unit": unit.pk, "dates": [days(5).isoformat()], "price": None}, format="json")
    assert nightly(5, 7) == 10_000 + 15_000
    assert host_api.put("/api/host/prices", {"unit": 99999, "dates": [], "price": 1}, format="json").status_code == 404


# ---------- reservations ----------


def test_reservations_list_filters_and_search(host_api, unit, other_unit, guest, foreign_guest):
    web = confirmed(unit, guest, ci=5)
    ussd = hold(other_unit, foreign_guest, ci=10, channel="ussd")
    lapsed = hold(unit, foreign_guest, ci=20)
    bookings._expire(Booking.objects.filter(pk=lapsed.pk))
    gone = confirmed(other_unit, guest, ci=30)
    bookings.cancel(gone, by="guest")

    def refs(query=""):
        r = host_api.get(f"/api/host/reservations{query}")
        assert r.status_code == 200
        return sorted(x["ref"] for x in r.data)

    assert refs() == sorted([web.ref, ussd.ref, gone.ref])  # expired holds are noise
    assert refs("?status=expired") == [lapsed.ref]
    assert refs("?status=held,confirmed") == sorted([web.ref, ussd.ref])
    assert refs("?channel=ussd") == [ussd.ref]
    assert refs(f"?unit={other_unit.pk}") == sorted([ussd.ref, gone.ref])
    assert refs(f"?from={days(9)}&to={days(11)}") == [ussd.ref]
    assert refs(f"?q={web.ref.lower()}") == [web.ref]
    assert refs("?q=emma") == [ussd.ref]
    assert refs("?q=7700900") == [ussd.ref]
    assert refs("?q=reef") == sorted([ussd.ref, gone.ref])
    assert len(host_api.get("/api/host/reservations?limit=1").data) == 1
    row = next(x for x in host_api.get("/api/host/reservations").data if x["ref"] == web.ref)
    assert (row["total"], row["amount_paid"], row["balance_due"], row["payment_status"]) == (
        web.total,
        web.total,
        0,
        "paid",
    )


def test_reservation_detail_and_editing(host_api, unit, guest):
    b = confirmed(unit, guest, ci=10)
    r = host_api.get(f"/api/host/reservations/{b.ref.lower()}")
    assert r.status_code == 200
    assert r.data["guest"]["phone"] == guest.phone and r.data["risk"]["score"] == b.risk_score
    assert r.data["checkin"]["code"] == b.access_codes.get().code and r.data["codes"][0]["sent_at"] is None
    assert {"payment_requested", "payment", "confirmed"} <= {e["kind"] for e in r.data["timeline"]}
    r = host_api.patch(
        f"/api/host/reservations/{b.ref}",
        {
            "host_notes": "Repeat guest - leave a fruit basket",
            "arrival_eta": "Around 3pm, after the SGR train gets into Miritini",
            "vehicle_plate": "KDA 123A + trailer",
            "arrival_mode": "train and taxi",
            "special_requests": "Cot",
        },
        format="json",
    )
    assert r.status_code == 200
    b.refresh_from_db()
    assert b.host_notes == "Repeat guest - leave a fruit basket" and r.data["host_notes"] == b.host_notes
    assert b.arrival_eta == "Around 3pm, after the SGR train gets into"[:40] and len(b.vehicle_plate) <= 12
    assert b.arrival_mode == "train and "[:10] and b.special_requests == "Cot"
    assert host_api.get("/api/host/reservations/AMS-0000").status_code == 404


def test_confirm_action_books_without_payment(host_api, unit, guest):
    b = hold(unit, guest)
    r = act(host_api, b, "confirm")
    assert r.status_code == 200 and r.data["status"] == "confirmed"
    b.refresh_from_db()
    assert (b.payment_status, b.balance_due, b.amount_paid) == ("unpaid", b.total, 0)
    assert "Balance" in guest_messages(guest, "booking_confirmed").get().body
    assert act(host_api, b, "confirm").status_code == 200  # already confirmed: a no-op
    bookings.cancel(b, by="host")
    r = act(host_api, b, "confirm")
    assert r.status_code == 400 and "cancelled" in r.data["error"]


def test_record_payment_action(host_api, unit, other_unit, guest):
    b = confirmed(unit, guest, ci=30, nights=3, payment_plan="deposit")
    balance = b.balance_due
    r = act(host_api, b, "record-payment", amount=5_000, method="bank", reference="FT2611250042")
    assert r.status_code == 200 and r.data["price"]["balance_due"] == balance - 5_000
    p = Payment.objects.get(booking=b, method="bank")
    assert (p.amount, p.provider, p.provider_ref, p.status, p.purpose) == (
        5_000,
        "manual",
        "FT2611250042",
        "success",
        "balance",
    )
    r = act(host_api, b, "record-payment")  # defaults to the whole balance, in cash
    assert r.status_code == 200 and r.data["price"]["payment_status"] == "paid"
    cash = Payment.objects.get(booking=b, method="cash")
    assert cash.amount == balance - 5_000 and cash.provider_ref == f"CASH-{cash.pk}"
    for body in ({}, {"amount": -500}, {"amount": "lots"}):
        r = act(host_api, b, "record-payment", **body)
        assert r.status_code == 400 and "amount" in r.data["error"]
    assert act(host_api, b, "record-payment", amount=100, method="bitcoin").status_code == 400
    assert Payment.objects.filter(booking=b).count() == 3

    walk_up = hold(other_unit, guest, ci=5)
    r = act(host_api, walk_up, "record-payment", amount=walk_up.total, method="mpesa", reference="SKL4H2XY9P")
    assert r.data["status"] == "confirmed" and r.data["price"]["payment_status"] == "paid"
    bookings.cancel(walk_up, by="host")
    assert act(host_api, walk_up, "record-payment", amount=100).status_code == 400


def test_request_payment_action(host_api, unit, other_unit, guest, foreign_guest):
    b = confirmed(unit, guest, ci=30, nights=3, payment_plan="deposit")
    r = act(host_api, b, "request-payment", method="mpesa")
    assert r.status_code == 200
    p = Payment.objects.get(booking=b, status="pending")
    assert (p.method, p.amount, p.purpose, p.created_by.phone) == ("mpesa", b.balance_due, "balance", "+254700000001")
    r = act(host_api, b, "request-payment", method="mpesa", amount=1_000)
    assert Payment.objects.filter(booking=b, status="pending", amount=1_000).exists()
    assert any(e["kind"] == "payment_requested" for e in r.data["timeline"])

    abroad = confirmed(other_unit, foreign_guest, ci=30, nights=3, payment_plan="deposit")
    r = act(host_api, abroad, "request-payment", method="mpesa")
    assert r.status_code == 400 and "Kenyan" in r.data["error"]
    assert act(host_api, abroad, "request-payment", method="card").status_code == 200
    link = Payment.objects.get(booking=abroad, status="pending").checkout_token
    assert guest_messages(foreign_guest, "pay_link").filter(body__contains=link).exists()

    paid = confirmed(unit, foreign_guest, ci=5)
    r = act(host_api, paid, "request-payment", method="card")
    assert r.status_code == 400 and "nothing left to pay" in r.data["error"]


def test_release_code_action_waits_for_check_in_day(host_api, unit, other_unit, guest, site):
    future = confirmed(unit, guest, ci=20)
    code = future.access_codes.get()
    r = act(host_api, future, "release-code", force=True)
    assert r.status_code == 400 and r.data["error"] == "Code not released: too early"
    future.refresh_from_db()
    code.refresh_from_db()
    assert future.status == "confirmed" and future.checked_in_at is None and future.code_released_at is None
    assert code.sent_at is None and not guest_messages(guest, "checkin_code").exists()

    arriving = confirmed(other_unit, guest, ci=0)  # no ID on file, and the register is required
    assert site.require_id_before_code and not guest.has_id
    r = act(host_api, arriving, "release-code", force=False)
    assert r.status_code == 400 and r.data["error"] == "Code not released: waiting id"
    r = act(host_api, arriving, "release-code")  # Amina's override (the console default)
    assert r.status_code == 200 and r.data["status"] == "checked_in"
    sent = arriving.access_codes.get(revoked_at__isnull=True)
    assert sent.sent_at and guest_messages(guest, "checkin_code").filter(body__contains=sent.code).exists()
    assert act(host_api, arriving, "release-code").data["error"] == "Code not released: not confirmed"


def test_check_out_action(host_api, unit, guest):
    upcoming = confirmed(unit, guest, ci=10)
    assert act(host_api, upcoming, "check-out").status_code == 400
    b = checked_in(unit, guest, ci=0)
    r = act(host_api, b, "check-out")
    assert r.status_code == 200 and r.data["status"] == "completed"
    assert not AccessCode.objects.filter(booking=b, revoked_at__isnull=True).exists()
    assert Task.objects.filter(type="turnover", booking=b).exists()
    assert guest_messages(guest, "checkout_thanks").exists()
    assert act(host_api, b, "check-out").status_code == 400


def test_host_cancellation_refunds_in_full_with_goodwill_airtime(host_api, unit, other_unit, guest, foreign_guest):
    unit.cancellation_policy = "strict"
    unit.save()
    b = confirmed(unit, guest, ci=3)  # the guest would get nothing back; Amina cancelling refunds everything
    r = act(host_api, b, "cancel", reason="Burst pipe")
    assert r.status_code == 200 and r.data["status"] == "cancelled"
    b.refresh_from_db()
    assert (b.cancelled_by, b.cancel_reason, b.amount_refunded, b.payment_status) == (
        "host",
        "Burst pipe",
        b.total,
        "refunded",
    )
    msg = guest_messages(guest, "cancelled_by_host").get().body
    assert "Refund" in msg and "airtime" in msg.lower()
    assert b.events.filter(kind="airtime").exists()
    assert act(host_api, b, "cancel").status_code == 400

    partial = confirmed(other_unit, foreign_guest, ci=10)
    act(host_api, partial, "cancel", refund_amount=2_000)
    partial.refresh_from_db()
    assert partial.amount_refunded == 2_000 and partial.payment_status == "partially_refunded"
    assert not partial.events.filter(kind="airtime").exists()  # airtime only reaches Kenyan numbers
    capped = confirmed(other_unit, foreign_guest, ci=20)
    act(host_api, capped, "cancel", refund_amount=10_000_000)
    capped.refresh_from_db()
    assert capped.amount_refunded == capped.amount_paid


def test_cancelled_stays_owe_nothing_and_queued_refunds_are_visible(host_api, unit, guest):
    unit.cancellation_policy = "strict"
    unit.save()
    kept = confirmed(unit, guest, ci=12, nights=2, payment_plan="deposit")
    assert 0 < kept.amount_paid < kept.total  # a deposit booking still owes its balance...
    assert act(host_api, kept, "cancel", reason="No-show agreed", refund_amount=0).status_code == 200
    kept.refresh_from_db()
    assert kept.amount_refunded == 0 and kept.balance_due == 0  # ...but nothing is owed once it's cancelled
    price = host_api.get(f"/api/host/reservations/{kept.ref}").data["price"]
    assert (price["balance_due"], price["refund_pending"]) == (0, 0)

    live = confirmed(unit, guest, ci=20, nights=2)
    payments.refund(live, 1_000, reason="Goodwill", queue=True)  # waits for Amina to send it
    price = host_api.get(f"/api/host/reservations/{live.ref}").data["price"]
    assert price["refund_pending"] == 1_000 and price["amount_refunded"] == 0


def test_resend_action(host_api, unit, guest):
    held = hold(unit, guest, ci=1)
    r = act(host_api, held, "resend", template="directions")
    assert r.status_code == 400  # nothing to resend before the booking is confirmed
    b = confirmed(unit, guest, ci=20)
    for key in ("booking_confirmed", "pre_arrival", "directions", "local_tips", "checkout_reminder"):
        assert act(host_api, b, "resend", template=key).status_code == 200, key
        assert guest_messages(guest, key).exists(), key
    assert "Past the baobab" in guest_messages(guest, "directions").get().body
    r = act(host_api, b, "resend", template="checkin_code")
    assert r.status_code == 400 and "hasn't been released" in r.data["error"]
    assert act(host_api, b, "resend", template="otp").status_code == 400
    assert act(host_api, b, "resend", template="nonsense").status_code == 400
    assert not guest_messages(guest, "checkin_code").exists()


def test_verify_id_and_message_actions(host_api, unit, guest):
    b = confirmed(unit, guest)
    r = act(host_api, b, "verify-id")
    assert r.status_code == 200 and r.data["guest"]["id_verified"] is True
    guest.refresh_from_db()
    assert guest.id_verified_at and b.events.filter(kind="register", text="ID verified in person").exists()
    r = act(host_api, b, "message", text="Your driver is waiting at arrivals")
    assert r.status_code == 200
    reply = Message.objects.filter(phone=guest.phone, kind="host_reply").get()
    assert reply.body == "Amina: Your driver is waiting at arrivals" and reply.sender == "host"
    assert act(host_api, b, "message", text="   ").status_code == 400
    assert Message.objects.filter(phone=guest.phone, kind="host_reply").count() == 1
    r = act(host_api, b, "teleport")
    assert r.status_code == 404 and r.data["error"] == "Unknown action."
    assert host_api.post("/api/host/reservations/AMS-0000/confirm").status_code == 404


def test_requests_queue_and_decisions(host_api, unit, other_unit, guest, foreign_guest):
    late = Addon.objects.create(
        code="late_checkout", name="Late checkout", category="flexibility", price=1_500, requires_approval=True
    )
    b = confirmed(unit, guest)
    ba = bookings.add_addon(b, "late_checkout", details={"time": "14:00"})
    lapsed = hold(other_unit, foreign_guest, ci=20)
    BookingAddon.objects.create(booking=lapsed, addon=late, total=1_500, status="requested")
    bookings._expire(Booking.objects.filter(pk=lapsed.pk))
    rows = host_api.get("/api/host/requests").data
    assert [(x["id"], x["code"], x["ref"], x["unit"], x["details"], x["total"]) for x in rows] == [
        (ba.pk, "late_checkout", b.ref, "Palm Suite", {"time": "14:00"}, 1_500)
    ]  # requests on lapsed holds aren't Amina's problem
    manager = as_user(User.objects.create_user("+254733555000", name="Co-host", role="manager"))
    r = manager.post(f"/api/host/requests/{ba.pk}/decide", {"approve": True}, format="json")
    assert r.status_code == 200 and r.data["ref"] == b.ref
    ba.refresh_from_db()
    assert ba.status == "confirmed" and ba.decided_at
    assert host_api.get("/api/host/requests").data == []
    assert host_api.post("/api/host/requests/999999/decide", {"approve": True}, format="json").status_code == 404


# ---------- listings, prices, blocks, calendars, amenities, add-ons ----------


def test_listing_manager(host_api, api, unit, guest):
    wifi = Amenity.objects.create(code="wifi", name="Wi-Fi")
    pool = Amenity.objects.create(code="pool", name="Pool")
    rows = host_api.get("/api/host/listings").data
    assert [x["name"] for x in rows] == ["Palm Suite"]
    assert rows[0]["wifi_password"] == "coconut-7" and rows[0]["address"] == "Plot 7, Beach Road"
    assert rows[0]["ical_export_url"].endswith(f"/api/ical/{unit.ical_token}.ics")

    r = host_api.patch(
        f"/api/host/listings/{unit.pk}", {"base_price": 11_000, "amenity_codes": ["wifi", "pool"]}, format="json"
    )
    assert r.status_code == 200 and sorted(r.data["amenity_codes"]) == ["pool", "wifi"]
    unit.refresh_from_db()
    assert unit.base_price == 11_000 and set(unit.amenities.all()) == {wifi, pool}
    assert api.get(f"/api/listings/{unit.slug}").data["price"]["base_price"] == 11_000
    assert host_api.get(f"/api/host/listings/{unit.pk}").data["name"] == "Palm Suite"

    r = host_api.post(
        "/api/host/listings", {"name": "Coral Cottage", "area": "diani", "base_price": 7_000}, format="json"
    )
    assert r.status_code == 201 and r.data["slug"] == "coral-cottage"
    coral = Unit.objects.get(slug="coral-cottage")
    assert api.get("/api/listings/coral-cottage").status_code == 200
    assert host_api.post("/api/host/listings", {"name": "No area", "base_price": 1}, format="json").status_code == 400

    hold(unit, guest)
    r = host_api.delete(f"/api/host/listings/{unit.pk}")
    assert r.status_code == 200 and r.data["paused"] is True  # homes with bookings are paused, not deleted
    unit.refresh_from_db()
    assert unit.status == "paused" and api.get(f"/api/listings/{unit.slug}").status_code == 404
    assert host_api.delete(f"/api/host/listings/{coral.pk}").status_code == 204
    assert not Unit.objects.filter(pk=coral.pk).exists()


def test_price_rules_change_quotes(host_api, unit):
    r = host_api.post(
        "/api/host/price-rules",
        {
            "unit": unit.pk,
            "name": "Christmas",
            "kind": "season",
            "start_date": days(10).isoformat(),
            "end_date": days(11).isoformat(),
            "adjust_type": "percent",
            "value": "50",
        },
        format="json",
    )
    assert r.status_code == 201 and r.data["unit_name"] == "Palm Suite"
    assert price_quote(unit, days(10), days(12))["accommodation"] == 2 * 15_000
    lm = host_api.post(
        "/api/host/price-rules",
        {"name": "Last minute", "kind": "last_minute", "days_before": 3, "adjust_type": "percent", "value": "-20"},
        format="json",
    )
    assert lm.status_code == 201 and lm.data["unit_name"] == "All homes"
    q = price_quote(unit, days(1), days(3))
    assert q["discount"] == round(2 * 10_000 * 0.2) and q["lines"][1]["label"] == "Last minute (20% off)"
    assert len(host_api.get("/api/host/price-rules").data) == 2
    assert host_api.delete(f"/api/host/price-rules/{r.data['id']}").status_code == 204
    assert price_quote(unit, days(10), days(12))["accommodation"] == 2 * 10_000
    assert PriceRule.objects.count() == 1


def test_calendar_blocks_stop_bookings(host_api, guest_api, api, unit, host):
    body = {
        "unit": unit.pk,
        "start_date": days(10).isoformat(),
        "end_date": days(13).isoformat(),
        "reason": "maintenance",
        "note": "Roof repairs",
    }
    r = host_api.post("/api/host/blocks", body, format="json")
    assert r.status_code == 201 and r.data["unit_name"] == "Palm Suite"
    blk = CalendarBlock.objects.get(pk=r.data["id"])
    assert blk.created_by == host and blk.feed is None
    booking = {"listing": unit.slug, "check_in": days(11).isoformat(), "check_out": days(14).isoformat()}
    assert guest_api.post("/api/bookings", booking, format="json").status_code == 409
    cal = api.get(f"/api/listings/{unit.slug}/calendar?start={days(9)}&end={days(15)}").data
    assert cal["unavailable"] == [days(10).isoformat(), days(11).isoformat(), days(12).isoformat()]
    assert api.get(f"/api/listings?check_in={days(11)}&check_out={days(12)}").data["count"] == 0
    assert [x["id"] for x in host_api.get("/api/host/blocks").data] == [blk.pk]

    bad = {**body, "end_date": days(10).isoformat()}
    assert host_api.post("/api/host/blocks", bad, format="json").status_code == 400
    r = host_api.patch(f"/api/host/blocks/{blk.pk}", {"note": "Roof + gutters"}, format="json")
    assert r.status_code == 200 and r.data["note"] == "Roof + gutters"
    r = host_api.patch(f"/api/host/blocks/{blk.pk}", {"end_date": days(9).isoformat()}, format="json")
    assert r.status_code == 400  # a partial edit is still checked against the saved start date
    assert host_api.delete(f"/api/host/blocks/{blk.pk}").status_code == 204
    assert guest_api.post("/api/bookings", booking, format="json").status_code == 201


def test_ical_feeds(host_api, unit, guest_api, monkeypatch):
    ci, co = days(14), days(17)
    ics = (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\n"
        f"DTSTART;VALUE=DATE:{ci:%Y%m%d}\r\nDTEND;VALUE=DATE:{co:%Y%m%d}\r\nUID:abc@airbnb.com\r\n"
        "SUMMARY:Reserved\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    )

    class FakeResponse:
        text = ics

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, url, **kwargs):
            if "broken" in url:
                raise property_services.httpx.ConnectError("no route to host")
            return FakeResponse()

    monkeypatch.setattr(property_services.httpx, "Client", FakeClient)
    r = host_api.post(
        "/api/host/ical-feeds",
        {"unit": unit.pk, "name": "Airbnb", "url": "https://www.airbnb.com/calendar/ical/1.ics"},
        format="json",
    )
    assert r.status_code == 201 and r.data["unit_name"] == "Palm Suite"
    feed_id = r.data["id"]
    r = host_api.post(f"/api/host/ical-feeds/{feed_id}/sync")
    assert r.status_code == 200 and r.data == {"ok": True, "events": 1, "conflicts": 0}
    blk = CalendarBlock.objects.get(feed_id=feed_id)
    assert (blk.start_date, blk.end_date, blk.reason) == (ci, co, "external")
    booking = {"listing": unit.slug, "check_in": days(15).isoformat(), "check_out": days(16).isoformat()}
    assert guest_api.post("/api/bookings", booking, format="json").status_code == 409
    feed = host_api.get(f"/api/host/ical-feeds/{feed_id}").data
    assert feed["last_ok"] is True and feed["events_count"] == 1 and feed["last_synced_at"]

    host_api.patch(f"/api/host/ical-feeds/{feed_id}", {"url": "https://broken.example.com/x.ics"}, format="json")
    r = host_api.post(f"/api/host/ical-feeds/{feed_id}/sync")
    assert r.data["ok"] is False and ICalFeed.objects.get(pk=feed_id).last_ok is False
    assert CalendarBlock.objects.filter(feed_id=feed_id).exists()  # a failed sync never drops known blocks
    assert host_api.delete(f"/api/host/ical-feeds/{feed_id}").status_code == 204
    assert not CalendarBlock.objects.filter(feed_id=feed_id).exists()
    assert guest_api.post("/api/bookings", booking, format="json").status_code == 201


def test_amenity_and_addon_managers(host_api, api, unit, other_unit):
    r = host_api.post(
        "/api/host/amenities", {"code": "pool", "name": "Pool", "category": "outdoor", "icon": "waves"}, format="json"
    )
    assert r.status_code == 201
    host_api.patch(f"/api/host/amenities/{r.data['id']}", {"name": "Infinity pool"}, format="json")
    assert [a["name"] for a in api.get("/api/amenities").data] == ["Infinity pool"]
    assert host_api.post("/api/host/amenities", {"code": "pool", "name": "Dupe"}, format="json").status_code == 400
    assert host_api.delete(f"/api/host/amenities/{r.data['id']}").status_code == 204

    r = host_api.post(
        "/api/host/addons",
        {"code": "kayak", "name": "Kayak hire", "price": 2_000, "pricing": "per_stay", "unit_ids": [other_unit.pk]},
        format="json",
    )
    assert r.status_code == 201 and r.data["unit_ids"] == [other_unit.pk]
    assert "kayak" not in [a["code"] for a in api.get(f"/api/addons?listing={unit.slug}").data]
    assert "kayak" in [a["code"] for a in api.get(f"/api/addons?listing={other_unit.slug}").data]
    host_api.patch(f"/api/host/addons/{r.data['id']}", {"active": False}, format="json")
    assert "kayak" not in [a["code"] for a in api.get("/api/addons").data]
    assert [a["code"] for a in host_api.get("/api/host/addons").data] == ["kayak"]  # the host still sees it


# ---------- money: refunds ----------


def test_mark_a_queued_refund_as_sent(host_api, unit, guest):
    b = hold(unit, guest)
    act(host_api, b, "record-payment", amount=b.total, method="cash")  # paid at the door
    act(host_api, b, "cancel", reason="Double-booked by mistake")
    rf = Refund.objects.get(booking=b)
    assert (rf.status, rf.method, rf.amount) == ("pending", "manual", b.total)  # cash can't be refunded by a robot
    assert Alert.objects.filter(kind="payment", booking=b, summary__contains="Refund to send").exists()
    b.refresh_from_db()
    assert b.amount_refunded == 0
    r = host_api.post(f"/api/host/refunds/{rf.pk}/sent", {"reference": "Handed back in cash"}, format="json")
    assert r.status_code == 200 and r.data == {"ok": True}
    rf.refresh_from_db()
    b.refresh_from_db()
    assert rf.status == "success" and rf.provider_ref == "Handed back in cash" and rf.completed_at
    assert b.amount_refunded == b.total and b.payment_status == "refunded"
    assert Alert.objects.get(kind="payment", booking=b, summary__contains="Refund to send").status == "resolved"
    receipt = guest_messages(guest, "refund_sent").get().body
    assert kes(b.total) in receipt and "Handed back in cash" in receipt
    host_api.post(f"/api/host/refunds/{rf.pk}/sent", {"reference": None}, format="json")  # a second tap
    b.refresh_from_db()
    assert b.amount_refunded == b.total and guest_messages(guest, "refund_sent").count() == 1
    assert host_api.post("/api/host/refunds/999999/sent", {}, format="json").status_code == 404


# ---------- reviews ----------


def test_host_reviews_and_replies(host_api, api, unit, other_unit, guest, foreign_guest):
    a = stay(unit, guest, days(-10), 2)
    b = stay(other_unit, foreign_guest, days(-20), 2)
    ra = Review.objects.create(booking=a, unit=unit, guest=guest, rating=5, cleanliness=5, comment="Bliss")
    Review.objects.create(booking=b, unit=other_unit, guest=foreign_guest, rating=3, comment="Noisy road")
    d = host_api.get("/api/host/reviews").data
    assert d["summary"]["rating"] == 4.0 and d["summary"]["count"] == 2
    assert sorted((u["unit"], u["rating"]) for u in d["by_unit"]) == [("Palm Suite", 5.0), ("Reef Studio", 3.0)]
    row = next(x for x in d["reviews"] if x["id"] == ra.pk)
    assert (row["ref"], row["guest"], row["categories"]) == (a.ref, "Wanjiru Test", {"cleanliness": 5})
    r = host_api.post(f"/api/host/reviews/{ra.pk}/respond", {"text": "  Asante, karibu tena!  "}, format="json")
    assert r.status_code == 200
    ra.refresh_from_db()
    assert ra.host_response == "Asante, karibu tena!" and ra.responded_at
    assert api.get(f"/api/listings/{unit.slug}/reviews").data[0]["host_response"] == "Asante, karibu tena!"
    r = host_api.post(f"/api/host/reviews/{ra.pk}/respond", {"text": "  "}, format="json")
    assert r.status_code == 400
    ra.refresh_from_db()
    assert ra.host_response == "Asante, karibu tena!"
    assert host_api.post("/api/host/reviews/999999/respond", {"text": "x"}, format="json").status_code == 404


# ---------- walk-in / phone bookings from the console ----------


def _walk_in(host_api, unit, ci=3, co=5, **extra):
    body = {
        "unit": unit.pk,
        "check_in": days(ci).isoformat(),
        "check_out": days(co).isoformat(),
        "phone": "0722 111 333",
        "name": "Baraka Mwangi",
        "adults": 2,
        **extra,
    }
    return host_api.post("/api/host/reservations", body, format="json")


def test_walk_in_pay_on_arrival(host_api, unit, host):
    r = _walk_in(host_api, unit, payment="none")
    assert r.status_code == 201 and r.data["payment"] == {}
    b = Booking.objects.get(ref=r.data["booking"]["ref"])
    assert (b.status, b.channel, b.adults, b.payment_status, b.balance_due) == (
        "confirmed",
        "walk_in",
        2,
        "unpaid",
        b.total,
    )
    guest = User.objects.get(phone="+254722111333")
    assert guest.name == "Baraka Mwangi" and guest.first_channel == "walk_in" and b.guest == guest
    assert b.events.get(kind="held").actor == host
    assert guest_messages(guest, "booking_confirmed").exists()
    r = _walk_in(host_api, unit, ci=10, co=11, payment="none", name="Someone Else")
    guest.refresh_from_db()
    assert r.status_code == 201 and guest.name == "Baraka Mwangi" and User.objects.filter(role="guest").count() == 1


def test_walk_in_paid_in_cash(host_api, unit):
    q = price_quote(unit, days(3), days(5), guests=2)
    r = _walk_in(host_api, unit, payment="cash", amount=q["total"], notes="Paid at the gate")
    b = Booking.objects.get(ref=r.data["booking"]["ref"])
    assert (b.status, b.payment_status, b.amount_paid, b.special_requests) == (
        "confirmed",
        "paid",
        q["total"],
        "Paid at the gate",
    )
    assert Payment.objects.get(booking=b).method == "cash"


def test_walk_in_by_mpesa_and_card(host_api, unit, other_unit):
    r = _walk_in(host_api, unit, payment="mpesa")
    assert r.status_code == 201 and r.data["payment"]["method"] == "mpesa" and r.data["payment"]["status"] == "pending"
    assert r.data["booking"]["status"] == "held"
    r = _walk_in(host_api, other_unit, phone="+44 7700 900777", name="Lucy Visitor", payment="card", channel="whatsapp")
    b = Booking.objects.get(ref=r.data["booking"]["ref"])
    assert b.channel == "whatsapp" and b.status == "held"
    token = Payment.objects.get(booking=b).checkout_token
    assert Message.objects.filter(phone="+447700900777", kind="hold_card", body__contains=token).exists()
    r = _walk_in(host_api, unit, ci=20, co=22, phone="+44 7700 900888", payment="mpesa")
    assert r.status_code == 201 and "Kenyan" in r.data["payment"]["error"]


def test_walk_in_errors(host_api, unit, guest):
    confirmed(unit, guest, ci=3)
    r = _walk_in(host_api, unit, payment="none")
    assert r.status_code == 409 and "taken" in r.data["error"]
    r = _walk_in(host_api, unit, ci=20, co=22, phone="12", payment="none")
    assert r.status_code == 409 and "valid phone number" in r.data["error"]
    r = _walk_in(host_api, unit, ci=20, co=22, adults=9, payment="none")
    assert r.status_code == 409 and "sleeps up to 4" in r.data["error"]
    assert host_api.post("/api/host/reservations", {"unit": 99999}, format="json").status_code == 404
    r = _walk_in(host_api, unit, ci=30, co=32, channel="airbnb", payment="none")
    assert Booking.objects.get(ref=r.data["booking"]["ref"]).channel == "airbnb"
    r = _walk_in(host_api, unit, ci=40, co=42, channel="space-station", payment="none")
    assert Booking.objects.get(ref=r.data["booking"]["ref"]).channel == "walk_in"
