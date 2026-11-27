"""HTTP API: phone login, permissions, staged disclosure of check-in details, and iCal sync."""

from unittest import mock

import pytest

from apps.bookings import services as bookings
from apps.payments import services as payments
from apps.payments.models import Payment
from apps.properties.models import CalendarBlock, ICalFeed, Unit
from apps.properties.services import export_ics, sync_feed

from .conftest import days


@pytest.mark.django_db
def test_otp_login_flow(api):
    r = api.post("/api/auth/otp/request", {"phone": "0712 345 678"}, format="json")
    assert r.status_code == 200 and r.data["phone"] == "+254712345678"
    assert (
        api.post("/api/auth/otp/verify", {"phone": "+254712345678", "code": "000000"}, format="json").status_code == 400
    )
    r = api.post("/api/auth/otp/verify", {"phone": "+254712345678", "code": r.data["debug_code"]}, format="json")
    assert r.status_code == 200 and r.data["authenticated"]
    assert api.get("/api/auth/me").data["phone"] == "+254712345678"


@pytest.mark.django_db
def test_otp_resend_gap_and_debug_code_only_in_demo(api, settings, django_capture_on_commit_callbacks):
    assert api.post("/api/auth/otp/request", {"phone": "+254700555001"}, format="json").status_code == 200
    assert api.post("/api/auth/otp/request", {"phone": "+254700555001"}, format="json").status_code == 400  # 30 s gap
    settings.DEMO = False
    r = api.post("/api/auth/otp/request", {"phone": "+254700555002"}, format="json")
    assert r.status_code == 200 and "debug_code" not in r.data and not r.data["simulator"]  # no key: the server log
    settings.AT_API_KEY = "sandbox-key"
    sent = {"SMSMessageData": {"Recipients": [{"number": "+254700555003", "statusCode": 101, "messageId": "ATXid_1"}]}}
    with (
        mock.patch("apps.comms.at._post", return_value=sent) as post,
        django_capture_on_commit_callbacks(execute=True),  # the code goes out once the request commits
    ):
        r = api.post("/api/auth/otp/request", {"phone": "+254700555003"}, format="json")
    assert r.data["simulator"] and "debug_code" not in r.data  # the code is only in the Africa's Talking simulator
    assert post.call_args.args[0] == "https://api.sandbox.africastalking.com/version1/messaging"
    assert post.call_args.kwargs["data"]["to"] == "+254700555003"


@pytest.mark.django_db
def test_guests_cannot_see_each_others_trips(unit, guest, foreign_guest, api):
    b = bookings.create_hold(unit=unit, guest=foreign_guest, check_in=days(5), check_out=days(7), channel="web")
    api.force_authenticate(guest)
    assert api.get(f"/api/bookings/{b.ref}").status_code == 404
    api.force_authenticate(foreign_guest)
    assert api.get(f"/api/bookings/{b.ref}").status_code == 200


@pytest.mark.django_db
def test_host_console_is_for_hosts_only(api, guest_api, host_api):
    assert api.get("/api/host/today").status_code in (401, 403)
    assert guest_api.get("/api/host/reservations").status_code == 403
    assert host_api.get("/api/host/today").status_code == 200
    assert host_api.get("/api/host/reservations").status_code == 200


@pytest.mark.django_db
def test_demo_endpoints_disappear_without_demo_mode(api, settings):
    settings.DEMO = False
    assert api.post("/api/demo/reset").status_code == 404
    assert api.post("/api/demo/sms", {"from": "+254700000123", "text": "hi"}, format="json").status_code == 404


@pytest.mark.django_db
def test_check_in_details_are_disclosed_in_stages(unit, guest, guest_api):
    b = bookings.create_hold(unit=unit, guest=guest, check_in=days(20), check_out=days(22), channel="web")
    held = guest_api.get(f"/api/bookings/{b.ref}").data["checkin"]
    assert "address" not in held and "wifi_password" not in held
    payments.start_payment(b, method="mpesa")
    payments.on_success(Payment.objects.get(booking=b), transaction_id="QSTAGE")
    confirmed = guest_api.get(f"/api/bookings/{b.ref}").data["checkin"]
    assert confirmed["address"] == unit.address  # address once booked…
    assert "wifi_password" not in confirmed and "code" not in confirmed  # …Wi-Fi and directions only 48 h before


