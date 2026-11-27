"""Every Africa's Talking callback (with and without AT_WEBHOOK_SECRET) and every Demo Lab endpoint, over HTTP."""

from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.bookings import services as bookings
from apps.bookings.models import Booking
from apps.comms.models import SimSwapCheck
from apps.core.models import Activity
from apps.messaging import services as messaging
from apps.messaging.models import Message
from apps.payments.models import Payment
from apps.reviews.models import Review

from .conftest import days
from .flowkit import KE_GUEST, bodies, build_catalogue, make_user, stay, with_id

HOST = "+254700000001"
SECRET = "s3cret-path-0123456789"
HOOKS = [
    "sms/incoming",
    "sms/delivery",
    "sms/optout",
    "ussd",
    "ussd/events",
    "voice",
    "airtime/status",
    "data/status",
    "insights/simswap",
]


@pytest.fixture
def homes(db):
    return build_catalogue()[1]


@pytest.fixture
def wanjiru(db):
    return with_id(make_user(KE_GUEST, name="Wanjiru Kamau"))


# ---------- the shared secret ----------


@pytest.mark.django_db
@pytest.mark.parametrize("route", HOOKS)
def test_every_hook_accepts_the_plain_path_without_a_secret_and_only_the_secret_path_with_one(
    client, settings, homes, route
):
    assert client.post(f"/at/{route}", {}).status_code == 200
    assert client.get(f"/at/{route}").status_code == 405  # AT always POSTs
    settings.AT_WEBHOOK_SECRET = SECRET
    assert client.post(f"/at/{route}", {}).status_code == 403
    assert client.post(f"/at/not-the-secret/{route}", {}).status_code == 403
    assert client.post(f"/at/{route}?key=wrong", {}).status_code == 403
    assert client.post(f"/at/{SECRET}/{route}", {}).status_code == 200
    assert client.post(f"/at/{route}?key={SECRET}", {}).status_code == 200


@pytest.mark.django_db
def test_a_non_ascii_secret_is_refused_not_a_server_error(client, settings, homes):
    settings.AT_WEBHOOK_SECRET = SECRET
    assert client.post("/at/caf%C3%A9/ussd", {}).status_code == 403
    assert client.post("/at/ussd?key=caf%C3%A9", {}).status_code == 403


@pytest.mark.django_db
def test_a_rejected_callback_does_nothing(client, settings, homes):
    settings.AT_WEBHOOK_SECRET = SECRET
    client.post("/at/sms/incoming", {"from": KE_GUEST, "text": "HELP", "id": "ATXid_x"})
    assert not Message.objects.exists() and not User.objects.filter(phone=KE_GUEST).exists()


# ---------- SMS ----------


@pytest.mark.django_db
def test_incoming_sms_is_answered(client, homes):
    form = {"from": "0722333444", "to": "22384", "text": "PRICES", "id": "ATXid_in1", "date": "2026-11-25 10:00:00"}
    r = client.post("/at/sms/incoming", form)
    assert r.status_code == 200 and r.content == b"OK"
    msg = Message.objects.get(direction="in")
    assert (msg.phone, msg.provider_id, msg.body, msg.handled) == (KE_GUEST, "ATXid_in1", "PRICES", "auto")
    assert bodies(KE_GUEST)[0].startswith("Our homes (per night, from):")
    assert Activity.objects.filter(kind="sms", phone=KE_GUEST).exists()


@pytest.mark.django_db
def test_an_incoming_sms_without_a_valid_sender_is_ignored(client, homes):
    for form in ({}, {"from": "", "text": "hi"}, {"from": "AFRICASTKNG", "text": "test"}):
        assert client.post("/at/sms/incoming", form).status_code == 200
    from apps.messaging.models import Thread

    assert not Message.objects.exists() and not Thread.objects.exists()  # no blank thread in Amina's inbox


