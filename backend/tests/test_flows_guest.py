"""Guest web flows end to end over HTTP: login, profile & privacy rights, wishlist, discovery and the whole trip."""

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import OTPCode, User
from apps.bookings import services as bookings
from apps.bookings.models import Addon, Booking, BookingAddon, BookingGuest
from apps.comms.at import ATError
from apps.core import crypto
from apps.core.models import SiteSettings
from apps.core.utils import kes
from apps.messaging import services as messaging
from apps.messaging.models import FAQ, Message
from apps.operations.models import Task
from apps.payments import services as payments
from apps.payments.models import Payment
from apps.properties.models import Amenity, Area, CalendarBlock, PriceOverride, Unit, Wishlist
from apps.properties.services import quote as price_quote
from apps.reviews.models import Review
from apps.safety.models import Alert

from .conftest import days
from .flowkit import frozen

pytestmark = pytest.mark.django_db


# ---------- helpers ----------


def hold(unit, guest, ci=10, nights=2, **kw):
    kw.setdefault("channel", "web")
    return bookings.create_hold(unit=unit, guest=guest, check_in=days(ci), check_out=days(ci + nights), **kw)


def settle(b, **kw):
    """Pay what is due now and let the (simulated) provider call back."""
    r = payments.start_payment(b, **kw)
    payments.on_success(Payment.objects.get(pk=r["payment_id"]), transaction_id=f"T{r['payment_id']}")
    b.refresh_from_db()
    return b


def confirmed(unit, guest, ci=10, nights=2, **kw):
    return settle(hold(unit, guest, ci, nights, **kw))


def checked_in(unit, guest, ci=0, nights=2, **kw):
    b = confirmed(unit, guest, ci, nights, **kw)
    assert bookings.release_code(b, force=True) == "released"
    b.refresh_from_db()
    return b


def past_stay(unit, guest, ago=10, nights=2, rating=None, **review):
    b = Booking.objects.create(
        ref=Booking.new_ref(),
        unit=unit,
        guest=guest,
        check_in=days(-ago),
        check_out=days(-ago + nights),
        status="completed",
        channel="web",
        total=20_000,
        amount_paid=20_000,
        payment_status="paid",
        cancellation_policy=unit.cancellation_policy,
    )
    if rating:
        Review.objects.create(booking=b, unit=unit, guest=guest, rating=rating, channel="web", **review)
    return b


def host_messages(kind=None):
    qs = Message.objects.filter(phone=SiteSettings.load().host_contact, direction="out")
    return qs.filter(kind=kind) if kind else qs


def as_user(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def otp(api, phone, ip="10.1.1.1"):
    return api.post("/api/auth/otp/request", {"phone": phone}, format="json", REMOTE_ADDR=ip)


def verify(api, phone, code, ip="10.1.1.1"):
    return api.post("/api/auth/otp/verify", {"phone": phone, "code": code}, format="json", REMOTE_ADDR=ip)


def allow_resend(phone):
    OTPCode.objects.filter(phone=phone).update(sent_at=timezone.now() - timedelta(seconds=31))


@pytest.fixture
def extras(db, other_unit):
    pickup = Addon.objects.create(
        code="airport_pickup",
        name="Airport pickup",
        category="transport",
        price=2_500,
        pricing="per_stay",
        sort_order=1,
    )
    daily = Addon.objects.create(
        code="daily_clean", name="Daily housekeeping", category="cleaning", price=800, pricing="per_night", sort_order=2
    )
    cruise = Addon.objects.create(
        code="dhow_cruise",
        name="Sunset dhow cruise",
        category="experience",
        price=4_500,
        pricing="per_guest",
        sort_order=3,
    )
    towels = Addon.objects.create(
        code="mid_stay_clean", name="Mid-stay clean", category="cleaning", price=1_500, pricing="per_item", sort_order=4
    )
    early = Addon.objects.create(
        code="early_checkin",
        name="Early check-in (from 11am)",
        category="flexibility",
        price=1_500,
        pricing="per_stay",
        requires_approval=True,
        options={"time": "11:00"},
        sort_order=5,
    )
    late = Addon.objects.create(
        code="late_checkout",
        name="Late checkout (until 2pm)",
        category="flexibility",
        price=1_500,
        pricing="per_stay",
        requires_approval=True,
        options={"time": "14:00"},
        sort_order=6,
    )
    snorkel = Addon.objects.create(
        code="reef_snorkel",
        name="Reef snorkelling",
        category="experience",
        price=3_000,
        pricing="per_guest",
        sort_order=7,
    )
    snorkel.units.set([other_unit])
    retired = Addon.objects.create(code="retired", name="Old extra", price=100, active=False, sort_order=8)
    return SimpleNamespace(
        pickup=pickup,
        daily=daily,
        cruise=cruise,
        towels=towels,
        early=early,
        late=late,
        snorkel=snorkel,
        retired=retired,
    )


# ---------- auth ----------


def test_csrf_token_is_required_for_session_writes(guest):
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(guest)
    assert client.patch("/api/me", {"name": "No token"}, format="json").status_code == 403
    r = client.get("/api/auth/csrf")
    assert r.status_code == 200 and r.json()["csrfToken"] and client.cookies["csrftoken"].value
    r = client.patch("/api/me", {"name": "Wanjiru K"}, format="json", HTTP_X_CSRFTOKEN=r.json()["csrfToken"])
    assert r.status_code == 200 and r.data["name"] == "Wanjiru K"


@pytest.mark.parametrize(
    ("raw", "phone"),
    [
        ("0712 345 678", "+254712345678"),
        ("254712345678", "+254712345678"),
        ("712-345-678", "+254712345678"),
        ("+254 (0)712 345 678", "+254712345678"),
        ("+2540712345678", "+254712345678"),
        ("0112 345 678", "+254112345678"),
        ("+44 7700 900123", "+447700900123"),
        ("+44 (0)7700 900123", "+447700900123"),
        ("0044 7700 900123", "+447700900123"),
        ("12345", None),
        ("", None),
    ],
)
def test_otp_request_normalises_the_phone_number(api, raw, phone):
    r = otp(api, raw)
    if phone is None:
        assert r.status_code == 400 and "valid phone number" in r.data["error"]
        assert not OTPCode.objects.exists()
        return
    assert r.status_code == 200 and r.data["phone"] == phone
    code = r.data["debug_code"]
    row = OTPCode.objects.get(phone=phone)
    assert len(code) == 6 and code not in row.code_hash  # only a keyed hash of the code is stored
    sms = Message.objects.get(phone=phone, kind="otp")
    assert code not in sms.body and messaging.REDACTED in sms.body and sms.direction == "out"  # only the SMS has it


def test_otp_login_logout_and_single_use_code(api):
    phone = "+254712000111"
    code = otp(api, "0712 000 111").data["debug_code"]
    r = verify(api, "0712000111", code)  # the same number typed differently still matches
    assert r.status_code == 200 and r.data["authenticated"] and r.data["phone"] == phone
    user = User.objects.get(phone=phone)
    assert user.first_channel == "web" and user.role == "guest" and not r.data["is_host"]
    assert not OTPCode.objects.filter(phone=phone).exists()
    assert api.get("/api/me").data["phone"] == phone
    assert verify(api, phone, code).status_code == 400  # a code works once
    assert api.post("/api/auth/logout").data == {"ok": True}
    assert api.get("/api/me").data == {"authenticated": False}
    assert User.objects.filter(phone=phone).count() == 1


def test_otp_wrong_code_locks_after_five_attempts(api):
    phone = "+254712000222"
    code = otp(api, phone).data["debug_code"]
    wrong = "111111" if code != "111111" else "222222"
    for _ in range(5):
        r = verify(api, phone, wrong)
        assert r.status_code == 400 and "isn't right" in r.data["error"]
    r = verify(api, phone, code)
    assert r.status_code == 400 and "Too many attempts" in r.data["error"]
    assert not User.objects.filter(phone=phone).exists()
    allow_resend(phone)
    code = otp(api, phone).data["debug_code"]  # a new code resets the attempts
    assert verify(api, phone, code).status_code == 200


def test_otp_code_expires(api):
    phone = "+254712000333"
    code = otp(api, phone).data["debug_code"]
    OTPCode.objects.filter(phone=phone).update(expires_at=timezone.now() - timedelta(seconds=1))
    r = verify(api, phone, code)
    assert r.status_code == 400 and "expired" in r.data["error"]
    assert verify(api, "+254712000999", "123456").status_code == 400  # never requested


def test_otp_resend_gap_and_hourly_cap_per_number(api):
    phone = "+254712000444"
    assert otp(api, phone, ip="10.0.0.1").status_code == 200
    r = otp(api, phone, ip="10.0.0.2")
    assert r.status_code == 400 and "30 seconds" in r.data["error"]
    for i in range(4):  # five codes per number per hour, whatever the IP
        allow_resend(phone)
        assert otp(api, phone, ip=f"10.0.1.{i}").status_code == 200
    allow_resend(phone)
    r = otp(api, phone, ip="10.0.2.1")
    assert r.status_code == 400 and "Too many codes" in r.data["error"]
    assert Message.objects.filter(phone=phone, kind="otp").count() == 5


def test_otp_hourly_cap_lasts_the_hour_on_the_shared_database_cache(api, settings):
    # production's workers share a DatabaseCache, whose incr() would cut the hour to its 5-minute default timeout
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "otp_cap"}}
    call_command("createcachetable")
    phone, start = "+254712000445", timezone.now().replace(minute=1, second=0, microsecond=0)
    with frozen(start):
        for i in range(5):
            allow_resend(phone)
            assert otp(api, phone, ip=f"10.0.3.{i}").status_code == 200
    cache_clock = timezone.now() + timedelta(minutes=40)  # the cache judges expiry on its own clock
    with (
        frozen(start + timedelta(minutes=40)),
        mock.patch("django.core.cache.backends.db.tz_now", return_value=cache_clock),
    ):
        allow_resend(phone)
        r = otp(api, phone, ip="10.0.4.1")
    assert r.status_code == 400 and "Too many codes" in r.data["error"]


