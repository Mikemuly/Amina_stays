"""Call Amina (voice IVR) end to end, one Africa's Talking callback per key press: language, every main-menu
digit, booking by phone, the bridge to Amina, voicemail, the 9-for-help escalation and the outbound SOS call
that connects Amina to the guest."""

from datetime import timedelta
from unittest import mock

import pytest

from apps.accounts.models import User
from apps.bookings.models import AccessCode, Booking, Waitlist
from apps.comms import voice as ivr
from apps.comms.models import VoiceSession
from apps.comms.views import process_voice
from apps.core.utils import today, weekend_start
from apps.messaging.models import Conversation, Message, Thread
from apps.payments.models import Payment
from apps.properties.services import quote as price_quote
from apps.safety.models import Alert
from apps.safety.services import followups
from apps.support.models import Ticket

from .conftest import days
from .flowkit import (
    KE_GUEST,
    bodies,
    build_catalogue,
    frozen,
    kenya,
    last_id,
    make_user,
    pay,
    sms,
    spoken,
    stay,
    voice,
    with_id,
)

HOST = "+254700000001"
NEW = "+254799000333"


@pytest.fixture
def homes(db):
    return build_catalogue()[1]


@pytest.fixture
def wanjiru(db):
    return with_id(make_user(KE_GUEST, name="Wanjiru Kamau"))


def call(*digits, session="v-flow", phone=KE_GUEST):
    """Dial in and press each key in turn; returns the last XML response."""
    root = voice("", session=session, phone=phone)
    for d in digits:
        root = voice(d, session=session, phone=phone)
    return root


def asks(root):
    gd = root.find("GetDigits")
    return gd is not None and gd.get("callbackUrl", "").endswith("/at/voice")


def hang_up(session="v-flow", phone=KE_GUEST, dial="0", **extra):
    out = process_voice(
        {
            "sessionId": session,
            "isActive": "0",
            "direction": "Inbound",
            "callerNumber": phone,
            "durationInSeconds": "42",
            "dialDurationInSeconds": dial,
            "hangupCause": "NORMAL_CLEARING",
            **extra,
        }
    )
    assert out == ""


# ---------- language ----------


@pytest.mark.django_db
def test_the_call_opens_with_the_language_choice_then_the_english_menu(homes):
    root = voice("", phone=NEW)
    assert root.tag == "Response" and asks(root)
    assert root.find("GetDigits").get("numDigits") == "1" and root.find("GetDigits").get("finishOnKey") == "#"
    assert spoken(root).startswith("Welcome to Amina Stays. For English, press 1. Kwa Kiswahili, bonyeza 2.")
    assert root.findall("Say")[-1].text == "We did not receive any input. Goodbye."  # after the GetDigits timeout
    menu = voice("1", phone=NEW)
    assert asks(menu) and spoken(menu).startswith("Press 1 to check availability and book. Press 2 to hear our prices")
    assert "Press 9 at any time for urgent help." in spoken(menu)
    assert all(s.get("voice") is None for s in menu.iter("Say"))
    user = User.objects.get(phone=NEW)
    assert user.first_channel == "voice" and user.lang == "en"
    assert VoiceSession.objects.get(session_id="v-flow").state == {"step": "main", "lang": "en"}


@pytest.mark.django_db
def test_kiswahili_speaks_with_the_swahili_voice_and_is_remembered(homes):
    menu = call("2", phone=NEW)
    says = list(menu.iter("Say"))
    assert says and all(s.get("voice") == "swahili" for s in says)
    assert spoken(menu).startswith("Bonyeza 1 kuangalia nafasi na kuweka nafasi.")
    assert User.objects.get(phone=NEW).lang == "sw"
    prices = voice("2", phone=NEW)
    assert spoken(prices).startswith("Nyumba zetu: Nyali Breeze Studio, Nyali, kuanzia shilingi")
    assert all(s.get("voice") == "swahili" for s in prices.iter("Say"))


@pytest.mark.django_db
def test_a_returning_guest_is_welcomed_back_by_name(homes, wanjiru):
    stay(homes["Old Town Loft"], wanjiru, days(5), days(6))
    assert spoken(call("1")).startswith("Welcome back Wanjiru. Press 1 to check availability")