@pytest.mark.django_db
def test_incoming_sms_as_json_and_a_crashing_handler_still_answers_ok(client, homes):
    r = client.post("/at/sms/incoming", {"from": KE_GUEST, "text": "STATUS"}, content_type="application/json")
    assert r.status_code == 200
    with mock.patch("apps.comms.smsbot.handle_sms", side_effect=RuntimeError("boom")):
        r = client.post("/at/sms/incoming", {"from": KE_GUEST, "text": "hello"})
    assert r.status_code == 200  # never bubble an error to Africa's Talking
    failed = Message.objects.filter(direction="in").latest("id")
    assert failed.handled == "relayed" and failed.kind == "error"  # left in Amina's queue instead


@pytest.mark.django_db
def test_live_send_then_delivery_reports(client, settings, homes, wanjiru):
    settings.AT_API_KEY = "live-key"
    answer = {
        "SMSMessageData": {
            "Message": "Sent to 1/1",
            "Recipients": [
                {
                    "number": KE_GUEST,
                    "status": "Success",
                    "statusCode": 101,
                    "messageId": "ATXid_d1",
                    "cost": "KES 0.8000",
                }
            ],
        }
    }
    with mock.patch("apps.comms.at._post", return_value=answer) as post:
        m = messaging.send(KE_GUEST, "Karibu!")
        messaging.dispatch(m.pk)
    assert post.call_args.kwargs["data"]["to"] == KE_GUEST
    m.refresh_from_db()
    assert (m.status, m.provider_id, m.provider_status, m.cost) == ("sent", "ATXid_d1", "Success", "KES 0.8000")

    client.post("/at/sms/delivery", {"id": "ATXid_d1", "status": "Buffered"})
    m.refresh_from_db()
    assert m.status == "sent" and m.provider_status == "Buffered"  # in flight: nothing final yet
    client.post("/at/sms/delivery", {"id": "ATXid_d1", "status": "Success", "networkCode": "63902"})
    m.refresh_from_db()
    assert m.status == "delivered" and m.delivered_at

    for status, reason in (("Failed", "InsufficientCredit"), ("Rejected", "UserInBlacklist")):
        other = Message.objects.create(
            thread=m.thread, phone=KE_GUEST, direction="out", body="x", status="sent", provider_id=f"ATXid_{status}"
        )
        client.post("/at/sms/delivery", {"id": other.provider_id, "status": status, "failureReason": reason})
        other.refresh_from_db()
        assert (other.status, other.failure_reason, other.provider_status) == ("failed", reason, status)
    assert client.post("/at/sms/delivery", {"id": "ATXid_unknown", "status": "Success"}).status_code == 200


@pytest.mark.django_db
def test_a_rejected_send_is_marked_failed_and_a_network_error_is_retried(settings, homes, wanjiru):
    settings.AT_API_KEY = "live-key"
    rejected = {
        "SMSMessageData": {"Recipients": [{"number": KE_GUEST, "status": "InvalidPhoneNumber", "statusCode": 403}]}
    }
    with mock.patch("apps.comms.at._post", return_value=rejected):
        m = messaging.send(KE_GUEST, "hello")
        messaging.dispatch(m.pk)
    m.refresh_from_db()
    assert m.status == "failed" and "InvalidPhoneNumber" in m.failure_reason  # not retried: AT refused it
    from apps.comms.at import ATError

    with mock.patch("apps.comms.at._post", side_effect=ATError("network error: timeout")):
        m2 = messaging.send(KE_GUEST, "hello again")
        messaging.dispatch(m2.pk)
    m2.refresh_from_db()
    assert m2.status == "queued" and m2.attempts == 1 and "timeout" in m2.failure_reason


@pytest.mark.django_db
def test_opt_out_callback_stops_marketing_only(client, homes, wanjiru):
    wanjiru.marketing_opt_in = True
    wanjiru.save()
    assert client.post("/at/sms/optout", {"senderId": "AMINA", "phoneNumber": "254722333444"}).status_code == 200
    wanjiru.refresh_from_db()
    assert wanjiru.sms_opt_out_at and not wanjiru.marketing_opt_in
    assert messaging.send(KE_GUEST, "Promo!", marketing=True) is None
    assert messaging.send(KE_GUEST, "Your booking is confirmed") is not None
    assert Activity.objects.filter(kind="guest", phone=KE_GUEST, title__contains="opted out").exists()
    assert client.post("/at/sms/optout", {"phoneNumber": "not a number"}).status_code == 200