def test_otp_requests_are_rate_limited_per_ip(api):
    for i in range(6):
        assert otp(api, f"+25471200050{i}", ip="10.9.9.9").status_code == 200
    assert otp(api, "+254712000599", ip="10.9.9.9").status_code == 429
    assert otp(api, "+254712000599", ip="10.9.9.10").status_code == 200


def test_debug_code_is_only_returned_in_demo_mode(api, settings):
    settings.DEMO = False
    r = otp(api, "+254712000666")
    assert r.status_code == 200 and "debug_code" not in r.data


def test_disabled_account_cannot_log_in(api):
    User.objects.create_user("+254712000777", is_active=False)
    code = otp(api, "+254712000777").data["debug_code"]
    r = verify(api, "+254712000777", code)
    assert r.status_code == 400 and "disabled" in r.data["error"]
    assert api.get("/api/me").data == {"authenticated": False}


def test_a_login_code_reaches_the_guests_phone_and_no_one_elses_screen(
    api, guest, guest_api, host_api, settings, django_capture_on_commit_callbacks
):
    messaging.send(guest.phone, "Karibu! Your booking is confirmed.")  # the guest already has a thread in the inbox
    settings.AT_API_KEY = "live-key"
    at_took_it = {
        "SMSMessageData": {
            "Recipients": [{"number": guest.phone, "status": "Success", "statusCode": 101, "messageId": "ATXid_otp"}]
        }
    }
    with (
        mock.patch("apps.accounts.services.secrets.randbelow", return_value=531_642),
        mock.patch("apps.comms.at._post", return_value=at_took_it) as post,
        django_capture_on_commit_callbacks(execute=True),
    ):
        code = otp(api, guest.phone).data["debug_code"]  # on screen in DEMO mode only
    assert code == "631642" and code in post.call_args.kwargs["data"]["message"]  # the SMS carries the code...
    stored = Message.objects.get(phone=guest.phone, kind="otp")
    assert stored.status == "sent" and code not in stored.body and code not in str(stored)  # ...nothing else does
    [row] = [r for r in host_api.get("/api/host/inbox").json() if r["phone"] == guest.phone]
    thread = host_api.get(f"/api/host/inbox/{row['id']}").json()
    assert row["last_preview"] == thread["thread"]["last_preview"] == "Karibu! Your booking is confirmed."
    assert [m["body"] for m in thread["messages"] if m["kind"] == "otp"] == [stored.body]
    assert all(code not in m["body"] for m in thread["messages"])
    assert host_api.get(f"/api/host/inbox?q={code}").json() == []
    assert all(code not in m["body"] for m in guest_api.get("/api/messages").json()["messages"])
    api.post("/at/sms/delivery", {"id": "ATXid_otp", "status": "Success"})  # delivery reports still land
    stored.refresh_from_db()
    assert stored.status == "delivered"


def test_a_login_sms_that_fails_is_never_sent_again_from_storage(api, settings, django_capture_on_commit_callbacks):
    settings.AT_API_KEY = "live-key"
    phone = "+254712000888"
    with (
        mock.patch("apps.comms.at._post", side_effect=ATError("network error: timeout")),
        django_capture_on_commit_callbacks(execute=True),
    ):
        otp(api, phone)
    m = Message.objects.get(phone=phone, kind="otp")
    assert (m.status, m.next_attempt_at, m.attempts) == ("failed", None, 1)  # the guest asks for a new code instead
    Message.objects.filter(pk=m.pk).update(status="queued")  # say a worker died mid-send and its lease ran out
    with mock.patch("apps.comms.at._post") as post:
        messaging.dispatch(m.pk)
    assert not post.called and Message.objects.get(pk=m.pk).status == "failed"


def test_login_codes_stored_before_the_fix_are_redacted(guest):
    from importlib import import_module

    from django.apps import apps

    old = messaging.send(guest.phone, "Your Amina Stays code is 638059. It expires in 5 minutes.", kind="otp")
    note = messaging.send("+254733000999", "Booking AMS-638059: 638059 is not a login code", kind="booking")
    import_module("apps.messaging.migrations.0003_redact_login_codes").redact_login_codes(apps, None)
    old.refresh_from_db(), note.refresh_from_db()
    assert old.body == "Your Amina Stays code is ••••••. It expires in 5 minutes." == old.thread.last_preview
    assert note.body == "Booking AMS-638059: 638059 is not a login code"


# ---------- profile & privacy ----------


def test_profile_read_and_update(guest, guest_api, api):
    assert api.get("/api/me").data == {"authenticated": False}
    assert api.patch("/api/me", {"name": "Hacker"}, format="json").status_code == 401
    guest.sms_opt_out_at = timezone.now()
    guest.save()
    r = guest_api.patch(
        "/api/me",
        {
            "name": "  Wanjiru Kamau ",
            "email": "wanjiru@example.com",
            "lang": "sw",
            "nationality": "ke",
            "preferred_channel": "whatsapp",
            "marketing_opt_in": True,
            "phone": "+254799999999",
            "role": "owner",
        },
        format="json",
    )
    assert r.status_code == 200
    assert (r.data["name"], r.data["email"], r.data["lang"], r.data["nationality"]) == (
        "Wanjiru Kamau",
        "wanjiru@example.com",
        "sw",
        "KE",
    )
    assert r.data["preferred_channel"] == "whatsapp" and r.data["marketing_opt_in"] is True
    guest.refresh_from_db()
    assert guest.sms_opt_out_at is None  # opting in again lifts an earlier STOP
    assert guest.phone == "+254711000001" and guest.role == "guest" and not r.data["is_host"]  # not editable here

    r = guest_api.patch("/api/me", {"lang": "xx", "preferred_channel": "telegram"}, format="json")
    assert r.data["lang"] == "sw" and r.data["preferred_channel"] == "whatsapp"  # unknown choices are ignored
    r = guest_api.patch("/api/me", {"marketing_opt_in": False, "email": ""}, format="json")
    assert r.data["marketing_opt_in"] is False and r.data["email"] == ""

    r = guest_api.patch("/api/me", {"email": "wanjiru@"}, format="json")
    assert r.status_code == 400 and "email" in r.data["error"].lower()
    guest.refresh_from_db()
    assert guest.email == ""  # a typo never reaches the card processor's receipt address


def test_identity_needs_consent_and_is_stored_encrypted(guest, guest_api, api, unit):
    b = hold(unit, guest)  # an active booking: its guest-register line follows the profile
    assert api.post("/api/me/identity", {"id_number": "28123456", "consent": True}, format="json").status_code in (
        401,
        403,
    )
    r = guest_api.post("/api/me/identity", {"id_type": "national_id", "id_number": "28123456"}, format="json")
    assert r.status_code == 400 and "consent" in r.data["error"]
    r = guest_api.post("/api/me/identity", {"id_number": "123", "consent": True}, format="json")
    assert r.status_code == 400
    guest.refresh_from_db()
    assert not guest.has_id

    r = guest_api.post(
        "/api/me/identity", {"id_type": "national_id", "id_number": "28123456", "consent": True}, format="json"
    )
    assert r.status_code == 200
    assert r.data["identity"]["last4"] == "••••3456" and r.data["identity"]["type"] == "national_id"
    assert "28123456" not in r.content.decode()
    guest.refresh_from_db()
    assert guest.id_number_enc and "28123456" not in guest.id_number_enc
    assert guest.get_id_number() == "28123456" and guest.nationality == "KE" and guest.consent_at
    lead = b.occupants.get(is_lead=True)
    assert lead.id_last4 == "••••3456" and crypto.decrypt(lead.id_number_enc) == "28123456"
    assert lead.full_name == "Wanjiru Test" and lead.nationality == "KE"


def test_foreign_passport_identity(foreign_guest):
    r = as_user(foreign_guest).post(
        "/api/me/identity", {"id_number": "x1234567", "nationality": "gb", "consent": True}, format="json"
    )
    assert r.status_code == 200
    foreign_guest.refresh_from_db()
    assert foreign_guest.id_type == "passport" and foreign_guest.get_id_number() == "X1234567"
    assert foreign_guest.nationality == "GB" and r.data["identity"]["last4"] == "••••4567"


def test_data_export_contains_everything_about_me_and_nothing_else(
    guest, guest_api, api, unit, other_unit, foreign_guest
):
    assert api.get("/api/me/export").status_code in (401, 403)
    guest.id_type = "national_id"
    guest.set_id_number("28123456")
    guest.email = "w@example.com"
    guest.save()
    b = confirmed(unit, guest)
    theirs = hold(other_unit, foreign_guest)
    r = guest_api.get("/api/me/export")
    assert r.status_code == 200 and "attachment" in r["Content-Disposition"]
    d = r.data
    assert d["profile"]["phone"] == guest.phone and d["profile"]["email"] == "w@example.com"
    assert d["profile"]["id_document"] == "Kenyan National ID ending ••••3456"
    assert [x["ref"] for x in d["bookings"]] == [b.ref] and d["bookings"][0]["paid"] == b.total
    assert any(m["text"].startswith("Booked!") for m in d["messages"])
    body = r.content.decode()
    assert "28123456" not in body and theirs.ref not in body and foreign_guest.phone not in body


def _login(user):
    client = APIClient()
    client.force_login(user)
    return client