# ---------- 1: availability and booking ----------


@pytest.mark.django_db
def test_book_by_phone_end_to_end_then_m_pesa_confirms_by_sms(homes):
    assert spoken(call("1", "1", phone=NEW)).startswith(
        "When would you like to stay? Press 1 for tonight. Press 2 for tomorrow."
    )
    assert spoken(voice("2", phone=NEW)).startswith("How many nights? Press a number from 1 to 7.")
    assert spoken(voice("2", phone=NEW)).startswith("How many guests? Press a number from 1 to 8.")
    ci, co = days(1), days(3)
    offer = voice("2", phone=NEW)
    blue = homes["Blue Reef Apartment"]
    total = price_quote(blue, ci, co, guests=2)["total"]
    assert f"Press 2 for Blue Reef Apartment in Nyali, {total} shillings in total." in spoken(offer)
    assert "Press 1 for Nyali Breeze Studio in Nyali" in spoken(offer) and "Press 5" not in spoken(offer)

    done = voice("2", phone=NEW)
    b = Booking.objects.get(guest__phone=NEW)
    assert done.find("GetDigits") is None
    assert spoken(done) == (
        f"We are holding Blue Reef Apartment for you. The total is {total} shillings. An M-Pesa prompt is coming to "
        "this phone now. Your confirmation will arrive by text message. Asante, goodbye."
    )
    assert (b.channel, b.unit, b.check_in, b.check_out, b.adults, b.lang, b.status) == (
        "voice",
        blue,
        ci,
        co,
        2,
        "en",
        "held",
    )
    assert Payment.objects.get(booking=b).status == "pending"
    before = last_id()
    pay(b)
    assert b.status == "confirmed" and bodies(NEW, before)[0].startswith("Booked! Blue Reef Apartment")


@pytest.mark.django_db
def test_book_in_kiswahili_gets_the_confirmation_in_kiswahili(homes):
    call("2", "1", "2", "2", "2", phone=NEW)
    done = voice("1", phone=NEW)
    assert spoken(done).startswith("Tumekuwekea Nyali Breeze Studio. Jumla ni shilingi")
    b = Booking.objects.get(guest__phone=NEW)
    assert b.lang == "sw"
    pay(b)
    assert bodies(NEW)[-1].startswith("Imethibitishwa! Nyali Breeze Studio")


@pytest.mark.django_db
def test_this_weekend_skips_the_nights_question(homes):
    root = call("1", "1", "3", phone=NEW)
    assert spoken(root).startswith("How many guests?")
    st = VoiceSession.objects.get(session_id="v-flow").state
    ci = weekend_start(today())
    assert st["check_in"] == ci.isoformat()
    assert st["check_out"] == (ci + timedelta(days=2 if ci.weekday() == 4 else 1)).isoformat()


@pytest.mark.django_db
def test_a_one_night_stay_only_offers_homes_that_take_one_night(homes):
    offer = call("1", "1", "2", "1", "2", phone=NEW)  # tomorrow, one night, two guests
    text = spoken(offer)
    assert "Nyali Breeze Studio" in text and "Old Town Loft" in text and "Diani" not in text and "Blue Reef" not in text


@pytest.mark.django_db
def test_when_only_longer_stays_are_free_the_nights_are_asked_again(homes, wanjiru):
    for name in ("Nyali Breeze Studio", "Old Town Loft"):  # the two one-night homes are taken tomorrow
        stay(homes[name], wanjiru, days(1), days(2))
    again = call("1", "1", "2", "1", "2", phone=NEW)
    assert spoken(again).startswith("The homes free then need a stay of at least 2 nights. How many nights?")
    offer = voice("2", phone=NEW)  # the two guests are remembered
    assert "Press 1 for Blue Reef Apartment in Nyali" in spoken(offer)
    voice("1", phone=NEW)
    b = Booking.objects.get(guest__phone=NEW)
    assert (b.unit.name, b.nights, b.adults) == ("Blue Reef Apartment", 2, 2)