# ---------- USSD, voice ----------


@pytest.mark.django_db
def test_ussd_callback_and_session_events(client, homes):
    form = {
        "sessionId": "ATUid_1",
        "serviceCode": "*384*1234#",
        "phoneNumber": "+254722333444",
        "networkCode": "63902",
        "text": "1*2",
    }
    r = client.post("/at/ussd", form)
    assert r["Content-Type"].startswith("text/plain") and r.content.decode().startswith("CON Check-in:")
    r = client.post("/at/ussd/events", {"sessionId": "ATUid_1", "status": "Completed", "phoneNumber": KE_GUEST})
    assert r.status_code == 200 and r.content == b"OK"
    with mock.patch("apps.comms.ussd.handle", side_effect=RuntimeError("boom")):
        r = client.post("/at/ussd", form)
    assert r.content.decode() == "END Sorry, something went wrong. Please try again."


@pytest.mark.django_db
def test_voice_callback_answers_xml_and_the_final_notification_is_empty(client, homes):
    form = {
        "sessionId": "ATVId_1",
        "isActive": "1",
        "direction": "Inbound",
        "callerNumber": KE_GUEST,
        "destinationNumber": "+254711082000",
    }
    r = client.post("/at/voice", form)
    assert r["Content-Type"] == "application/xml" and b"<GetDigits" in r.content
    r = client.post("/at/voice", {**form, "isActive": "0", "durationInSeconds": "12", "hangupCause": "NORMAL_CLEARING"})
    assert r.status_code == 200 and r.content == b""
    assert Activity.objects.filter(kind="voice", phone=KE_GUEST).count() == 1


@pytest.mark.django_db
def test_voice_callback_url_carries_the_secret(client, settings, homes):
    settings.AT_WEBHOOK_SECRET, settings.PUBLIC_URL = SECRET, "https://amina.example"
    form = {"sessionId": "ATVId_2", "isActive": "1", "direction": "Inbound", "callerNumber": KE_GUEST}
    r = client.post(f"/at/{SECRET}/voice", form)
    assert f'callbackUrl="https://amina.example/at/{SECRET}/voice"'.encode() in r.content


# ---------- airtime, data, SIM swap ----------


@pytest.mark.django_db
def test_airtime_and_data_status_reach_the_activity_feed(client, homes):
    client.post(
        "/at/airtime/status",
        {"phoneNumber": KE_GUEST, "status": "Success", "value": "KES 50.0000", "requestId": "ATQid_1"},
    )
    client.post("/at/data/status", {"phoneNumber": KE_GUEST, "status": "Success", "transactionId": "ATPid_1"})
    documented = {
        "requestId": "ATQid_2",
        "transactionId": "ATPid_2",
        "status": "Failed",
        "destination": "+254705****48",
    }
    client.post("/at/data/status", documented, content_type="application/json")
    titles = list(Activity.objects.filter(kind="system").values_list("title", flat=True))
    assert f"Airtime Success to {KE_GUEST} (KES 50.0000)" in titles
    assert f"Mobile data Success to {KE_GUEST}" in titles
    assert "Mobile data Failed to +254705****48" in titles  # AT names the (masked) destination