def test_erasure_without_a_stay_wipes_personal_data(guest, unit):
    guest.email, guest.marketing_opt_in, guest.host_notes, guest.tags = "w@example.com", True, "Lovely", ["vip"]
    guest.id_type = "national_id"
    guest.set_id_number("28123456")
    guest.save()
    Wishlist.objects.create(user=guest, unit=unit)
    abandoned = hold(unit, guest)  # booked but never paid, then cancelled: no stay, no register duty
    bookings.cancel(abandoned, by="guest")
    messaging.send(guest.phone, "Your code is 123456", kind="otp")
    client = _login(guest)

    r = client.post("/api/me/erase")
    assert r.status_code == 200 and r.data == {"erased": True, "register_kept": False}
    guest.refresh_from_db()
    assert (guest.name, guest.email, guest.id_type, guest.id_number_enc, guest.id_last4) == ("", "", "", "", "")
    assert not guest.marketing_opt_in and guest.sms_opt_out_at and guest.host_notes == "" and guest.tags == []
    assert not Wishlist.objects.filter(user=guest).exists()
    assert set(Message.objects.filter(phone=guest.phone).values_list("body", flat=True)) == {
        "[erased at guest's request]"
    }
    line = abandoned.occupants.get()
    assert line.full_name != "Wanjiru Test" and line.id_number_enc == "" and line.id_last4 == ""
    assert client.get("/api/me").data == {"authenticated": False}  # logged out
    assert Booking.objects.filter(pk=abandoned.pk).exists()  # the financial record stays


def test_erasure_keeps_the_legal_guest_register(guest, unit):
    guest.email, guest.marketing_opt_in = "w@example.com", True
    guest.id_type = "national_id"
    guest.set_id_number("28123456")
    guest.save()
    stay = checked_in(unit, guest)
    bookings.check_out(stay)
    r = _login(guest).post("/api/me/erase")
    assert r.data == {"erased": True, "register_kept": True}
    guest.refresh_from_db()
    assert guest.name == "Wanjiru Test" and guest.get_id_number() == "28123456"  # kept for the TRA register
    assert guest.email == "" and not guest.marketing_opt_in and guest.sms_opt_out_at
    lead = stay.occupants.get(is_lead=True)
    assert lead.full_name == "Wanjiru Test" and crypto.decrypt(lead.id_number_enc) == "28123456"


# ---------- wishlist ----------


def test_wishlist_add_list_remove(guest, guest_api, api, unit, other_unit):
    for method, url, body in (
        ("get", "/api/me/wishlist", None),
        ("post", "/api/me/wishlist", {"slug": unit.slug}),
        ("delete", f"/api/me/wishlist/{unit.slug}", None),
    ):
        assert getattr(api, method)(url, body, format="json").status_code in (401, 403)
    assert guest_api.post("/api/me/wishlist", {"slug": unit.slug}, format="json").status_code == 201
    assert guest_api.post("/api/me/wishlist", {"slug": unit.slug}, format="json").status_code == 201
    assert guest_api.post("/api/me/wishlist", {"slug": other_unit.slug}, format="json").status_code == 201
    assert guest_api.post("/api/me/wishlist", {"slug": "no-such-home"}, format="json").status_code == 404
    assert Wishlist.objects.filter(user=guest).count() == 2

    saved = guest_api.get("/api/me/wishlist").data
    assert {c["slug"] for c in saved} == {unit.slug, other_unit.slug} and all(c["wishlisted"] for c in saved)
    cards = {c["slug"]: c["wishlisted"] for c in guest_api.get("/api/listings").data["results"]}
    assert cards == {unit.slug: True, other_unit.slug: True}
    assert not any(c["wishlisted"] for c in api.get("/api/listings").data["results"])

    other_unit.status = "paused"
    other_unit.save()
    assert [c["slug"] for c in guest_api.get("/api/me/wishlist").data] == [unit.slug]
    assert guest_api.delete(f"/api/me/wishlist/{unit.slug}").status_code == 204
    assert guest_api.get("/api/me/wishlist").data == []


# ---------- discovery ----------


def test_public_config(api, site, settings):
    r = api.get("/api/config")
    assert r.status_code == 200
    d = r.data
    assert d["business"]["name"] == site.business_name and d["business"]["checkin_time"] == "14:00"
    assert (d["deposit_percent"], d["hold_minutes"], d["levy_percent"]) == (30, 10, 2.0)
    assert d["payments"] == {"mpesa": "simulate", "card": "simulate", "simulated": True, "card_test_mode": False}
    assert d["demo"] is True and "demo_lab" in d and d["require_id"] is True
    settings.DEMO = False
    assert "demo_lab" not in api.get("/api/config").data


def test_areas_count_listed_homes_only(api, area, unit, other_unit):
    Area.objects.create(name="Nyali", slug="nyali", sort_order=1)
    other_unit.status = "paused"
    other_unit.save()
    by_slug = {a["slug"]: a for a in api.get("/api/areas").data}
    assert by_slug["diani"]["units_count"] == 1 and by_slug["diani"]["location"] == {"lat": -4.3, "lng": 39.58}
    assert by_slug["nyali"]["units_count"] == 0 and by_slug["nyali"]["location"] is None


def test_amenities_catalogue(api):
    Amenity.objects.create(code="pool", name="Pool", category="outdoor", icon="waves", sort_order=2)
    Amenity.objects.create(code="wifi", name="Fast Wi-Fi", category="essentials", icon="wifi", sort_order=1)
    data = api.get("/api/amenities").data
    assert [a["code"] for a in data] == ["wifi", "pool"] and data[0]["name"] == "Fast Wi-Fi"


def test_addons_catalogue_and_per_listing(api, unit, other_unit, breakfast, extras):
    def codes(query=""):
        return [a["code"] for a in api.get(f"/api/addons{query}").data]

    everything = [
        "breakfast",
        "airport_pickup",
        "daily_clean",
        "dhow_cruise",
        "mid_stay_clean",
        "early_checkin",
        "late_checkout",
    ]
    assert codes() == [*everything, "reef_snorkel"]  # inactive extras never show
    assert codes(f"?listing={unit.slug}") == everything  # reef snorkelling is only offered at Reef Studio
    other_unit.breakfast_available = False
    other_unit.save()
    assert codes(f"?listing={other_unit.slug}") == [*everything[1:], "reef_snorkel"]  # no kitchen, no breakfast
    early = next(a for a in api.get("/api/addons").data if a["code"] == "early_checkin")
    assert early["requires_approval"] is True and early["pricing_label"] == "per stay" and early["price"] == 1500


def test_public_faqs_only_show_public_facts(api):
    FAQ.objects.create(
        category="check_in", question="What time is check-in?", keywords="check in", answer_en="From {checkin_time}."
    )
    FAQ.objects.create(category="wifi", question="Wi-Fi password?", keywords="wifi", answer_en="It is {wifi}.")
    FAQ.objects.create(category="other", question="Hidden", keywords="x", answer_en="No", active=False)
    data = api.get("/api/faqs").data
    assert [(f["question"], f["answer"]) for f in data] == [("What time is check-in?", "From 2pm.")]


@pytest.fixture
def villa(area, unit, other_unit):
    """Three homes: Palm Suite (Diani, flexible), Reef Studio (Diani, moderate) and Baobab Villa (Nyali, strict)."""
    pool = Amenity.objects.create(code="pool", name="Pool")
    wifi = Amenity.objects.create(code="wifi", name="Wi-Fi")
    unit.amenities.set([wifi])
    nyali = Area.objects.create(name="Nyali", slug="nyali")
    v = Unit.objects.create(
        name="Baobab Villa",
        area=nyali,
        property_type="villa",
        bedrooms=3,
        max_guests=8,
        base_price=25_000,
        cancellation_policy="strict",
        tags=["beachfront", "pool"],
        is_featured=True,
    )
    v.amenities.set([pool, wifi])
    return v


def _names(api, query=""):
    r = api.get(f"/api/listings{query}")
    assert r.status_code == 200, r.data
    return [c["name"] for c in r.data["results"]]


def test_search_filters(api, unit, other_unit, villa, guest, foreign_guest):
    Unit.objects.create(name="Draft Cottage", area=unit.area, base_price=1_000, status="draft")
    assert sorted(_names(api)) == ["Baobab Villa", "Palm Suite", "Reef Studio"]
    assert sorted(_names(api, "?area=diani")) == ["Palm Suite", "Reef Studio"]
    assert _names(api, "?area=Nyali") == ["Baobab Villa"]
    assert sorted(_names(api, "?guests=3")) == ["Baobab Villa", "Palm Suite"]
    assert _names(api, "?tag=pool") == ["Baobab Villa"]
    assert sorted(_names(api, "?type=villa,apartment")) == ["Baobab Villa", "Palm Suite", "Reef Studio"]
    assert _names(api, "?type=villa") == ["Baobab Villa"]
    assert _names(api, "?bedrooms=2") == ["Baobab Villa"]
    assert _names(api, "?amenities=pool,wifi") == ["Baobab Villa"]  # every amenity must match
    assert sorted(_names(api, "?amenities=wifi")) == ["Baobab Villa", "Palm Suite"]
    assert sorted(_names(api, "?free_cancellation=1")) == ["Palm Suite", "Reef Studio"]
    # "from" prices: Palm 11,220 (10,000 + half the cleaning fee + 2% levy), Reef 5,100, Baobab 25,500
    assert sorted(_names(api, "?min_price=6000")) == ["Baobab Villa", "Palm Suite"]
    assert sorted(_names(api, "?max_price=12000")) == ["Palm Suite", "Reef Studio"]
    assert _names(api, "?min_price=6000&max_price=12000") == ["Palm Suite"]
    assert _names(api, "?sort=price") == ["Reef Studio", "Palm Suite", "Baobab Villa"]

    for i in range(5):  # five 5-star stays make Reef Studio a guest favourite
        who = User.objects.create_user(f"+25472200000{i}", name=f"Guest {i}")
        past_stay(other_unit, who, ago=40 - 3 * i, rating=5)
    past_stay(unit, guest, rating=4)
    assert _names(api, "?guest_favourite=1") == ["Reef Studio"]
    assert _names(api, "?sort=rating") == ["Reef Studio", "Palm Suite", "Baobab Villa"]
    assert _names(api)[0] == "Baobab Villa"  # featured homes lead the default order

    # dates: a confirmed stay and a calendar block take homes out of the results
    confirmed(unit, guest, ci=10, nights=2)
    CalendarBlock.objects.create(unit=other_unit, start_date=days(11), end_date=days(12), reason="maintenance")
    r = api.get(f"/api/listings?check_in={days(10)}&check_out={days(12)}")
    assert [c["name"] for c in r.data["results"]] == ["Baobab Villa"] and r.data["nights"] == 2
    q = price_quote(villa, days(10), days(12))
    assert r.data["results"][0]["price"]["total"] == q["total"]
    assert sorted(_names(api, f"?check_in={days(12)}&check_out={days(14)}")) == [
        "Baobab Villa",
        "Palm Suite",
        "Reef Studio",
    ]  # check-out day is free again
    r = api.get(f"/api/listings?check_in={days(-3)}&check_out={days(-1)}")
    assert r.data["count"] == 3 and r.data["nights"] is None  # past dates are ignored, not an error
    assert _names(api, f"?check_in={days(10)}&check_out={days(12)}&area=nyali&guests=8") == ["Baobab Villa"]


