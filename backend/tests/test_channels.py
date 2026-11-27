"""The four Africa's Talking channels: USSD (160-char screens), SMS "Ask Amina", voice IVR and the webhooks themselves."""

import re
import xml.etree.ElementTree as ET

import pytest

from apps.accounts.models import User
from apps.bookings.models import Booking
from apps.comms.views import process_incoming_sms, process_ussd, process_voice
from apps.messaging.models import Message
from apps.safety.models import Alert

from .conftest import days

PHONE = "+254722111222"


def ussd(chain, phone=PHONE):
    out = process_ussd(phone, chain, "s-test")
    assert out.startswith(("CON ", "END ")), out
    return out


def _options(screen):
    return re.findall(r"^(\d+)\.", screen, re.MULTILINE)


@pytest.mark.django_db
def test_every_ussd_screen_fits_160_characters(unit, other_unit, breakfast):
    seen, queue = set(), [""]
    while queue and len(seen) < 120:
        chain = queue.pop(0)
        if chain in seen:
            continue
        seen.add(chain)
        out = ussd(chain)
        assert len(out[4:]) <= 160, f"{chain!r} is {len(out[4:])} chars:\n{out}"
        assert out.isascii(), f"{chain!r} has characters a phone may not show:\n{out}"
        if out.startswith("CON") and chain.count("*") < 3:
            queue += [
                f"{chain}*{n}" if chain else n for n in _options(out) if n != "9"
            ]  # 9 = emergency: tested separately
    assert len(seen) > 20


def test_a_long_ussd_text_is_cut_with_plain_dots_inside_the_limit():
    from apps.comms.ussd import LIMIT, fit

    text = "Karibu Amina Stays - nyumba nzuri karibu na bahari. " * 6
    for limit in (LIMIT - 4, 40):
        cut = fit(text, limit)
        assert cut.endswith("...") and cut.isascii() and len(cut) <= limit and text.startswith(cut[:-3])
    assert fit("Karibu", 10) == "Karibu"


@pytest.mark.django_db
def test_ussd_booking_creates_a_hold(unit, other_unit):
    out = ussd("1*1*2*2*2*1*1")  # book > Diani > tomorrow > 2 nights > 2 guests > first home > confirm
    assert out.startswith("END") and "AMS-" in out
    b = Booking.objects.get(guest__phone=PHONE)
    assert b.channel == "ussd" and b.status == "held" and b.nights == 2


@pytest.mark.django_db
def test_ussd_back_and_home_navigation(unit):
    home = ussd("")
    assert ussd("1*0") == home  # 0 = back to the previous screen
    assert ussd("1*1*00") == home  # 00 = main menu


@pytest.mark.django_db
def test_ussd_emergency_raises_an_alert(unit, host):
    out = ussd("9")
    assert Alert.objects.filter(phone=PHONE).exists()
    assert "999" in out or "112" in out


def sms(text, phone=PHONE):
    inbound = process_incoming_sms(phone, text, provider_id=f"t-{text}")
    return list(
        Message.objects.filter(phone=phone, direction="out", id__gt=inbound.id)
        .order_by("id")
        .values_list("body", flat=True)
    )


@pytest.mark.django_db
def test_sms_prices(unit, other_unit):
    replies = sms("PRICES")
    assert replies and "KES" in replies[0]


@pytest.mark.django_db
def test_sms_booking_conversation_in_kiswahili(unit, other_unit):
    ci = days(12)
    replies = sms(f"Nataka nyumba Diani {ci.day} {ci:%b} siku 3 watu 2")
    assert replies and "1)" in replies[-1], replies
    sms("1")
    b = Booking.objects.get(guest__phone=PHONE)
    assert b.channel == "sms" and b.check_in == ci and b.nights == 3


@pytest.mark.django_db
def test_sms_help_escalates_to_the_host(unit, host):
    sms("HELP someone is at the door")
    assert Alert.objects.filter(phone=PHONE).exists()
    assert Message.objects.filter(phone=host.phone, direction="out").exists()