@pytest.mark.django_db
def test_sim_swap_callback_updates_the_check_and_the_booking(client, settings, homes, wanjiru):
    from apps.comms import simswap

    settings.SIM_SWAP_PROVIDER, settings.AT_API_KEY = "africastalking", "live-key"
    b = stay(homes["Old Town Loft"], wanjiru, days(0), days(1))
    queued = {"responses": [{"phoneNumber": KE_GUEST, "requestId": "ATSwpid_1", "status": "Queued"}]}
    with mock.patch("apps.comms.at._post", return_value=queued):
        assert simswap.status_for(b) == "pending"
    swapped_on = (timezone.now() - timedelta(days=2)).isoformat()
    payload = {"requestId": "ATSwpid_1", "phoneNumber": KE_GUEST, "status": "Swapped", "lastSimSwapDate": swapped_on}
    assert client.post("/at/insights/simswap", payload, content_type="application/json").status_code == 200
    check = SimSwapCheck.objects.get(request_id="ATSwpid_1")
    assert check.status == "Swapped" and check.last_swap_date and check.raw["callback"]["status"] == "Swapped"
    b.refresh_from_db()
    assert b.sim_swap_status == "Swapped"
    assert simswap.status_for(b) == "swapped"
    unknown = {"requestId": "nope", "status": "Swapped"}
    assert client.post("/at/insights/simswap", unknown, content_type="application/json").status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("shape", "read", "state"),
    [
        ("%d-%m-%Y", True, "swapped"),  # the shape AT's docs show
        ("%Y-%m-%d", True, "swapped"),
        ("%d/%m/%Y", True, "swapped"),
        ("%Y-%m-%dT08:15:00+03:00", True, "swapped"),
        ("01-01-1900", True, "clear"),  # the docs' sample: swapped long ago is no reason to hold a door code
        ("sometime", False, "clear"),  # unreadable: logged, and no reason either
    ],
)
def test_sim_swap_dates_hold_the_code_only_for_a_recent_swap(
    client, settings, homes, wanjiru, caplog, shape, read, state
):
    from apps.comms import simswap

    settings.SIM_SWAP_PROVIDER, settings.AT_API_KEY = "africastalking", "live-key"
    b = stay(homes["Old Town Loft"], wanjiru, days(0), days(1))
    queued = {"responses": [{"phoneNumber": KE_GUEST, "requestId": "ATSwpid_2", "status": "Queued"}]}
    with mock.patch("apps.comms.at._post", return_value=queued):
        assert simswap.status_for(b) == "pending"
    swapped_on = (timezone.localdate() - timedelta(days=2)).strftime(shape)
    payload = {"requestId": "ATSwpid_2", "status": "Swapped", "lastSimSwapDate": swapped_on}
    client.post("/at/insights/simswap", payload, content_type="application/json")
    assert (SimSwapCheck.objects.get(request_id="ATSwpid_2").last_swap_date is not None) == read
    assert simswap.status_for(b) == state
    assert ("unreadable SIM swap date" in caplog.text) == (not read)


@pytest.mark.django_db
def test_a_sim_swap_answered_at_once_is_read_too(settings, homes, wanjiru):
    from apps.comms import simswap

    settings.SIM_SWAP_PROVIDER, settings.AT_API_KEY = "africastalking", "live-key"
    b = stay(homes["Old Town Loft"], wanjiru, days(0), days(1))
    answer = {"responses": [{"requestId": "ATSwpid_3", "status": "Swapped", "lastSimSwapDate": "01-01-1900"}]}
    with mock.patch("apps.comms.at._post", return_value=answer):
        assert simswap.status_for(b) == "clear"


# ---------- Demo Lab ----------


@pytest.mark.django_db
def test_demo_sms_and_the_phone_view(api, homes):
    r = api.post("/api/demo/sms", {"from": "0722 333 444", "text": "PRICES"}, format="json")
    assert r.status_code == 200
    msgs = r.json()["messages"]
    assert [m["direction"] for m in msgs] == ["in", "out"] and msgs[1]["body"].startswith("Our homes")
    assert api.post("/api/demo/sms", {"from": "12", "text": "hi"}, format="json").status_code == 400
    all_msgs = api.get(f"/api/demo/phone/{KE_GUEST}").json()["messages"]
    assert [m["id"] for m in all_msgs] == [m["id"] for m in msgs]
    api.post("/api/demo/sms", {"from": KE_GUEST, "text": "menu"}, format="json")
    newer = api.get(f"/api/demo/phone/{KE_GUEST}?after={msgs[-1]['id']}").json()["messages"]
    assert newer[0]["body"] == "menu" and len(newer) == 2
    assert api.get("/api/demo/phone/0722333444").json()["messages"][-1]["id"] == newer[-1]["id"]
    trunk = api.post("/api/demo/sms", {"from": "+254 (0)722 333 444", "text": "STATUS"}, format="json").json()
    assert {m["direction"] for m in trunk["messages"]} == {"in", "out"}  # "+254 (0)7…" is the same phone
    assert Message.objects.filter(phone=KE_GUEST).count() == 6 and not Message.objects.exclude(phone=KE_GUEST).exists()