def test_listing_detail_keeps_private_details_private(api, unit, breakfast, extras, other_unit):
    unit.latitude, unit.longitude = Decimal("-4.301230"), Decimal("39.584560")
    unit.save()
    r = api.get(f"/api/listings/{unit.slug}")
    assert r.status_code == 200
    body = r.content.decode()
    for secret in (unit.address, unit.wifi_name, unit.wifi_password, unit.directions, "39.58456"):
        assert secret not in body
    assert r.data["location"] and r.data["location"] != {"lat": -4.30123, "lng": 39.58456}
    assert r.data["cancellation"]["policy"] == "flexible" and r.data["min_nights"] == 1
    assert [a["code"] for a in r.data["addons"]] == [
        "breakfast",
        "airport_pickup",
        "daily_clean",
        "dhow_cruise",
        "mid_stay_clean",
        "early_checkin",
        "late_checkout",
    ]
    other_unit.breakfast_available = False
    other_unit.save()
    codes = [a["code"] for a in api.get(f"/api/listings/{other_unit.slug}").data["addons"]]
    assert "breakfast" not in codes and "reef_snorkel" in codes
    unit.status = "paused"
    unit.save()
    assert api.get(f"/api/listings/{unit.slug}").status_code == 404
    assert api.get("/api/listings/no-such-home").status_code == 404


def test_calendar_marks_taken_nights(api, unit, guest):
    confirmed(unit, guest, ci=3, nights=2)
    CalendarBlock.objects.create(unit=unit, start_date=days(8), end_date=days(9), reason="owner")
    PriceOverride.objects.create(unit=unit, date=days(6), price=15_000)
    r = api.get(f"/api/listings/{unit.slug}/calendar?start={days(-5)}&end={days(10)}")
    assert r.status_code == 200 and r.data["start"] == days(0)  # never shows the past
    assert r.data["unavailable"] == [days(3).isoformat(), days(4).isoformat(), days(8).isoformat()]
    assert r.data["prices"][days(6).isoformat()] == 15_000 and r.data["prices"][days(5).isoformat()] == 10_000
    assert len(r.data["prices"]) == 10 and r.data["min_nights"] == 1 and r.data["max_nights"] == 60
    default = api.get(f"/api/listings/{unit.slug}/calendar").data
    assert default["end"] == days(120) and days(3).isoformat() in default["unavailable"]