@pytest.mark.django_db
def test_sms_stop_opts_out_of_marketing(unit):
    sms("STOP")
    assert User.objects.get(phone=PHONE).sms_opt_out_at is not None


def voice(digits="", session="v-test", phone=PHONE):
    xml = process_voice(
        {
            "sessionId": session,
            "isActive": "1",
            "direction": "Inbound",
            "callerNumber": phone,
            "destinationNumber": "+254711082000",
            "dtmfDigits": digits,
        }
    )
    return ET.fromstring(xml)


@pytest.mark.django_db
def test_voice_ivr_language_then_main_menu(unit):
    root = voice()
    assert root.tag == "Response" and root.find("GetDigits") is not None
    menu = voice("1")
    assert "Press 1" in "".join(menu.itertext())


@pytest.mark.django_db
def test_voice_kiswahili_uses_the_swahili_voice(unit):
    voice(session="v-sw")
    root = voice("2", session="v-sw")
    says = root.iter("Say")
    assert any(s.get("voice") == "swahili" for s in says)


@pytest.mark.django_db
def test_at_ussd_webhook_and_secret(client, settings, unit):
    form = {"sessionId": "ATUid_1", "serviceCode": "*384*1#", "phoneNumber": PHONE, "text": ""}
    r = client.post("/at/ussd", form)
    assert r.status_code == 200 and r.content.startswith(b"CON ") and r["Content-Type"].startswith("text/plain")
    settings.AT_WEBHOOK_SECRET = "s3cret-path"
    assert client.post("/at/ussd", form).status_code == 403
    assert client.post("/at/wrong/ussd", form).status_code == 403
    assert client.post("/at/s3cret-path/ussd", form).status_code == 200


@pytest.mark.django_db
def test_at_delivery_report_updates_the_message(client, guest):
    from apps.messaging.models import Thread

    thread = Thread.objects.create(phone=guest.phone, guest=guest)
    m = Message.objects.create(
        thread=thread, phone=guest.phone, direction="out", body="hi", status="sent", provider_id="ATXid_9"
    )
    client.post("/at/sms/delivery", {"id": "ATXid_9", "status": "Success"})
    m.refresh_from_db()
    assert m.status == "delivered"


def _confirmed_stay(unit, guest, check_in, check_out):
    from apps.bookings import services as bookings
    from apps.payments import services as payments
    from apps.payments.models import Payment

    b = bookings.create_hold(unit=unit, guest=guest, check_in=check_in, check_out=check_out, channel="web")
    payments.start_payment(b, method="mpesa")
    payments.on_success(Payment.objects.get(booking=b), transaction_id=f"Q{b.pk}")
    return b


@pytest.mark.django_db
def test_wifi_asked_any_way_gets_this_guests_wifi(unit, guest):
    from apps.messaging.models import FAQ

    FAQ.objects.create(
        category="wifi",
        question="Is there Wi-Fi?",
        keywords="wifi,wi-fi,internet",
        answer_en="Yes - fast fibre in every home.",
    )
    FAQ.objects.create(
        category="wifi",
        question="What is the Wi-Fi password?",
        keywords="wifi,wi-fi,password",
        answer_en="Wi-Fi at {unit}: {wifi}",
        sort_order=5,
    )
    _confirmed_stay(unit, guest, days(0), days(2))
    for text in ("Wi-Fi", "wi fi?", "WiFi password"):
        assert "PalmWifi" in sms(text, phone=guest.phone)[-1], text


@pytest.mark.django_db
def test_web_chat_is_answered_in_the_web_chat_not_by_sms(unit, guest, guest_api):
    from apps.messaging.models import FAQ

    FAQ.objects.create(
        category="amenities",
        question="Is there parking?",
        keywords="parking,car",
        answer_en="Yes - free secure parking.",
    )
    guest_api.post("/api/messages", {"body": "Is there parking?"}, format="json")
    reply = Message.objects.filter(phone=guest.phone, direction="out").latest("id")
    assert reply.body.startswith("Yes - free secure parking") and reply.channel == "web" and reply.status == "sent"