@pytest.mark.django_db
def test_demo_ussd_and_voice(api, homes):
    r = api.post("/api/demo/ussd", {"phone": "0722333444", "text": "", "session": "d1"}, format="json")
    assert r.json()["response"].startswith("CON Karibu Amina Stays")
    assert api.post("/api/demo/ussd", {"phone": "", "text": ""}, format="json").status_code == 400
    r = api.post("/api/demo/voice", {"phone": KE_GUEST, "session": "dv1"}, format="json")
    assert "<GetDigits" in r.json()["xml"]
    r = api.post("/api/demo/voice", {"phone": KE_GUEST, "session": "dv1", "digits": "2"}, format="json")
    assert 'voice="swahili"' in r.json()["xml"]
    r = api.post("/api/demo/voice", {"phone": KE_GUEST, "session": "dv1", "hangup": True}, format="json")
    assert r.json()["xml"] == ""


@pytest.mark.django_db
def test_demo_pay_settles_the_hold(api, homes, wanjiru):
    b = bookings.create_hold(
        unit=homes["Old Town Loft"], guest=wanjiru, check_in=days(3), check_out=days(4), channel="ussd"
    )
    r = api.post(f"/api/demo/pay/{b.ref.lower()}")
    assert r.status_code == 200 and r.json() == {"ref": b.ref, "status": "confirmed", "paid": b.total}
    p = Payment.objects.get(booking=b)
    assert p.status == "success" and p.transaction_id == f"DEMO{p.pk}"
    assert bodies(KE_GUEST)[-1].startswith("Booked! Old Town Loft")
    assert api.post(f"/api/demo/pay/{b.ref}").json() == {"error": "There's nothing left to pay."}
    assert api.post("/api/demo/pay/AMS-0000").status_code == 404


@pytest.mark.django_db
def test_demo_pay_uses_the_pending_prompt(api, homes, wanjiru):
    from apps.payments import services as payments

    b = bookings.create_hold(
        unit=homes["Old Town Loft"], guest=wanjiru, check_in=days(3), check_out=days(4), channel="sms"
    )
    payments.start_payment(b)
    api.post(f"/api/demo/pay/{b.ref}")
    assert Payment.objects.filter(booking=b).count() == 1 and Payment.objects.get(booking=b).status == "success"


@pytest.mark.django_db
def test_demo_tick_runs_due_or_chosen_jobs(api, homes, host):
    r = api.post("/api/demo/tick", {"jobs": ["host_digest"]}, format="json")
    assert list(r.json()) == ["host_digest"] and bodies(HOST, kind="host_digest")
    r = api.post("/api/demo/tick", {}, format="json")
    assert r.status_code == 200 and "expire_holds" in r.json() and "outbox" in r.json()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "step", ["pre_arrival", "directions", "id_request", "welcome_check", "checkout_reminder", "mid_stay"]
)
def test_demo_advance_sends_each_timeline_message(api, homes, wanjiru, step):
    b = stay(homes["Blue Reef Apartment"], wanjiru, days(10), days(14))  # long before the 48-hour reveal
    r = api.post(f"/api/demo/advance/{b.ref}", {"step": step}, format="json")
    assert r.json() == {"ref": b.ref, "status": "confirmed", "result": "ok"}
    [sent] = bodies(KE_GUEST, kind=step)
    assert "{" not in sent
    if step == "mid_stay":
        assert "KES 1,500" in sent
    if step == "directions":  # the time machine sends it as on its real date: with the real route and Wi-Fi
        assert "Wi-Fi: BlueReef / reef-sunrise-2026" in sent and "Mount Kenya Road" in sent