@pytest.mark.django_db
def test_going_back_after_a_minimum_stay_miss_asks_for_the_guests_again(homes, wanjiru):
    for name in ("Nyali Breeze Studio", "Old Town Loft"):
        stay(homes[name], wanjiru, days(1), days(2))
    assert spoken(call("1", "1", "2", "1", "2", phone=NEW)).startswith("The homes free then need")
    assert spoken(voice("0", phone=NEW)).startswith("Press 1 to check availability")  # back to the main menu
    voice("1", phone=NEW)  # book again: tomorrow, three nights
    voice("2", phone=NEW)
    assert spoken(voice("3", phone=NEW)).startswith("How many guests?")


@pytest.mark.django_db
def test_nothing_free_joins_the_waitlist(homes, wanjiru):
    big = make_user("+254733000999", name="Big Family")
    stay(homes["Bamburi Family House"], big, days(1), days(3), adults=6)
    root = call("1", "1", "2", "2", "6", phone=NEW)  # six guests: only Bamburi sleeps six
    assert spoken(root).startswith("Sorry, nothing is free for those dates. We have added you to our waiting list")
    assert Waitlist.objects.get(guest__phone=NEW).guests == 6


@pytest.mark.django_db
def test_dates_by_text_message_hand_the_booking_over_to_sms(homes):
    root = call("1", "1", "4", phone=NEW)
    assert spoken(root).startswith("We have sent you a text message. Just reply with your dates")
    [ask] = bodies(NEW)
    assert ask.startswith("Hi from Amina Stays! Which dates?")
    assert Conversation.objects.get(phone=NEW).state == "collecting"
    ci = days(9)
    [offer] = sms(f"{ci.day} {ci:%b} for 2 nights", phone=NEW)
    assert offer.startswith(f"Yes! {ci:%a} {ci.day} {ci:%b}")


# ---------- 2: prices and breakfast ----------


@pytest.mark.django_db
def test_prices_and_breakfast_then_book_or_back(homes):
    root = call("1", "2", phone=NEW)
    text = spoken(root)
    assert text.startswith("Our homes: Nyali Breeze Studio in Nyali, from ")
    assert (
        "Breakfast is 650 shillings per person per day" in text and text.count("shillings a night") == 5
    )  # five homes
    assert spoken(voice("1", phone=NEW)).startswith("When would you like to stay?")
    assert spoken(call("1", "2", "0", session="v-2", phone=NEW)).startswith("Press 1 to check availability")


# ---------- 3: my booking and directions ----------


@pytest.mark.django_db
def test_my_booking_without_a_booking(homes):
    root = call("1", "3", phone=NEW)
    assert spoken(root).startswith("We could not find a booking for this number. Press 1 to book, or 0")
    assert spoken(voice("1", phone=NEW)).startswith("When would you like to stay?")


@pytest.mark.django_db
def test_my_booking_reads_the_stay_then_directions_by_voice_and_sms(homes, wanjiru):
    b = stay(homes["Blue Reef Apartment"], wanjiru, days(1), days(3))
    root = call("1", "3")
    text = spoken(root)
    assert text.startswith("Your booking at Blue Reef Apartment runs from ")
    assert (
        f"Reference A M S {' '.join(b.ref[4:])}. Status: Confirmed." in text
        and "Press 1 to hear the directions." in text
    )
    before = last_id()
    directions = voice("1")
    assert spoken(directions).startswith("Blue Reef Apartment. Head down Mount Kenya Road")
    assert "Look out for White tower next to the Nyali public beach access." in spoken(directions)
    assert bodies(KE_GUEST, before, kind="directions")
    assert spoken(call("1", "3", "2", session="v-2")).startswith(
        "Your door code will arrive by text message on the morning of"
    )


@pytest.mark.django_db
def test_directions_wait_for_the_48_hour_reveal_on_the_phone_too(homes, wanjiru):
    stay(homes["Blue Reef Apartment"], wanjiru, days(20), days(22))
    early = call("1", "3", "1")
    assert spoken(early) == (
        "Blue Reef Apartment is in Nyali. The full directions and Wi-Fi details are shared by text message "
        "2 days before you arrive. Goodbye."
    )
    assert not bodies(KE_GUEST, kind="directions")  # no directions and no Wi-Fi password three weeks early
    with frozen(kenya(days(18), "14:00")):  # 48 h before the 2pm check-in
        root = call("1", "3", "1", session="v-2")
    assert spoken(root).startswith("Blue Reef Apartment. Head down Mount Kenya Road")
    [text] = bodies(KE_GUEST, kind="directions")
    assert "Wi-Fi: BlueReef / reef-sunrise-2026" in text