def test_quote_checks_every_rule(api, unit, guest, breakfast):
    unit.min_nights, unit.max_nights = 2, 14
    unit.save()

    def quote(**body):
        body = {k: v.isoformat() if hasattr(v, "isoformat") else v for k, v in body.items()}
        return api.post(f"/api/listings/{unit.slug}/quote", body, format="json")

    r = quote(check_in=days(10), check_out=days(13), adults=2, addons=[{"code": "breakfast"}], payment_plan="deposit")
    assert r.status_code == 200 and r.data["available"] is True and r.data["problems"] == []
    assert r.data["nights"] == 3 and r.data["addons"] == 650 * 2 * 3  # defaults to everyone eating
    assert r.data["deposit_available"] and r.data["due_now"] == r.data["deposit"] == -(-r.data["total"] * 30 // 100)
    assert sum(line["amount"] for line in r.data["lines"]) == r.data["total"]
    full = quote(check_in=days(10), check_out=days(13), adults=2, addons=[{"code": "breakfast", "quantity": 1}])
    assert full.data["addons"] == 650 * 3 and full.data["due_now"] == full.data["total"]

    def problems(**body):
        r = quote(**body)
        assert r.status_code == 200 and r.data["available"] is False
        return " ".join(r.data["problems"])

    assert "Minimum stay is 2 nights" in problems(check_in=days(10), check_out=days(11))
    assert "14 nights" in problems(check_in=days(10), check_out=days(30))
    assert "18 months" in problems(check_in=days(600), check_out=days(603))
    assert "up to 4 guests" in problems(check_in=days(10), check_out=days(12), adults=3, children=2)
    assert "in the past" in problems(check_in=days(-2), check_out=days(1))
    confirmed(unit, guest, ci=20, nights=3)
    assert "aren't available" in problems(check_in=days(21), check_out=days(23))
    assert quote(check_in=days(23), check_out=days(25)).data["available"] is True  # back-to-back is fine

    near = quote(check_in=days(1), check_out=days(3), payment_plan="deposit").data
    assert near["deposit_available"] is False and near["due_now"] == near["total"]
    assert quote(check_in=days(5), check_out=days(5)).status_code == 400
    assert quote(check_in="soon").status_code == 400
    assert Booking.objects.count() == 1  # quoting never holds anything


def test_listing_reviews_are_public_with_first_names_only(api, unit, guest, foreign_guest):
    past_stay(unit, guest, rating=5, comment="Asante sana!", cleanliness=5, location=4, host_response="Karibu tena")
    past_stay(unit, foreign_guest, ago=20, rating=2, comment="Hidden", is_public=False)
    data = api.get(f"/api/listings/{unit.slug}/reviews").data
    assert len(data) == 1
    assert data[0]["guest"] == "Wanjiru" and data[0]["rating"] == 5 and data[0]["host_response"] == "Karibu tena"
    assert data[0]["categories"] == {"cleanliness": 5, "location": 4}
    assert guest.phone not in str(data)


def test_ical_export_feed(api, unit, guest, foreign_guest):
    confirmed(unit, guest, ci=5, nights=3)
    lapsed = hold(unit, foreign_guest, ci=20)
    Booking.objects.filter(pk=lapsed.pk).update(hold_expires_at=timezone.now() - timedelta(minutes=1))
    CalendarBlock.objects.create(unit=unit, start_date=days(10), end_date=days(12), reason="owner")
    CalendarBlock.objects.create(unit=unit, start_date=days(14), end_date=days(15), reason="external")
    r = api.get(f"/api/ical/{unit.ical_token}.ics")
    assert r.status_code == 200 and r["Content-Type"].startswith("text/calendar")
    body = r.content.decode()
    assert body.startswith("BEGIN:VCALENDAR") and body.count("BEGIN:VEVENT") == 2
    assert f"DTSTART;VALUE=DATE:{days(5):%Y%m%d}" in body and f"DTEND;VALUE=DATE:{days(8):%Y%m%d}" in body
    assert f"DTSTART;VALUE=DATE:{days(10):%Y%m%d}" in body
    assert f"{days(14):%Y%m%d}" not in body and f"{days(20):%Y%m%d}" not in body
    assert guest.name not in body and guest.phone not in body
    assert api.get("/api/ical/not-a-token.ics").status_code == 404


# ---------- booking ----------


def _book(client, unit, ci, co, **extra):
    body = {"listing": unit.slug, "check_in": days(ci).isoformat(), "check_out": days(co).isoformat(), **extra}
    return client.post("/api/bookings", body, format="json")


def test_book_in_full_with_extras_identity_and_mpesa(guest, guest_api, unit, breakfast, extras, host):
    r = _book(
        guest_api,
        unit,
        10,
        13,
        adults=2,
        children=1,
        infants=1,
        payment_plan="full",
        payment_method="mpesa",
        addons=[
            {"code": "breakfast", "quantity": 2, "details": {"style": "swahili", "time": "08:30"}},
            {"code": "airport_pickup", "details": {"flight": "KQ604", "time": "13:20"}},
            {"code": "reef_snorkel"},  # not offered here: silently dropped
            {"code": "retired"},
        ],
        name="Wanjiru Kamau",
        email="wanjiru@example.com",
        lang="sw",
        marketing_opt_in=True,
        identity={"id_type": "national_id", "id_number": "28123456", "consent": True},
        arrival_eta="15:00",
        arrival_mode="flight",
        vehicle_plate="kda 123a",
        special_requests="A cot please",
        occupants=[
            {"full_name": "Otieno Kamau", "id_type": "national_id", "id_number": "30111222", "nationality": "ke"},
            {"full_name": "Baby Kamau", "is_minor": True},
            {"full_name": ""},
        ],
    )
    assert r.status_code == 201, r.data
    b = Booking.objects.get(ref=r.data["booking"]["ref"])
    assert (b.status, b.channel, b.adults, b.children, b.infants, b.lang) == ("held", "web", 2, 1, 1, "sw")
    q = price_quote(
        unit, days(10), days(13), guests=3, addons=[{"addon": breakfast, "quantity": 2}, {"addon": extras.pickup}]
    )
    assert b.total == q["total"] and b.addons_amount == 650 * 2 * 3 + 2_500
    assert b.payment_plan == "full" and b.amount_due_now == b.total and b.hold_active
    assert {a.addon.code: (a.status, a.details) for a in b.addons.select_related("addon")} == {
        "breakfast": ("confirmed", {"style": "swahili", "time": "08:30"}),
        "airport_pickup": ("confirmed", {"flight": "KQ604", "time": "13:20"}),
    }
    assert (b.vehicle_plate, b.arrival_mode, b.arrival_eta, b.special_requests) == (
        "KDA 123A",
        "flight",
        "15:00",
        "A cot please",
    )
    guest.refresh_from_db()
    assert (guest.name, guest.email, guest.lang, guest.marketing_opt_in) == (
        "Wanjiru Kamau",
        "wanjiru@example.com",
        "sw",
        True,
    )
    assert guest.get_id_number() == "28123456"
    lead, otieno, baby = b.occupants.all()
    assert lead.is_lead and lead.full_name == "Wanjiru Kamau" and crypto.decrypt(lead.id_number_enc) == "28123456"
    assert crypto.decrypt(otieno.id_number_enc) == "30111222" and otieno.nationality == "KE"
    assert baby.is_minor and not baby.id_number_enc
    assert "28123456" not in r.content.decode() and "30111222" not in r.content.decode()

    pay = r.data["payment"]
    assert (pay["method"], pay["status"], pay["amount"], pay["purpose"]) == ("mpesa", "pending", b.total, "full")
    p = Payment.objects.get(booking=b)
    assert p.status == "pending" and p.phone == guest.phone and p.amount == b.total
    payments.on_success(p, transaction_id="QFULL1", provider_ref="QFULL1")
    b.refresh_from_db()
    assert (b.status, b.payment_status, b.balance_due, b.amount_paid) == ("confirmed", "paid", 0, b.total)
    assert b.access_codes.filter(revoked_at__isnull=True, sent_at__isnull=True).count() == 1  # made, not sent
    assert Message.objects.filter(phone=guest.phone, kind="booking_confirmed").count() == 1
    assert host_messages("host_notice").filter(body__contains=b.ref).exists()
    trip = guest_api.get(f"/api/bookings/{b.ref}").data
    assert trip["status"] == "confirmed" and sum(line["amount"] for line in trip["price"]["lines"]) == b.total
    assert trip["breakfast"]["style"] == "swahili" and trip["breakfast"]["people"] == 2


def test_book_with_a_deposit_then_pay_the_balance(guest, guest_api, unit):
    r = _book(guest_api, unit, 30, 33, payment_plan="deposit", payment_method="mpesa")
    assert r.status_code == 201
    b = Booking.objects.get(ref=r.data["booking"]["ref"])
    deposit = -(-b.total * 30 // 100)
    assert b.payment_plan == "deposit" and b.amount_due_now == deposit
    assert r.data["payment"]["amount"] == deposit and r.data["payment"]["purpose"] == "deposit"
    payments.on_success(Payment.objects.get(booking=b), transaction_id="QDEP1")
    b.refresh_from_db()
    assert b.status == "confirmed" and b.payment_status == "deposit_paid" and b.balance_due == b.total - deposit
    assert "Balance" in Message.objects.get(phone=guest.phone, kind="booking_confirmed").body
    trip = guest_api.get(f"/api/bookings/{b.ref}").data
    assert trip["can_pay"] and trip["price"]["balance_due"] == b.total - deposit

    r = guest_api.post(f"/api/bookings/{b.ref}/pay", {"method": "mpesa"}, format="json")
    assert r.status_code == 200 and r.data["amount"] == b.total - deposit and r.data["purpose"] == "balance"
    payments.on_success(Payment.objects.get(pk=r.data["payment_id"]), transaction_id="QBAL1")
    b.refresh_from_db()
    assert b.payment_status == "paid" and b.balance_due == 0 and b.amount_paid == b.total
    assert "fully paid" in Message.objects.filter(phone=guest.phone, kind="payment_received").latest("id").body
    r = guest_api.post(f"/api/bookings/{b.ref}/pay", {"method": "mpesa"}, format="json")
    assert r.status_code == 400 and "nothing left to pay" in r.data["error"]


def test_deposit_plan_falls_back_to_full_payment_close_to_arrival(guest_api, unit):
    r = _book(guest_api, unit, 1, 3, payment_plan="deposit")
    b = Booking.objects.get(ref=r.data["booking"]["ref"])
    assert b.payment_plan == "full" and b.amount_due_now == b.total == r.data["payment"]["amount"]


def test_booking_validation_errors(guest, guest_api, api, unit, other_unit):
    assert _book(api, unit, 10, 12).status_code in (401, 403)
    r = guest_api.post("/api/bookings", {"check_in": days(10).isoformat()}, format="json")
    assert r.status_code == 400 and r.data["error"].startswith("Listing")
    assert _book(guest_api, unit, 10, 12, adults=0).status_code == 400
    assert _book(guest_api, unit, 10, 12, payment_method="paypal").status_code == 400
    assert _book(guest_api, unit, 10, 12, email="not-an-email").status_code == 400
    assert _book(guest_api, unit, 10, 12, payment_plan="later").status_code == 400

    def refused(*args, **kw):
        r = _book(guest_api, unit, *args, **kw)
        assert r.status_code == 409, r.data
        return r.data["error"]

    assert "after check-in" in refused(12, 10)
    assert "already passed" in refused(-2, 1)
    assert "up to 4 guests" in refused(10, 12, adults=3, children=2)
    unit.min_nights = 3
    unit.save()
    assert "minimum stay of 3 nights" in refused(10, 12)
    CalendarBlock.objects.create(unit=other_unit, start_date=days(10), end_date=days(11), reason="owner")
    r = _book(guest_api, other_unit, 10, 12)
    assert r.status_code == 409 and "taken" in r.data["error"]
    other_unit.status = "paused"
    other_unit.save()
    assert _book(guest_api, other_unit, 20, 22).status_code == 404
    assert _book(guest_api, unit, 10, 13, identity={"id_number": "28123456"}).status_code == 400  # no consent
    guest.is_blocked = True
    guest.save()
    assert "unable to accept" in refused(20, 23)
    assert not Booking.objects.exists() and not Payment.objects.exists()


def test_card_booking_returns_a_hosted_checkout_link(guest_api, unit):
    r = _book(guest_api, unit, 10, 12, payment_method="card")
    assert r.status_code == 201
    p = Payment.objects.get(booking__ref=r.data["booking"]["ref"])
    assert p.method == "card" and p.checkout_token and r.data["payment"]["checkout_url"].endswith(p.checkout_token)


def test_foreign_guest_cannot_use_mpesa_and_switches_to_card(foreign_guest, unit):
    client = as_user(foreign_guest)
    r = _book(client, unit, 10, 12, payment_method="mpesa")
    assert r.status_code == 201 and "Kenyan" in r.data["payment"]["error"]
    ref = r.data["booking"]["ref"]
    r = client.post(f"/api/bookings/{ref}/pay", {}, format="json")  # card is the default abroad
    assert r.status_code == 200 and r.data["method"] == "card" and "/pay/card/" in r.data["checkout_url"]


def test_my_trips_lists_my_bookings_only(guest, guest_api, unit, other_unit, foreign_guest):
    soon = hold(unit, guest, ci=5)
    later = confirmed(other_unit, guest, ci=20)
    lapsed = hold(unit, guest, ci=30)
    bookings._expire(Booking.objects.filter(pk=lapsed.pk))
    hold(other_unit, foreign_guest, ci=40)
    trips = guest_api.get("/api/bookings").data
    assert [t["ref"] for t in trips] == [later.ref, soon.ref]
    assert trips[0]["status"] == "confirmed" and trips[1]["hold_expires_at"] is not None


def test_check_in_details_unlock_48_hours_out_and_the_code_after_release(guest, guest_api, unit, other_unit, host_api):
    far = confirmed(other_unit, guest, ci=20)
    c = guest_api.get(f"/api/bookings/{far.ref}").data["checkin"]
    assert "address" in c and not c["details_visible"] and "wifi_password" not in c and "directions" not in c
    assert "code" in host_api.get(f"/api/host/reservations/{far.ref}").data["checkin"]  # Amina always sees it

    b = confirmed(unit, guest, ci=1)
    c = guest_api.get(f"/api/bookings/{b.ref}").data["checkin"]
    assert c["details_visible"] and c["wifi_password"] == "coconut-7" and c["directions"] == "Past the baobab"
    assert "code" not in c
    assert bookings.release_code(b, force=True) == "too_early"  # not even Amina's override before arrival day
    assert "code" not in guest_api.get(f"/api/bookings/{b.ref}").data["checkin"]

    arriving = confirmed(other_unit, guest, ci=0)
    assert bookings.release_code(arriving, force=True) == "released"
    c = guest_api.get(f"/api/bookings/{arriving.ref}").data["checkin"]
    assert c["code"] == arriving.access_codes.get(revoked_at__isnull=True).code

    bookings.cancel(far, by="guest")
    c = guest_api.get(f"/api/bookings/{far.ref}").data["checkin"]
    assert "address" not in c and "wifi_password" not in c and "code" not in c


def test_guest_updates_arrival_details(guest, guest_api, unit):
    b = confirmed(unit, guest)
    r = guest_api.patch(
        f"/api/bookings/{b.ref.lower()}",
        {"arrival_eta": "15:30", "arrival_mode": "sgr", "vehicle_plate": " kdb 456c ", "special_requests": "Pillows"},
        format="json",
    )
    assert r.status_code == 200
    assert r.data["arrival"] == {
        "eta": "15:30",
        "mode": "sgr",
        "vehicle_plate": "KDB 456C",
        "special_requests": "Pillows",
    }
    assert b.events.filter(kind="arrival").exists()
    r = guest_api.patch(f"/api/bookings/{b.ref}", {"arrival_eta": "x" * 100}, format="json")
    assert r.status_code == 200 and len(r.data["arrival"]["eta"]) == 40


def test_pay_again_reuses_the_prompt_and_can_switch_to_card(guest, guest_api, unit):
    r = _book(guest_api, unit, 10, 12, payment_method="mpesa")
    ref, first = r.data["booking"]["ref"], r.data["payment"]["payment_id"]
    b = Booking.objects.get(ref=ref)
    again = guest_api.post(f"/api/bookings/{ref}/pay", {"method": "mpesa"}, format="json").data
    assert again["payment_id"] == first and "already waiting" in again["message"]  # no second STK push
    payments.on_failure(Payment.objects.get(pk=first), "cancelled on the phone")
    retry = guest_api.post(f"/api/bookings/{ref}/pay", {"method": "mpesa"}, format="json").data
    assert retry["payment_id"] != first and retry["amount"] == b.total
    card = guest_api.post(f"/api/bookings/{ref}/pay", {"method": "card"}, format="json").data
    assert card["method"] == "card" and card["amount"] == b.total and card["checkout_url"]
    token = card["checkout_url"].rsplit("/", 1)[-1]
    assert APIClient().post(f"/api/pay/card/{token}", {"action": "pay"}, format="json").data["status"] == "success"
    b.refresh_from_db()
    assert b.status == "confirmed" and b.amount_paid == b.total
    assert guest_api.post(f"/api/bookings/{ref}/pay", {"method": "bitcoin"}, format="json").status_code == 400


def test_guest_cannot_pick_their_own_amount(guest, guest_api, unit, other_unit):
    b = hold(unit, guest)
    r = guest_api.post(f"/api/bookings/{b.ref}/pay", {"method": "mpesa", "amount": 1}, format="json")
    assert r.status_code == 400
    assert not Payment.objects.filter(booking=b, amount=1).exists()
    r = guest_api.post(f"/api/bookings/{b.ref}/pay", {"method": "mpesa", "amount": b.total * 2}, format="json")
    assert r.status_code == 400
    assert guest_api.post(f"/api/bookings/{b.ref}/pay", {"amount": "lots"}, format="json").status_code == 400
    r = guest_api.post(f"/api/bookings/{b.ref}/pay", {"method": "mpesa", "amount": str(b.total)}, format="json")
    assert r.status_code == 200 and r.data["amount"] == b.total
    paid = confirmed(other_unit, guest)
    r = guest_api.post(f"/api/bookings/{paid.ref}/pay", {"method": "mpesa", "amount": 500}, format="json")
    assert r.status_code == 400 and "nothing left to pay" in r.data["error"]
    assert not Payment.objects.filter(booking=paid, status="pending").exists()


def test_cannot_pay_for_a_lapsed_hold(guest, guest_api, unit):
    b = hold(unit, guest)
    Booking.objects.filter(pk=b.pk).update(hold_expires_at=timezone.now() - timedelta(seconds=1))
    r = guest_api.post(f"/api/bookings/{b.ref}/pay", {"method": "mpesa"}, format="json")
    assert r.status_code == 400 and "expired" in r.data["error"]


@pytest.mark.parametrize(
    ("policy", "lead_days", "percent"),
    [
        ("flexible", 3, 100),
        ("flexible", 0, 0),
        ("moderate", 7, 100),
        ("moderate", 2, 50),
        ("moderate", -1, 0),
        ("firm", 31, 100),
        ("firm", 10, 50),
        ("firm", 3, 0),
        ("strict", 10, 50),
        ("strict", 3, 0),
    ],
)
def test_guest_cancellation_refund_follows_the_policy(policy, lead_days, percent, guest, guest_api, unit, host):
    unit.cancellation_policy = policy
    unit.save()
    b = confirmed(unit, guest, ci=max(lead_days, 0), nights=3)
    if lead_days < 0:  # a no-show cancelling after the check-in time has passed
        Booking.objects.filter(pk=b.pk).update(check_in=days(lead_days), check_out=days(lead_days + 3))
    expected = round(b.total * percent / 100)

    quote = guest_api.get(f"/api/bookings/{b.ref}/cancel").data
    assert (quote["percent"], quote["refund"], quote["paid"], quote["policy"]) == (percent, expected, b.total, policy)
    assert guest_api.get(f"/api/bookings/{b.ref}").data["cancellation"]["refund"] == expected
    b.refresh_from_db()
    assert b.status == "confirmed"  # looking at the quote changes nothing

    r = guest_api.post(f"/api/bookings/{b.ref}/cancel", {"reason": "Change of plans"}, format="json")
    assert r.status_code == 200 and r.data["refund"] == expected
    b.refresh_from_db()
    assert (b.status, b.cancelled_by, b.cancel_reason, b.amount_refunded) == (
        "cancelled",
        "guest",
        "Change of plans",
        expected,
    )
    assert b.payment_status == {100: "refunded", 50: "partially_refunded", 0: "paid"}[percent]
    assert [(rf.amount, rf.status) for rf in b.refunds.all()] == ([(expected, "success")] if expected else [])
    assert not b.access_codes.filter(revoked_at__isnull=True).exists()
    msg = Message.objects.get(phone=guest.phone, kind="cancelled_by_guest")
    assert (kes(expected) in msg.body) == bool(expected)
    assert host_messages("host_notice").filter(body__contains=f"{b.ref}").filter(body__contains="cancelled").exists()
    assert guest_api.post(f"/api/bookings/{b.ref}/cancel", {}, format="json").status_code == 400


def test_cancelling_a_deposit_refunds_a_share_of_what_was_paid(guest, guest_api, other_unit):
    b = confirmed(other_unit, guest, ci=2, nights=3, payment_plan="deposit")  # moderate, inside 5 days: 50%
    assert b.payment_plan == "deposit" and b.amount_paid == b.amount_due_now < b.total
    quote = guest_api.get(f"/api/bookings/{b.ref}/cancel").data
    assert quote["paid"] == b.amount_paid and quote["refund"] == round(b.amount_paid / 2)
    assert guest_api.post(f"/api/bookings/{b.ref}/cancel", {}, format="json").data["refund"] == quote["refund"]


def test_cancelling_an_unpaid_hold(guest, guest_api, unit, foreign_guest):
    b = hold(unit, guest)
    assert guest_api.get(f"/api/bookings/{b.ref}/cancel").data["refund"] == 0
    r = guest_api.post(f"/api/bookings/{b.ref}/cancel", {}, format="json")
    assert r.status_code == 200 and r.data["refund"] == 0
    b.refresh_from_db()
    assert b.status == "cancelled" and not b.refunds.exists()
    assert hold(unit, foreign_guest).status == "held"  # the dates are free again


def test_extras_of_every_kind(guest, guest_api, unit, breakfast, extras, host):
    b = confirmed(unit, guest, ci=10, nights=3, adults=2)
    paid = b.amount_paid

    def add(**body):
        return guest_api.post(f"/api/bookings/{b.ref}/extras", body, format="json")

    assert add(code="airport_pickup", details={"flight": "KQ604", "time": "13:20"}).status_code == 200
    assert add(code="daily_clean").status_code == 200
    assert add(code="dhow_cruise").status_code == 200
    assert add(code="mid_stay_clean", quantity=2).status_code == 200
    assert add(code="breakfast", details={"style": "english"}).status_code == 200
    r = add(code="early_checkin", details={"time": "11:00"})
    assert r.status_code == 200
    assert add(code="early_checkin").status_code == 400  # flexibility extras once per stay
    assert add(code="breakfast").status_code == 400
    assert "isn't offered" in add(code="reef_snorkel").data["error"]
    assert add(code="retired").status_code == 400 and add(code="nope").status_code == 400

    got = {a.addon.code: (a.quantity, a.total, a.status) for a in b.addons.select_related("addon")}
    assert got == {
        "airport_pickup": (1, 2_500, "confirmed"),
        "daily_clean": (1, 800 * 3, "confirmed"),
        "dhow_cruise": (2, 4_500 * 2, "confirmed"),
        "mid_stay_clean": (2, 1_500 * 2, "confirmed"),
        "breakfast": (2, 650 * 2 * 3, "confirmed"),
        "early_checkin": (1, 1_500, "requested"),
    }
    b.refresh_from_db()
    confirmed_extras = 2_500 + 2_400 + 9_000 + 3_000 + 3_900
    q = price_quote(unit, days(10), days(13), guests=2)
    taxable = q["total"] - q["levy"] + confirmed_extras
    assert b.addons_amount == confirmed_extras and b.total == taxable + round(
        taxable * 0.02
    )  # the request isn't billed
    assert b.amount_paid == paid and b.balance_due == b.total - paid
    ba = b.addons.get(addon__code="early_checkin")
    assert host_messages("addon_request").filter(body__contains=f"REQUEST #{ba.pk}").exists()
    price = r.data["price"]
    assert price["balance_due"] == b.balance_due and sum(line["amount"] for line in price["lines"]) == b.total
    assert price["pending"] == [{"label": "Early check-in (from 11am)", "amount": 1_500}]


# ---------- extras that wait for Amina's approval, and bills that go down ----------


def _request(client, b, code, **details):
    r = client.post(f"/api/bookings/{b.ref}/extras", {"code": code, "details": details}, format="json")
    assert r.status_code == 200, r.data
    return b.addons.get(addon__code=code, status="requested")


def _decide(host_api, ba, approve):
    r = host_api.post(f"/api/host/requests/{ba.pk}/decide", {"approve": approve}, format="json")
    assert r.status_code == 200, r.data
    ba.refresh_from_db()
    ba.booking.refresh_from_db()
    return r


def test_a_requested_extra_does_not_touch_the_bill_until_approved(guest, guest_api, unit, other_unit, extras):
    deposit = confirmed(other_unit, guest, ci=30, nights=3, payment_plan="deposit")
    paid_up = confirmed(unit, guest, ci=10, nights=2)
    assert (deposit.payment_status, paid_up.payment_status) == ("deposit_paid", "paid")
    for b in (deposit, paid_up):
        before = (b.total, b.levy_amount, b.addons_amount, b.balance_due, b.payment_status)
        r = guest_api.post(
            f"/api/bookings/{b.ref}/extras", {"code": "late_checkout", "details": {"time": "14:00"}}, format="json"
        )
        assert r.status_code == 200
        b.refresh_from_db()
        assert (b.total, b.levy_amount, b.addons_amount, b.balance_due, b.payment_status) == before
        price = r.data["price"]
        assert price["pending"] == [{"label": "Late checkout (until 2pm)", "amount": 1_500}]
        assert sum(line["amount"] for line in price["lines"]) == b.total == price["total"]
        assert price["balance_due"] == before[3]
    assert paid_up.balance_due == 0 and not Payment.objects.filter(purpose="addon").exists()


def test_approving_an_extra_asks_for_exactly_what_it_adds(guest, guest_api, host_api, unit, extras):
    b = confirmed(unit, guest, ci=10, nights=2)
    ba = _request(guest_api, b, "late_checkout", time="14:00")
    before = b.total
    r = _decide(host_api, ba, True)
    b.refresh_from_db()
    assert ba.status == "confirmed" and b.total - before == 1_530  # KES 1,500 plus the 2% tourism levy
    p = Payment.objects.get(booking=b, purpose="addon")
    assert (p.amount, p.method, p.status) == (1_530, "mpesa", "pending")
    assert "KES 1,530 has been added" in Message.objects.get(phone=guest.phone, kind="request_approved").body
    assert r.data["price"]["pending"] == [] and sum(line["amount"] for line in r.data["price"]["lines"]) == b.total
    code = b.access_codes.get(revoked_at__isnull=True)
    assert timezone.localtime(code.valid_until).strftime("%H:%M") == "14:30"  # the door code follows the late checkout
    payments.on_success(p, transaction_id="QLATE1")
    b.refresh_from_db()
    assert (b.balance_due, b.payment_status, b.amount_paid) == (0, "paid", b.total)  # no 30-shilling leftover


def test_approving_an_extra_on_a_deposit_booking_asks_only_for_the_extra(guest, guest_api, host_api, unit, extras):
    b = confirmed(unit, guest, ci=30, nights=3, payment_plan="deposit")
    balance = b.balance_due
    ba = _request(guest_api, b, "early_checkin", time="11:00")
    assert b.balance_due == balance
    _decide(host_api, ba, True)
    b.refresh_from_db()
    p = Payment.objects.get(booking=b, purpose="addon")
    assert p.amount == 1_530 and b.balance_due == balance + 1_530  # the rest of the balance is due later, as planned
    payments.on_success(p, transaction_id="QEARLY1")
    b.refresh_from_db()
    assert b.balance_due == balance and b.payment_status == "deposit_paid"


def test_approving_an_extra_the_guest_already_paid_for_starts_no_new_payment(guest, guest_api, host_api, unit, extras):
    """Live regression: the balance the guest paid already included the requested late checkout (the old recalc
    billed requests), and approving it then started - and the simulator settled - a second KES 1,500 payment."""
    b = confirmed(unit, guest, ci=10, nights=2)
    ba = _request(guest_api, b, "late_checkout", time="14:00")
    taxable = b.accommodation_amount - b.discount_amount + b.cleaning_fee + ba.total
    billed = taxable + round(taxable * 0.02)
    Booking.objects.filter(pk=b.pk).update(addons_amount=ba.total, levy_amount=billed - taxable, total=billed)
    r = guest_api.post(f"/api/bookings/{b.ref}/pay", {"method": "mpesa"}, format="json")
    assert r.data["amount"] == 1_530
    payments.on_success(Payment.objects.get(pk=r.data["payment_id"]), transaction_id="QBAL-LATE")
    b.refresh_from_db()
    assert b.amount_paid == billed and b.balance_due == 0
    payment_ids = set(b.payments.values_list("id", flat=True))

    _decide(host_api, ba, True)
    b.refresh_from_db()
    assert ba.status == "confirmed"
    assert set(b.payments.values_list("id", flat=True)) == payment_ids  # no new M-Pesa push
    assert (b.total, b.addons_amount) == (billed, 1_500)  # the late checkout is counted once
    assert (b.amount_paid, b.balance_due, b.payment_status) == (billed, 0, "paid")
    assert not b.refunds.exists()
    assert "added to your bill" not in Message.objects.get(phone=guest.phone, kind="request_approved").body


def test_declining_a_request_leaves_the_bill_alone(guest, guest_api, host_api, unit, extras):
    b = confirmed(unit, guest)
    ba = _request(guest_api, b, "early_checkin", time="11:00")
    before = (b.total, b.amount_paid, b.payment_status)
    assert [x["id"] for x in host_api.get("/api/host/requests").data] == [ba.pk]
    r = _decide(host_api, ba, False)
    b.refresh_from_db()
    assert ba.status == "declined" and (b.total, b.amount_paid, b.payment_status) == before
    assert not b.refunds.exists() and not b.payments.filter(purpose="addon").exists()
    assert r.data["price"]["pending"] == [] and host_api.get("/api/host/requests").data == []
    assert Message.objects.filter(phone=guest.phone, kind="request_declined").exists()


def test_on_request_extra_chosen_at_checkout_is_quoted_as_pending(guest, guest_api, host_api, api, unit, extras):
    body = {
        "check_in": days(10).isoformat(),
        "check_out": days(12).isoformat(),
        "addons": [{"code": "late_checkout"}, {"code": "airport_pickup"}],
    }
    q = api.post(f"/api/listings/{unit.slug}/quote", body, format="json").data
    assert [(x["code"], x["amount"]) for x in q["pending"]] == [("late_checkout", 1_500)]
    assert q["addons"] == 2_500 and sum(line["amount"] for line in q["lines"]) == q["total"] == q["due_now"]
    r = _book(
        guest_api,
        unit,
        10,
        12,
        addons=[{"code": "late_checkout", "details": {"time": "14:00"}}, {"code": "airport_pickup"}],
        payment_method="mpesa",
    )
    b = Booking.objects.get(ref=r.data["booking"]["ref"])
    assert b.total == q["total"] == r.data["payment"]["amount"]  # charged what the quote said, nothing more
    assert r.data["booking"]["price"]["pending"] == [{"label": "Late checkout (until 2pm)", "amount": 1_500}]
    settle(b)
    assert b.payment_status == "paid"
    _decide(host_api, b.addons.get(addon__code="late_checkout"), True)
    assert Payment.objects.get(booking=b, purpose="addon").amount == 1_530


@pytest.mark.parametrize(("policy", "ci", "percent"), [("flexible", 10, 100), ("moderate", 2, 50)])
def test_cancelling_with_a_pending_request(policy, ci, percent, guest, guest_api, host_api, unit, extras):
    unit.cancellation_policy = policy
    unit.save()
    b = confirmed(unit, guest, ci=ci, nights=3)
    ba = _request(guest_api, b, "early_checkin", time="11:00")
    quote = guest_api.get(f"/api/bookings/{b.ref}/cancel").data
    expected = round(b.total * percent / 100)
    assert (quote["paid"], quote["percent"], quote["refund"]) == (b.total, percent, expected)  # only what was paid
    r = guest_api.post(f"/api/bookings/{b.ref}/cancel", {"reason": None}, format="json")
    assert r.status_code == 200 and r.data["refund"] == expected
    b.refresh_from_db()
    ba.refresh_from_db()
    assert b.status == "cancelled" and b.amount_refunded == expected and b.refunds.count() == 1
    assert ba.status == "cancelled" and host_api.get("/api/host/requests").data == []
    _decide(host_api, ba, True)  # a stale tap on the old request changes nothing
    b.refresh_from_db()
    assert ba.status == "cancelled" and not b.payments.filter(purpose="addon").exists() and b.refunds.count() == 1


def test_removing_breakfast_after_paying_queues_a_refund(guest, guest_api, unit, breakfast):
    b = confirmed(
        unit, guest, ci=10, nights=2, adults=2, addons=[{"code": "breakfast", "details": {"style": "english"}}]
    )
    assert b.payment_status == "paid"
    paid = b.amount_paid
    r = guest_api.put(f"/api/bookings/{b.ref}/breakfast", {"style": "none"}, format="json")
    assert r.status_code == 200
    b.refresh_from_db()
    rf = b.refunds.get()
    assert rf.amount == paid - b.total == 650 * 2 * 2 + 52  # 4 breakfasts plus their 2% levy
    assert (rf.status, rf.method) == ("pending", "mpesa_b2c")  # waits for Amina to send it and mark it sent
    assert (b.amount_refunded, b.payment_status, b.balance_due) == (0, "paid", 0)
    sms = Message.objects.get(phone=guest.phone, kind="refund_queued")
    assert f"{kes(rf.amount)} will be refunded to your M-Pesa" in sms.body
    assert b.events.filter(kind="refund", text__contains="queued").exists()
    assert Alert.objects.filter(kind="payment", booking=b).exists()
    assert guest_api.put(f"/api/bookings/{b.ref}/breakfast", {"style": "none"}, format="json").status_code == 200
    bookings.recalc(b)
    assert b.refunds.count() == 1 and Message.objects.filter(kind="refund_queued").count() == 1


def test_lowering_breakfast_tops_up_the_refund_and_it_settles_when_sent(guest, guest_api, host_api, unit, breakfast):
    b = confirmed(
        unit,
        guest,
        ci=10,
        nights=3,
        adults=4,
        addons=[{"code": "breakfast", "quantity": 4, "details": {"style": "swahili"}}],
    )
    paid = b.amount_paid

    def people(n):
        r = guest_api.put(f"/api/bookings/{b.ref}/breakfast", {"style": "swahili", "people": n}, format="json")
        assert r.status_code == 200
        b.refresh_from_db()

    people(2)
    first = b.refunds.get()
    assert first.amount == 650 * 2 * 3 + 78
    people(2)  # the same change again is not a new refund
    assert b.refunds.count() == 1
    people(1)
    second = b.refunds.exclude(pk=first.pk).get()
    assert second.amount == 650 * 1 * 3 + 39  # only the new difference
    assert first.amount + second.amount == paid - b.total
    assert b.amount_paid == paid and b.balance_due == 0 and b.payment_status == "paid"

    for rf in (first, second):
        r = host_api.post(f"/api/host/refunds/{rf.pk}/sent", {"reference": f"B2C{rf.pk}"}, format="json")
        assert r.status_code == 200
    b.refresh_from_db()
    assert b.amount_refunded == paid - b.total and b.payment_status == "paid" and b.balance_due == 0
    assert set(b.refunds.values_list("status", flat=True)) == {"success"}
    bookings.recalc(b)
    assert b.refunds.count() == 2

    people(2)  # breakfast goes back up after the money was handed back: that part is owed again
    assert b.balance_due == 650 * 1 * 3 + 39 and b.refunds.count() == 2


def test_breakfast_cannot_change_after_the_stay(guest, guest_api, unit, breakfast):
    b = checked_in(unit, guest, ci=0, nights=1, addons=[{"code": "breakfast"}])
    bookings.check_out(b)
    r = guest_api.put(f"/api/bookings/{b.ref}/breakfast", {"style": "english"}, format="json")
    assert r.status_code == 400 and "active booking" in r.data["error"]
    assert guest_api.put(f"/api/bookings/{b.ref}/breakfast", {"style": "none"}, format="json").status_code == 200
    b.refresh_from_db()
    assert b.addons.get(addon=breakfast).status == "confirmed" and not b.refunds.exists()


def test_breakfast_choose_change_and_remove(guest, guest_api, unit, other_unit, breakfast):
    b = confirmed(unit, guest, ci=10, nights=3, adults=2)
    base_total = b.total
    put = lambda **body: guest_api.put(f"/api/bookings/{b.ref}/breakfast", body, format="json")  # noqa: E731
    r = put(style="swahili", people=2, dietary="Halal", time="08:30")
    assert r.status_code == 200 and r.data["breakfast"]["style"] == "swahili" and r.data["breakfast"]["people"] == 2
    assert r.data["breakfast"]["summary"] == "2 x Swahili (mahamri, chai, mbaazi, fruit), Halal, at 08:30"
    r = put(style="vegetarian", people=9)  # capped at the home's capacity
    ba = BookingAddon.objects.get(booking=b, addon=breakfast, status="confirmed")
    assert ba.quantity == 4 and ba.total == 650 * 4 * 3 and ba.details["style"] == "vegetarian"
    assert ba.details["time"] == "08:00"  # the kitchen default when no time is given
    assert put(style="caviar").status_code == 400
    assert put(style="none").status_code == 200
    b.refresh_from_db()
    assert b.total == base_total and b.addons.get(addon=breakfast).status == "cancelled"
    assert BookingAddon.objects.filter(booking=b).count() == 1

    no_kitchen = confirmed(other_unit, guest, ci=20)
    other_unit.breakfast_available = False
    other_unit.save()
    r = guest_api.put(f"/api/bookings/{no_kitchen.ref}/breakfast", {"style": "english"}, format="json")
    assert r.status_code == 400 and "isn't available" in r.data["error"]
    r = guest_api.post(f"/api/bookings/{no_kitchen.ref}/extras", {"code": "breakfast"}, format="json")
    assert r.status_code == 400  # not through the generic extras door either


def test_guest_register_occupants(guest, guest_api, unit):
    b = confirmed(unit, guest, adults=3)
    r = guest_api.post(
        f"/api/bookings/{b.ref}/occupants",
        {
            "occupants": [
                {"full_name": "Otieno Kamau", "id_type": "national_id", "id_number": "30111222", "nationality": "ke"},
                {"full_name": "Amani Kamau", "is_minor": True},
                {"id_number": "99999999"},
            ]
        },
        format="json",
    )
    assert r.status_code == 200
    occ = [(o["full_name"], o["id_last4"], o["nationality"], o["is_minor"], o["is_lead"]) for o in r.data["occupants"]]
    assert occ == [
        ("Wanjiru Test", "", "", False, True),
        ("Otieno Kamau", "••••1222", "KE", False, False),
        ("Amani Kamau", "", "", True, False),
    ]
    assert "30111222" not in r.content.decode()
    assert crypto.decrypt(BookingGuest.objects.get(full_name="Otieno Kamau").id_number_enc) == "30111222"
    assert b.events.filter(kind="register").exists()


def test_guest_checks_out(guest, guest_api, unit):
    upcoming = confirmed(unit, guest, ci=10)
    assert guest_api.post(f"/api/bookings/{upcoming.ref}/checkout").status_code == 400
    b = checked_in(unit, guest, ci=0, nights=2)
    code = b.access_codes.get(revoked_at__isnull=True)
    r = guest_api.post(f"/api/bookings/{b.ref}/checkout")
    assert r.status_code == 200 and r.data["status"] == "completed" and r.data["can_review"] is True
    code.refresh_from_db()
    unit.refresh_from_db()
    assert code.revoked_at and code.revoke_reason == "checked_out" and unit.housekeeping == "dirty"
    assert Task.objects.filter(type="turnover", booking=b, unit=unit).exists()
    assert Message.objects.filter(phone=guest.phone, kind="checkout_thanks").exists()
    assert "code" not in r.data["checkin"]
    assert guest_api.post(f"/api/bookings/{b.ref}/checkout").status_code == 400


def test_guest_reports_an_issue(guest, guest_api, unit, host):
    b = checked_in(unit, guest)
    assert guest_api.post(f"/api/bookings/{b.ref}/issues", {"description": "  "}, format="json").status_code == 400
    r = guest_api.post(
        f"/api/bookings/{b.ref}/issues",
        {"category": "water", "description": "No hot water in the shower"},
        format="json",
    )
    assert r.status_code == 200 and r.data["priority"] == "high"
    task = Task.objects.get(pk=r.data["task"])
    assert (task.booking, task.unit, task.category, task.source) == (b, unit, "water", "guest")
    assert Message.objects.filter(phone=guest.phone, kind="issue_logged").exists()
    assert host_messages().filter(body__contains=f"Issue #{task.pk}").exists()


def test_guest_sos_reaches_amina(guest, guest_api, unit, host):
    b = checked_in(unit, guest)
    r = guest_api.post(f"/api/bookings/{b.ref}/sos", {"text": "Someone is trying the door"}, format="json")
    assert r.status_code == 200 and r.data["call_status"] == "dry_run"
    alert = Alert.objects.get(pk=r.data["alert"])
    assert (alert.kind, alert.severity, alert.source, alert.booking) == ("sos", "critical", "web", b)
    assert alert.details == "Someone is trying the door"
    sos = host_messages("sos").get()
    assert "URGENT HELP" in sos.body and b.ref in sos.body and "trying the door" in sos.body


def test_review_only_after_a_completed_stay_and_only_once(guest, guest_api, api, unit):
    b = checked_in(unit, guest, ci=0, nights=1)
    r = guest_api.post(f"/api/bookings/{b.ref}/review", {"rating": 5}, format="json")
    assert r.status_code == 400 and "once your stay is complete" in r.data["error"]
    bookings.check_out(b)
    for bad in (0, 6, None):
        assert guest_api.post(f"/api/bookings/{b.ref}/review", {"rating": bad}, format="json").status_code == 400
    r = guest_api.post(
        f"/api/bookings/{b.ref}/review",
        {
            "rating": 5,
            "comment": "Asante sana!",
            "categories": {"cleanliness": 5, "location": 4, "value": 9, "bogus": 3},
        },
        format="json",
    )
    assert r.status_code == 200 and r.data["review"]["rating"] == 5 and r.data["can_review"] is False
    review = Review.objects.get(booking=b)
    assert (review.unit, review.guest, review.channel, review.comment) == (unit, guest, "web", "Asante sana!")
    assert (review.cleanliness, review.location, review.value, review.accuracy) == (5, 4, 5, None)

    r = guest_api.post(f"/api/bookings/{b.ref}/review", {"rating": 1, "comment": "Changed my mind"}, format="json")
    assert r.status_code == 400
    review.refresh_from_db()
    assert review.rating == 5 and review.comment == "Asante sana!"
    assert api.get(f"/api/listings/{unit.slug}/reviews").data[0]["comment"] == "Asante sana!"


def test_low_review_alerts_amina(guest, guest_api, unit, host):
    b = checked_in(unit, guest, ci=0, nights=1)
    bookings.check_out(b)
    r = guest_api.post(f"/api/bookings/{b.ref}/review", {"rating": 2, "comment": "Dusty"}, format="json")
    assert r.status_code == 200
    assert Alert.objects.filter(kind="low_review", booking=b).exists()
    assert host_messages().filter(body__contains="Low review (2/5)").exists()


def test_guests_cannot_see_or_touch_someone_elses_booking(guest, guest_api, foreign_guest, unit, breakfast, extras):
    theirs = checked_in(unit, foreign_guest, ci=0, nights=2)
    snapshot = lambda: (  # noqa: E731
        Booking.objects.filter(pk=theirs.pk).values_list("status", "total", "amount_paid", "arrival_eta").get(),
        theirs.addons.count(),
        theirs.occupants.count(),
        theirs.payments.count(),
        Task.objects.count(),
        Alert.objects.count(),
        Review.objects.count(),
    )
    before = snapshot()
    base = f"/api/bookings/{theirs.ref}"
    for method, url, body in (
        ("get", base, None),
        ("patch", base, {"arrival_eta": "now"}),
        ("post", f"{base}/pay", {"method": "mpesa"}),
        ("get", f"{base}/cancel", None),
        ("post", f"{base}/cancel", {}),
        ("post", f"{base}/extras", {"code": "airport_pickup"}),
        ("put", f"{base}/breakfast", {"style": "swahili"}),
        ("post", f"{base}/occupants", {"occupants": [{"full_name": "Intruder"}]}),
        ("post", f"{base}/checkout", {}),
        ("post", f"{base}/issues", {"description": "Fake"}),
        ("post", f"{base}/sos", {}),
        ("post", f"{base}/review", {"rating": 1}),
    ):
        r = getattr(guest_api, method)(url, body, format="json")
        assert r.status_code == 404, (method, url, r.status_code)
        assert foreign_guest.phone not in r.content.decode()
    assert snapshot() == before
    assert [t["ref"] for t in guest_api.get("/api/bookings").data] == []
    assert guest_api.get(f"/api/host/reservations/{theirs.ref}").status_code == 403
    assert guest_api.get("/api/bookings/AMS-0000").status_code == 404