@pytest.mark.django_db
def test_demo_advance_releases_the_code_checks_out_and_asks_for_a_review(api, homes, wanjiru):
    b = stay(homes["Blue Reef Apartment"], wanjiru, days(1), days(3))  # arrives tomorrow: the time machine skips ahead
    assert api.post(f"/api/demo/advance/{b.ref}", {"step": "checkout"}, format="json").json() == {
        "error": "There's no active stay to check out of."
    }
    r = api.post(f"/api/demo/advance/{b.ref}", {"step": "code"}, format="json")
    assert r.json()["result"] == "released" and r.json()["status"] == "checked_in"
    assert bodies(KE_GUEST, kind="checkin_code")
    r = api.post(f"/api/demo/advance/{b.ref}", {"step": "review"}, format="json")
    assert r.json() == {"ref": b.ref, "status": "completed", "result": True}
    assert bodies(KE_GUEST, kind="review_request")
    r = api.post(f"/api/demo/advance/{b.ref}", {"step": "review"}, format="json")
    assert r.json()["result"] is True  # the presenter can ask again
    Review.objects.create(booking=b, unit=b.unit, guest=wanjiru, rating=5)
    assert api.post(f"/api/demo/advance/{b.ref}", {"step": "review"}, format="json").json()["result"] is False
    assert api.post(f"/api/demo/advance/{b.ref}", {"step": "nope"}, format="json").status_code == 400


@pytest.mark.django_db
def test_demo_advance_code_holds_for_a_missing_id_unless_forced(api, homes):
    hans = make_user("+4915112345101", name="Hans Muller", lang="de")
    b = stay(homes["Diani Palm Suite"], hans, days(0), days(2))
    assert api.post(f"/api/demo/advance/{b.ref}", {"step": "code"}, format="json").json()["result"] == "waiting_id"
    r = api.post(f"/api/demo/advance/{b.ref}", {"step": "code", "force": True}, format="json")
    assert r.json()["result"] == "released"
    b.refresh_from_db()
    assert b.status == "checked_in"


@pytest.mark.django_db
def test_demo_ical_feed(client, homes):
    r = client.get("/api/demo/ical/blue-reef-apartment.ics")
    body = r.content.decode()
    assert r["Content-Type"].startswith("text/calendar") and body.startswith("BEGIN:VCALENDAR")
    assert body.count("BEGIN:VEVENT") == 2 and f"DTSTART;VALUE=DATE:{days(14):%Y%m%d}" in body


@pytest.mark.django_db
def test_demo_reset_reseeds_through_the_management_command(api):
    with mock.patch("django.core.management.call_command") as cmd:
        r = api.post("/api/demo/reset")
    assert r.status_code == 200 and r.json()["reset"] is True
    cmd.assert_called_once_with("seed_demo", "--reset")


@pytest.mark.django_db
def test_every_demo_endpoint_is_gone_without_demo_mode(api, client, settings, homes, wanjiru):
    b = stay(homes["Old Town Loft"], wanjiru, days(3), days(4))
    settings.DEMO = False
    with mock.patch("django.core.management.call_command") as cmd:
        assert api.post("/api/demo/reset").status_code == 404
    cmd.assert_not_called()
    for url, body in (
        ("/api/demo/sms", {"from": KE_GUEST, "text": "hi"}),
        ("/api/demo/ussd", {"phone": KE_GUEST, "text": ""}),
        ("/api/demo/voice", {"phone": KE_GUEST}),
        (f"/api/demo/pay/{b.ref}", {}),
        ("/api/demo/tick", {}),
        (f"/api/demo/advance/{b.ref}", {"step": "checkout"}),
    ):
        assert api.post(url, body, format="json").status_code == 404, url
    assert api.get(f"/api/demo/phone/{KE_GUEST}").status_code == 404
    assert client.get("/api/demo/ical/old-town-loft.ics").status_code == 404
    assert "demo_lab" not in api.get("/api/config").json()
    assert not Message.objects.filter(direction="in").exists()
    assert Booking.objects.get(pk=b.pk).status == "confirmed"