@pytest.mark.django_db
def test_an_in_house_guest_gets_the_door_code_by_sms(homes, wanjiru):
    b = stay(homes["Blue Reef Apartment"], wanjiru, days(0), days(2), checked_in=True)
    code = AccessCode.objects.get(booking=b, revoked_at__isnull=True)
    before = last_id()
    assert spoken(call("1", "3", "2")) == "We have sent your door code by text message. Goodbye."
    assert any(code.code in m for m in bodies(KE_GUEST, before, kind="checkin_code"))


@pytest.mark.django_db
def test_a_held_booking_is_read_out_without_options(homes, wanjiru):
    from apps.bookings import services as bookings

    bookings.create_hold(unit=homes["Old Town Loft"], guest=wanjiru, check_in=days(4), check_out=days(5), channel="web")
    root = call("1", "3")
    assert root.find("GetDigits") is None and "Status: Held" in spoken(root)


# ---------- 4: talk to Amina ----------


@pytest.mark.django_db
def test_talk_to_amina_bridges_the_call_to_her_and_her_backup(homes, site):
    site.backup_phone = "+254700000099"
    site.save()
    assert spoken(call("1", "4", phone=NEW)).startswith(
        "Press 1 to be connected to Amina now. Press 2 to leave her a voice message."
    )
    root = voice("1", phone=NEW)
    dial = root.find("Dial")
    assert spoken(root) == "Connecting you to Amina. Please hold."
    assert dial.get("phoneNumbers") == f"{HOST},+254700000099" and dial.get("sequential") == "true"
    hang_up(phone=NEW, dial="75")  # she answered: nothing else to do
    assert not bodies(HOST) and not bodies(NEW)
    session = VoiceSession.objects.get(session_id="v-flow")
    assert session.ended_at and session.duration_seconds == 42 and session.hangup_cause == "NORMAL_CLEARING"


@pytest.mark.django_db
def test_a_missed_bridge_tells_both_sides(homes):
    call("1", "4", "1", phone=NEW)
    hang_up(phone=NEW, dial="0")
    ticket = Ticket.objects.get(phone=NEW)  # a call-back on the support desk, with a Call button
    assert (ticket.category, ticket.channel) == ("callback", "voice")
    assert bodies(HOST) == [
        f"Missed call from guest {NEW} who wanted to talk ({ticket.ref}). Please call back - reply CALL {ticket.ref} to be connected."
    ]
    assert bodies(NEW) == ["Amina couldn't pick up just now. Text your question to this number and she'll reply here."]


@pytest.mark.django_db
def test_voicemail_is_thanked_and_relayed_to_amina_once(homes, wanjiru):
    b = stay(homes["Old Town Loft"], wanjiru, days(2), days(3))
    record = call("1", "4", "2")
    rec = record.find("Record")
    assert rec is not None and rec.get("finishOnKey") == "#" and rec.get("maxLength") == "90"
    url = "https://voice.africastalking.com/recordings/abc.mp3"
    after = voice("", recordingUrl=url)
    assert spoken(after) == "Thank you. Amina will get back to you. Goodbye." and after.find("GetDigits") is None
    assert bodies(HOST, kind="voicemail") == [f"Voicemail from {KE_GUEST} ({b.ref}): {url}"]
    msg = Message.objects.get(phone=KE_GUEST, direction="in", channel="voice")
    assert msg.body == f"[voicemail] {url}" and msg.handled == "relayed" and msg.booking == b
    assert Thread.objects.get(phone=KE_GUEST).needs_reply
    hang_up(recordingUrl=url)  # AT repeats the URL on hang-up: still one voicemail
    assert len(bodies(HOST, kind="voicemail")) == 1


# ---------- 9: urgent help ----------