@pytest.mark.django_db
def test_web_booking_end_to_end(unit, guest, guest_api):
    r = guest_api.post(
        "/api/bookings",
        {
            "listing": unit.slug,
            "check_in": days(9).isoformat(),
            "check_out": days(11).isoformat(),
            "adults": 2,
            "payment_method": "mpesa",
            "name": "Wanjiru Test",
        },
        format="json",
    )
    assert r.status_code == 201, r.data
    ref = r.data["booking"]["ref"]
    assert r.data["payment"]["method"] == "mpesa"
    payments.on_success(Payment.objects.get(booking__ref=ref), transaction_id="QWEB1")
    trip = guest_api.get(f"/api/bookings/{ref}").data
    assert trip["status"] == "confirmed" and trip["price"]["balance_due"] == 0
    clash = guest_api.post(
        "/api/bookings",
        {"listing": unit.slug, "check_in": days(10).isoformat(), "check_out": days(12).isoformat()},
        format="json",
    )
    assert clash.status_code == 409


@pytest.mark.django_db
def test_ical_export_and_import(unit, other_unit, guest):
    b = bookings.create_hold(unit=unit, guest=guest, check_in=days(5), check_out=days(8), channel="web")
    payments.start_payment(b, method="mpesa")
    payments.on_success(Payment.objects.get(booking=b), transaction_id="QICS")
    ics = export_ics(unit)
    assert "BEGIN:VCALENDAR" in ics and f"DTSTART;VALUE=DATE:{days(5):%Y%m%d}" in ics

    feed = ICalFeed.objects.create(unit=other_unit, name="Airbnb", url="https://example.com/airbnb.ics")
    ci, co = days(14), days(17)
    text = (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Airbnb Inc//Hosting Calendar//EN\r\n"
        f"BEGIN:VEVENT\r\nDTSTART;VALUE=DATE:{ci:%Y%m%d}\r\nDTEND;VALUE=DATE:{co:%Y%m%d}\r\nUID:abc-123@airbnb.com\r\n"
        "SUMMARY:Reserved\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    )
    sync_feed(feed, text=text)
    assert CalendarBlock.objects.filter(unit=other_unit, start_date=ci, end_date=co).exists()
    with pytest.raises(bookings.BookingError):
        bookings.create_hold(unit=other_unit, guest=guest, check_in=days(15), check_out=days(16), channel="web")


@pytest.mark.django_db
def test_host_can_open_and_complete_a_task(host_api, unit):
    from apps.operations.models import Task

    task = Task.objects.create(type="maintenance", title="Fix the shower head", unit=unit)
    assert host_api.get(f"/api/host/tasks/{task.pk}").status_code == 200
    assert host_api.post(f"/api/host/tasks/{task.pk}/complete", {}, format="json").status_code == 200
    task.refresh_from_db()
    assert task.status == "done"


@pytest.mark.django_db
def test_host_card_payment_request_texts_the_link(host_api, unit, foreign_guest):
    from apps.messaging.models import Message

    b = bookings.create_hold(
        unit=unit, guest=foreign_guest, check_in=days(20), check_out=days(22), channel="web", payment_plan="deposit"
    )
    payments.start_payment(b, method="card")
    payments.on_success(Payment.objects.get(booking=b), transaction_id="CARD1")
    r = host_api.post(f"/api/host/reservations/{b.ref}/request-payment", {"method": "card"}, format="json")
    assert r.status_code == 200, r.data
    link = Payment.objects.filter(booking=b, status="pending").latest("id").checkout_token
    assert Message.objects.filter(phone=foreign_guest.phone, kind="pay_link", body__contains=link).exists()


@pytest.mark.django_db
def test_compliance_csv_exports(host_api, unit, guest):
    b = bookings.create_hold(unit=unit, guest=guest, check_in=days(1), check_out=days(3), channel="web")
    payments.start_payment(b, method="mpesa")
    payments.on_success(Payment.objects.get(booking=b), transaction_id="QCSV")
    register = host_api.get(f"/api/host/compliance/register?from={days(0)}&to={days(5)}&export=csv")
    assert register.status_code == 200 and register["Content-Type"].startswith("text/csv")
    assert b.ref in register.content.decode()
    month = f"{days(1):%Y-%m}"
    tra = host_api.get(f"/api/host/compliance/tra-return?month={month}&export=csv")
    assert tra.status_code == 200 and tra["Content-Type"].startswith("text/csv")


@pytest.mark.django_db
def test_search_filters_by_property_type_and_free_cancellation(api, unit, area):
    Unit.objects.create(
        name="Baobab House",
        area=area,
        base_price=12_000,
        max_guests=6,
        property_type="house",
        cancellation_policy="strict",
    )
    houses = api.get("/api/listings?type=house").data["results"]
    assert [c["name"] for c in houses] == ["Baobab House"]
    assert houses[0]["free_cancellation"] is False
    flexible = api.get("/api/listings?free_cancellation=1").data["results"]
    assert [c["name"] for c in flexible] == ["Palm Suite"]
    assert flexible[0]["free_cancellation"] is True
    assert api.get("/api/listings?guest_favourite=1").data["count"] == 0  # no reviews yet, so no favourites


def test_go_live_check_names_what_a_live_site_still_needs(settings):
    from apps.core.checks import go_live_check

    settings.DEMO, settings.AT_API_KEY, settings.AT_WEBHOOK_SECRET = True, "", ""
    settings.MPESA_PROVIDER = settings.CARD_PROVIDER = "simulate"
    ids = {w.id for w in go_live_check()}
    assert {"amina.W001", "amina.W002", "amina.W004", "amina.W005", "amina.W006", "amina.W009", "amina.W017"} <= ids


def test_go_live_check_is_quiet_once_every_key_is_set(settings):
    from django.test import override_settings

    from apps.core.checks import go_live_check

    settings.DEMO = False
    settings.AT_USERNAME, settings.AT_API_KEY, settings.AT_SANDBOX = "aminastays", "atsk_live", False
    settings.AT_SENDER_ID, settings.AMINA_PHONE = "AMINASTAYS", "+254712345678"
    settings.AT_WEBHOOK_SECRET, settings.PUBLIC_URL = "long-random-secret", "https://aminastays.co.ke"
    settings.ALLOWED_HOSTS = ["aminastays.co.ke"]
    settings.MPESA_PROVIDER, settings.DARAJA_ENV, settings.DARAJA_SHORTCODE = "daraja", "production", "522533"
    settings.DARAJA_CONSUMER_KEY = settings.DARAJA_CONSUMER_SECRET = settings.DARAJA_PASSKEY = "set"
    settings.CARD_PROVIDER, settings.PAYSTACK_SECRET_KEY = "paystack", "sk_live_set"
    settings.ID_ENCRYPTION_KEY = "set"
    settings.IGLOOHOME_API_KEY, settings.LOCK_PROVIDER_API_BASE = "set", "https://locks.example"
    assert go_live_check() == []

    def warned(**changes):
        with override_settings(**changes):
            return [w.id for w in go_live_check()]

    assert warned(AT_SENDER_ID="") == ["amina.W013"]  # AT's default sender reaches Airtel only
    assert warned(AT_SENDER_ID="", AT_SMS_NUMBER="22384") == []  # the two-way shortcode sends instead
    assert warned(DARAJA_SHORTCODE="174379") == ["amina.W014"]
    assert warned(ALLOWED_HOSTS=["localhost", ".ngrok-free.app"]) == ["amina.W015"]
    assert warned(PUBLIC_URL="https://abc123.ngrok-free.app", ALLOWED_HOSTS=[".ngrok-free.app"]) == ["amina.W016"]
    assert warned(DARAJA_ENV="sandbox", PUBLIC_URL="https://abc123.ngrok-free.app", ALLOWED_HOSTS=["*"]) == [
        "amina.W008"
    ]  # a sandbox demo through a tunnel is fine
    assert warned(AMINA_PHONE="+254 700 000 001") == ["amina.W017"]