@pytest.mark.django_db
def test_nine_raises_an_sos_and_bridges_straight_to_amina(homes, host, wanjiru, site):
    b = stay(homes["Blue Reef Apartment"], wanjiru, days(0), days(2), checked_in=True)
    root = call("1", "1", "9")  # 9 works from any step, even mid-booking
    assert spoken(root).startswith("We are alerting Amina and connecting you to her now.")
    assert root.find("Dial").get("phoneNumbers") == HOST
    alert = Alert.objects.get()
    assert (alert.kind, alert.source, alert.severity, alert.booking, alert.call_status) == (
        "sos",
        "voice",
        "critical",
        b,
        "bridged",
    )
    [urgent] = bodies(HOST, kind="sos")
    assert urgent.startswith("URGENT HELP (voice): Wanjiru Kamau") and "Connecting the caller to you now." in urgent
    assert VoiceSession.objects.get(session_id="v-flow").state["alert_id"] == alert.pk


@pytest.mark.django_db
def test_an_unanswered_sos_bridge_rings_amina_again_on_the_same_alert(homes, host, wanjiru):
    stay(homes["Blue Reef Apartment"], wanjiru, days(0), days(2), checked_in=True)
    call("1", "9")
    alert = Alert.objects.get()
    before = last_id()
    hang_up(dial="0")
    assert Alert.objects.count() == 1  # one emergency, one alert
    alert.refresh_from_db()
    assert alert.calls_made == 1 and alert.call_status == "dry_run"
    assert bodies(KE_GUEST, before) == [
        "Amina didn't answer yet - we're calling her again now. If you are in danger call 999 or 112."
    ]
    assert any(m.startswith("URGENT") and "Calling you now" in m for m in bodies(HOST, before))
    assert sms("OK", phone=HOST) == [f"Alert #{alert.pk} acknowledged."]
    with frozen(alert.last_call_at + timedelta(minutes=5)):
        followups()  # acknowledged: nobody is rung again
    alert.refresh_from_db()
    assert alert.calls_made == 1 and alert.status == "acknowledged"


@pytest.mark.django_db
def test_an_answered_sos_bridge_needs_nothing_more(homes, host, wanjiru):
    call("1", "9")
    before = last_id()
    hang_up(dial="120")
    assert not bodies(KE_GUEST, before) and not bodies(HOST, before)


# ---------- invalid digits and navigation ----------


@pytest.mark.django_db
def test_invalid_digits_repeat_the_question(homes):
    assert spoken(call("1", "7", phone=NEW)).startswith(
        "Sorry, that is not a valid choice. Press 1 to check availability"
    )
    assert spoken(voice("1", phone=NEW)).startswith("When would you like to stay?")
    assert spoken(voice("8", phone=NEW)).startswith("Sorry, that is not a valid choice. When would you like to stay?")
    voice("2", phone=NEW)
    assert spoken(voice("9", session="v-x", phone=NEW)).startswith("Welcome to Amina Stays")  # a new call starts over
    assert spoken(voice("8", phone=NEW)).startswith("Sorry, that is not a valid choice. How many nights?")
    voice("2", phone=NEW)
    assert spoken(voice("9", phone=NEW)).startswith("We are alerting Amina")  # 9 is always help
    call("1", "1", "2", "2", "2", session="v-y", phone=NEW)
    assert spoken(voice("7", session="v-y", phone=NEW)).startswith("Sorry, that is not a valid choice. Press 1 for")


@pytest.mark.django_db
def test_zero_returns_to_the_main_menu_and_any_other_key_picks_english(homes):
    assert spoken(call("1", "1", "2", "0", phone=NEW)).startswith("Press 1 to check availability")
    assert spoken(call("5", session="v-2", phone=NEW)).startswith("Press 1 to check availability")


# ---------- the outbound SOS safety call to Amina ----------


@pytest.mark.django_db
def test_amina_answers_the_sos_call_hears_who_and_where_and_is_bridged(homes, host, wanjiru):
    b = stay(homes["Blue Reef Apartment"], wanjiru, days(0), days(2), checked_in=True)
    sms("HELP")
    alert = Alert.objects.get()
    payload = {
        "sessionId": "AT-out-1",
        "isActive": "1",
        "direction": "Outbound",
        "callerNumber": "+254711082000",
        "destinationNumber": HOST,
        "clientRequestId": f"alert-{alert.pk}",
        "dtmfDigits": "",
    }
    import xml.etree.ElementTree as ET

    root = ET.fromstring(process_voice(payload))
    text = spoken(root)
    assert text.startswith(
        "Urgent alert from Amina Stays. Wanjiru Kamau (2 5 4 7 2 2 3 3 3 4 4 4), staying at Blue Reef"
    )
    assert f"(ref {b.ref}), needs help. Press 1 to be connected to the guest now." in text
    assert root.findall("Say")[-1].text == "The details have also been sent to you by text. Goodbye."
    bridged = ET.fromstring(process_voice({**payload, "dtmfDigits": "1"}))
    assert spoken(bridged) == "Connecting you to the guest now."
    assert bridged.find("Dial").get("phoneNumbers") == KE_GUEST
    alert.refresh_from_db()
    assert alert.status == "acknowledged"
    session = VoiceSession.objects.get(session_id="AT-out-1")
    assert session.direction == "outbound" and session.phone == HOST and session.state["alert_id"] == alert.pk


@pytest.mark.django_db
def test_the_demo_lab_safety_call_finds_the_open_alert(homes, host, wanjiru, api):
    r = api.post("/api/demo/voice", {"phone": HOST, "session": "demo-1", "direction": "Outbound"}, format="json")
    assert "There are no open alerts" in r.json()["xml"]
    sms("HELP")
    r = api.post("/api/demo/voice", {"phone": HOST, "session": "demo-2", "direction": "Outbound"}, format="json")
    assert "Wanjiru Kamau" in r.json()["xml"] and "Press 1 to be connected" in r.json()["xml"]
    r = api.post(
        "/api/demo/voice", {"phone": HOST, "session": "demo-2", "direction": "Outbound", "digits": "5"}, format="json"
    )
    assert "Press 1 to be connected" in r.json()["xml"]  # any other key repeats the alert
    r = api.post(
        "/api/demo/voice", {"phone": HOST, "session": "demo-2", "direction": "Outbound", "digits": "1"}, format="json"
    )
    assert f'phoneNumbers="{KE_GUEST}"' in r.json()["xml"]
    assert Alert.objects.get().status == "acknowledged"


@pytest.mark.django_db
def test_a_live_sos_call_is_pre_registered_by_session_id(homes, host, wanjiru, settings):
    settings.AT_API_KEY, settings.AT_VOICE_NUMBER = "live-key", "+254711082000"
    entries = {
        "entries": [{"phoneNumber": HOST, "status": "Queued", "sessionId": "ATVId_live1"}],
        "errorMessage": "None",
    }
    with mock.patch("apps.comms.at._post", return_value=entries) as post:
        [ack] = sms("HELP")
    assert ack.startswith("We are calling Amina right now.")
    assert post.call_args.kwargs["data"]["clientRequestId"] == f"alert-{Alert.objects.get().pk}"
    alert = Alert.objects.get()
    assert alert.call_status == "Queued"
    session = VoiceSession.objects.get(session_id="ATVId_live1")
    assert session.state == {"purpose": "alert", "alert_id": alert.pk} and session.direction == "outbound"
    root = voice("", session="ATVId_live1", phone=HOST, direction="Outbound", destinationNumber=HOST)
    assert "needs help. Press 1" in spoken(root)


@pytest.mark.django_db
def test_a_call_africas_talking_could_not_place_leaves_no_session(homes, host, wanjiru, settings):
    b = stay(homes["Blue Reef Apartment"], wanjiru, days(0), days(2))
    settings.AT_API_KEY, settings.AT_VOICE_NUMBER = "live-key", "+254711082000"
    refused = {"entries": [{"phoneNumber": HOST, "status": "InvalidPhoneNumber", "sessionId": "None"}]}
    with mock.patch("apps.comms.at._post", return_value=refused):
        sms("HELP")
        ivr.place_welcome_call(b)
    assert not VoiceSession.objects.exists()  # AT's sessionId "None" is not a call
    assert Alert.objects.get().call_status == "InvalidPhoneNumber"


@pytest.mark.django_db
def test_numbers_go_to_africas_talking_in_international_format(settings, site):
    from apps.comms import at

    settings.AT_API_KEY, settings.AT_VOICE_NUMBER = "live-key", "0711 082 000"
    with mock.patch("apps.comms.at._post", return_value={"entries": []}) as post:
        at.voice_call(["0722 333 444", "", "+44 7700 900555", "not a number"])
    assert post.call_args.kwargs["data"]["to"] == "+254722333444,+447700900555"
    assert post.call_args.kwargs["data"]["from"] == "+254711082000"
    with pytest.raises(at.ATError):
        at.voice_call("ext 12")
    site.host_phone, site.backup_phone = "0700 000 001", "254700000099"  # saved before Settings checked numbers
    site.save()
    dial = call("1", "4", "1", session="v-dial", phone=NEW).find("Dial")
    assert dial.get("phoneNumbers") == "+254700000001,+254700000099"


@pytest.mark.django_db
def test_the_guest_on_a_call_is_whichever_number_is_not_ours(homes, wanjiru, settings):
    settings.AT_VOICE_NUMBER = "+254711082000"
    b = stay(homes["Blue Reef Apartment"], wanjiru, days(0), days(2))
    placed = {"direction": "Outbound", "clientRequestId": f"welcome-{b.ref}"}  # not pre-registered
    # AT documents callerNumber as the person and destinationNumber as our number, for calls we place too
    root = voice("", session="ATVId_doc", phone=KE_GUEST, destinationNumber="+254711082000", **placed)
    assert spoken(root).startswith("Karibu Wanjiru! This is Amina Stays.")
    voice("", session="ATVId_swap", phone="+254711082000", destinationNumber="0722 333 444", **placed)
    voice("", session="ATVId_in", phone="0722333444")
    assert dict(VoiceSession.objects.values_list("session_id", "phone")) == {
        "ATVId_doc": KE_GUEST,
        "ATVId_swap": KE_GUEST,
        "ATVId_in": KE_GUEST,
    }


# ---------- the optional welcome call ----------


@pytest.mark.django_db
def test_the_arrival_welcome_call_walks_the_guest_in(homes, wanjiru, settings):
    b = stay(homes["Blue Reef Apartment"], wanjiru, days(0), days(2))
    res = {"entries": [{"phoneNumber": KE_GUEST, "status": "Queued", "sessionId": "ATVId_welcome"}]}
    with mock.patch("apps.comms.at.voice_call", return_value=res):
        ivr.place_welcome_call(b)
    out = dict(session="ATVId_welcome", direction="Outbound", destinationNumber=KE_GUEST)
    root = voice("", **out)
    assert spoken(root).startswith("Karibu Wanjiru! This is Amina Stays. Your door code for Blue Reef Apartment")
    assert spoken(voice("1", **out)).startswith("Blue Reef Apartment. Head down Mount Kenya Road")


# ---------- sessions ----------


@pytest.mark.django_db
def test_each_call_keeps_its_own_state_between_callbacks(homes):
    call("1", "1", "2", session="call-A", phone=NEW)  # mid-booking
    call("2", session="call-B", phone="+254799000444")  # a second caller, in Kiswahili
    a, b = VoiceSession.objects.get(session_id="call-A"), VoiceSession.objects.get(session_id="call-B")
    assert a.state["step"] == "nights" and a.state["check_in"] == days(1).isoformat() and a.state["lang"] == "en"
    assert b.state == {"step": "main", "lang": "sw"}
    assert spoken(voice("3", session="call-A", phone=NEW)).startswith("How many guests?")  # A carries on where it was


@pytest.mark.django_db
def test_a_broken_hop_answers_politely(homes):
    call("1", "1", "2", "2", "2", phone=NEW)
    VoiceSession.objects.filter(session_id="v-flow").update(
        state={"step": "pick", "lang": "en", "options": [{"id": 999999}]}
    )
    root = voice("1", phone=NEW)
    assert spoken(root) == "Sorry, something went wrong. Please try again later."
