"""Ask Amina by SMS, end to end: every keyword the bot understands, free-text booking in English and
Kiswahili, the knowledge base, relays to Amina's inbox, opt-out, the safety word, Amina's own SMS
commands, staff commands, and the web chat that shares the same thread."""

import re
from datetime import timedelta

import pytest

from apps.accounts.models import User
from apps.bookings.models import AccessCode, Booking, BookingAddon, Waitlist
from apps.core.utils import kes
from apps.messaging.models import Conversation, Message, Thread
from apps.operations.models import Task
from apps.payments.models import Payment
from apps.properties.services import from_price
from apps.reviews.models import Review
from apps.reviews.services import request_review
from apps.safety.models import Alert

from .conftest import days
from .flowkit import KE_GUEST, bodies, build_catalogue, frozen, kenya, last_id, make_user, pay, sms, stay, with_id

HOST = "+254700000001"
NEW = "+254799000222"


@pytest.fixture
def homes(db):
    return build_catalogue()[1]


@pytest.fixture
def wanjiru(db):
    return with_id(make_user(KE_GUEST, name="Wanjiru Kamau"))


@pytest.fixture
def team(db):
    return {
        role: make_user(phone, name=name, role=role, lang="sw")
        for name, phone, role in (
            ("Fatuma Ali", "+254700000011", "cleaner"),
            ("Juma Mwinyi", "+254700000012", "caretaker"),
            ("Mama Zawadi", "+254700000013", "cook"),
            ("Hassan Omar", "+254700000014", "security"),
        )
    }


@pytest.fixture
def upcoming(homes, wanjiru):
    """Confirmed and paid in full, arriving in three days for three nights (two adults)."""
    return stay(homes["Blue Reef Apartment"], wanjiru, days(3), days(6), adults=2)


@pytest.fixture
def in_house(homes, wanjiru):
    return stay(homes["Blue Reef Apartment"], wanjiru, days(0), days(3), adults=2, checked_in=True)


def inbound(phone=KE_GUEST):
    return Message.objects.filter(phone=phone, direction="in").latest("id")


# ---------- greetings, menu, language ----------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "hello",
    [
        "menu",
        "MENU",
        "info",
        "hi",
        "Hi!",
        "Hello.",
        "hey",
        "Jambo",
        "Habari?",
        "mambo",
        "hujambo",
        "ciao",
        "Hallo",
        "Bonjour!",
    ],
)
def test_greetings_in_any_language_get_the_menu(homes, hello):
    [reply] = sms(hello, phone=NEW)
    assert reply.startswith("Ask Amina - reply with: PRICES, BOOK, BREAKFAST") or reply.startswith("Uliza Amina"), reply
    assert not bodies(HOST)


@pytest.mark.django_db
def test_a_returning_guest_is_greeted_by_name_in_their_language(homes, upcoming, wanjiru):
    assert sms("hello")[0].startswith("Karibu tena Wanjiru! Ask Amina - reply with:")
    wanjiru.lang = "sw"
    wanjiru.save()
    assert sms("jambo")[0].startswith("Karibu tena Wanjiru! Uliza Amina - jibu: BEI, BOOK")


@pytest.mark.django_db
def test_language_can_be_changed_by_sms(homes):
    assert sms("LANG SW", phone=NEW) == ["Lugha imewekwa: Kiswahili."]
    assert User.objects.get(phone=NEW).lang == "sw"
    assert sms("Italiano", phone=NEW) == ["Lingua impostata: italiano."]
    assert sms("lang xx", phone=NEW) == ["Reply LANG EN, LANG SW, LANG IT, LANG DE or LANG FR."]
    assert sms("english", phone=NEW) == ["Language set to English."]


@pytest.mark.django_db
def test_a_new_guest_writing_kiswahili_is_answered_in_kiswahili(homes):
    sms("Habari, bei gani?", phone=NEW)
    assert User.objects.get(phone=NEW).lang == "sw"


# ---------- prices ----------


@pytest.mark.django_db
@pytest.mark.parametrize("word", ["PRICES", "price", "rates", "cost?", "tariff", "prezzi", "Preise", "prix"])
def test_price_keywords_list_every_home(homes, word):
    [reply] = sms(word, phone=NEW)
    nyali, mtwapa = homes["Nyali Breeze Studio"], homes["Mtwapa Creek Cottage"]
    # the all-in 'from' price (cleaning and levy included), the same figure as the website, USSD and voice
    assert reply.startswith(
        f"Our homes (per night, from): Nyali Breeze Studio (Nyali, 1BR, 2 guests) {kes(from_price(nyali))};"
    )
    assert f"Mtwapa Creek Cottage (Mtwapa, 2BR, 4 guests) {kes(from_price(mtwapa))}" in reply
    assert from_price(nyali) > nyali.base_price


@pytest.mark.django_db
def test_prices_in_kiswahili(homes):
    assert sms("Bei?", phone=NEW)[0].startswith("Nyumba zetu (kwa usiku, kuanzia): Nyali Breeze Studio")
    assert User.objects.get(phone=NEW).lang == "sw"  # a first message in Kiswahili sets the language


# ---------- breakfast ----------


@pytest.mark.django_db
def test_breakfast_choice_by_digit_with_dietary_needs_then_change_and_cancel(homes, upcoming):
    [menu] = sms("BREAKFAST")
    assert menu.startswith("Breakfast (KES 650/person/day, served 7:30-10:00): 1 Swahili")
    assert Conversation.objects.get(phone=KE_GUEST).state == "breakfast"
    [saved] = sms("1 halal, no pork")
    assert (
        saved
        == "Breakfast set: 2 x Swahili (mahamri, chai, mbaazi, fruit), HALAL, NO PORK, at 08:00. The kitchen has been told. Change any time - reply BREAKFAST."
    )
    meal = upcoming.addons.get(addon__code="breakfast")
    assert meal.details["style"] == "swahili" and meal.details["dietary"] == "HALAL, NO PORK" and meal.quantity == 2
    upcoming.refresh_from_db()
    assert upcoming.addons_amount == 650 * 2 * 3

    sms("kifungua kinywa")
    assert sms("4")[0].startswith("Breakfast set: 2 x Vegetarian / vegan")
    assert upcoming.addons.filter(addon__code="breakfast").exclude(status="cancelled").count() == 1
    sms("BREAKFAST")
    assert sms("0") == ["No problem - no breakfast for this stay. Reply BREAKFAST if you change your mind."]
    assert not upcoming.addons.filter(addon__code="breakfast", status="confirmed").exists()


@pytest.mark.django_db
def test_breakfast_without_a_booking_gets_the_knowledge_base_answer(homes):
    [reply] = sms("Breakfast?", phone=NEW)
    assert reply.startswith("Yes! Breakfast is KES 650 per person per day")


# ---------- arrival: ETA, travel, pickup ----------


@pytest.mark.django_db
def test_eta_is_saved_on_the_booking(homes, upcoming):
    assert sms("ETA 3pm") == ["Thanks! We'll expect you around 15:00."]
    upcoming.refresh_from_db()
    assert upcoming.arrival_eta == "15:00"
    assert sms("arriving at 14:30") == ["Thanks! We'll expect you around 14:30."]
    upcoming.refresh_from_db()
    assert upcoming.arrival_eta == "14:30"


@pytest.mark.django_db
def test_arrive_asks_how_they_travel_then_offers_the_right_pickup(homes, upcoming):
    assert sms("ARRIVE") == [
        "How are you getting here? 1 Flight (Moi Airport) 2 SGR train 3 Car/taxi 4 Bus 5 Already in Mombasa"
    ]
    [tip] = sms("2")
    assert tip.startswith("Thanks! The SGR terminus is at Miritini") and tip.endswith("Reply PICKUP (KES 2,000).")
    upcoming.refresh_from_db()
    assert upcoming.arrival_mode == "sgr"
    assert sms("yes") == ["Added: SGR station pickup (KES 2,000). Reply PAY to pay now."]
    assert upcoming.addons.filter(addon__code="sgr_pickup", status="confirmed").exists()

    sms("travel")
    assert sms("3") == ["For Diani use the Dongo Kundu bypass to avoid Likoni ferry queues."]  # no pickup offer by car


@pytest.mark.django_db
def test_pickup_keyword_adds_the_airport_pickup(homes, upcoming):
    assert sms("PICKUP") == ["Added: Airport pickup (KES 2,500). Reply PAY to pay now."]
    upcoming.refresh_from_db()
    assert upcoming.balance_due == round(2500 * 1.02)


# ---------- requests that need Amina's yes ----------


@pytest.mark.django_db
def test_late_and_early_are_requested_from_amina_who_decides_by_sms(homes, host, in_house):
    before = last_id()
    assert sms("LATE") == ["We've asked Amina about late checkout (until 2pm). You'll hear back shortly."]
    late = BookingAddon.objects.get(booking=in_house, addon__code="late_checkout")
    assert late.status == "requested"
    [ask] = bodies(HOST, before)
    assert (
        ask
        == f"REQUEST #{late.pk}: Wanjiru Kamau ({in_house.ref}, Blue Reef Apartment) asks for Late checkout (until 2pm) at 14:00. Reply YES {late.pk} or NO {late.pk}."
    )

    assert sms("early check-in") == ["We've asked Amina about early check-in (from 11am). You'll hear back shortly."]
    early = BookingAddon.objects.get(booking=in_house, addon__code="early_checkin")

    before, bill = last_id(), Booking.objects.get(pk=in_house.pk).total
    assert sms(f"YES {late.pk}", phone=HOST) == [f"Approved: Late checkout (until 2pm) for {in_house.ref}. Guest told."]
    late.refresh_from_db()
    assert late.status == "confirmed"
    added = Booking.objects.get(pk=in_house.pk).total - bill
    assert added >= 1500
    assert bodies(KE_GUEST, before, kind="request_approved") == [
        f"Good news - late checkout (until 2pm) is confirmed for Blue Reef Apartment. {kes(added)} has been added to your bill."
    ]
    code = AccessCode.objects.get(booking=in_house, revoked_at__isnull=True)
    assert code.valid_until.astimezone().strftime("%H:%M") == "14:30"  # the door code now works until 2pm (+30 min)

    before = last_id()
    assert sms(f"no {early.pk}", phone=HOST) == [
        f"Declined: Early check-in (from 11am) for {in_house.ref}. Guest told."
    ]
    early.refresh_from_db()
    assert early.status == "declined"
    assert bodies(KE_GUEST, before)[0].startswith("Sorry - early check-in (from 11am) isn't possible this time")
    assert sms("YES 99999", phone=HOST) == ["No request #99999."]


@pytest.mark.django_db
def test_clean_is_added_straight_away(homes, in_house):
    assert sms("CLEAN") == ["Added: Mid-stay clean & fresh towels (KES 1,500). Reply PAY to pay now."]
    assert in_house.addons.filter(addon__code="mid_stay_clean", status="confirmed").exists()


@pytest.mark.django_db
def test_extend_quotes_the_extra_nights_when_the_home_is_free(homes, host, in_house):
    [quote] = sms("EXTEND 2")
    assert quote.startswith(f"{in_house.ref}: change to ") and "(5 nights, 2 guests)" in quote
    assert "M-Pesa prompt" in quote and inbound().handled == "auto"


@pytest.mark.django_db
def test_extend_asks_amina_when_the_home_is_taken(homes, host, in_house):
    stay(in_house.unit, make_user("+254733000777", name="Next Guest"), days(3), days(5))
    before = last_id()
    assert sms("ongeza") == ["We've asked Amina about 1 more night. You'll hear back shortly."]
    thread = Thread.objects.get(phone=KE_GUEST)
    [ask] = bodies(HOST, before)
    assert ask.startswith(
        f"EXTEND: Wanjiru Kamau ({in_house.ref}, Blue Reef Apartment) wants 1 more night(s) to {days(4)}."
    )
    assert f"Unit is NOT free - reply #{thread.pk} to answer." in ask
    assert thread.needs_reply and inbound().handled == "relayed"


@pytest.mark.django_db
def test_requests_without_a_booking_say_so(homes):
    for word in ("LATE", "EARLY", "CLEAN", "PICKUP", "CODE", "PAY", "STATUS", "CANCEL"):
        assert sms(word, phone=NEW) == [
            "We couldn't find an active booking for this number. Reply BOOK to make one."
        ], word
    # a question about an extra is for the knowledge base: what it costs, and that it comes with a booking
    [answer] = sms("airport pickup?", phone=NEW)
    assert answer.startswith("Yes - Amina's trusted driver can meet you at Moi International Airport (KES 2,500)")
    assert answer.endswith("Reply PICKUP once booked. Uber, Bolt and Little also work well.")


# ---------- ID, door code ----------


@pytest.mark.django_db
def test_id_by_sms_completes_the_register_and_unlocks_the_held_door_code(homes, site):
    from apps.bookings import services as bookings

    guest = make_user(NEW, name="Hans Muller")
    b = stay(homes["Diani Palm Suite"], guest, days(0), days(2))
    assert bookings.release_code(b) == "waiting_id"
    assert bodies(NEW, kind="code_waiting_id")[0].startswith(
        "Your door code for Diani Palm Suite is ready, but we still need your ID"
    )
    assert sms("CODE", phone=NEW)[0].startswith("Your door code arrives by SMS on the morning of")

    assert sms("ID", phone=NEW)[0].startswith("Kenyan tourism regulations require a guest register")  # just asking
    [saved] = sms("ID 3456-7890", phone=NEW)
    guest.refresh_from_db()
    assert saved == "Thank you - your Kenyan National ID ending 7890 is registered." and guest.has_id
    assert b.occupants.get(is_lead=True).id_last4.endswith("7890")  # the guest register row is updated too

    from apps.core.scheduler import run_due

    before = last_id()
    with frozen(kenya(days(0), "08:05")):  # the morning release pass after the ID came in
        assert run_due(only=["release_codes"]) == {"release_codes": 1}
    b.refresh_from_db()
    code = AccessCode.objects.get(booking=b, revoked_at__isnull=True)
    assert b.status == "checked_in" and code.sent_at
    assert any(code.code in m for m in bodies(NEW, before, kind="checkin_code"))
    assert sms("CODE", phone=NEW)[0].startswith(f"Welcome to Diani Palm Suite! Door code: {code.code}")


@pytest.mark.django_db
def test_too_short_id_is_explained(homes):
    assert sms("ID 12", phone=NEW) == ["Reply ID followed by your ID or passport number, e.g. ID 12345678."]


# ---------- pay, status, cancel ----------


@pytest.mark.django_db
def test_pay_sends_an_m_pesa_prompt_for_what_is_owed(homes, wanjiru):
    from apps.bookings import services as bookings

    b = bookings.create_hold(
        unit=homes["Old Town Loft"], guest=wanjiru, check_in=days(8), check_out=days(9), channel="sms"
    )
    assert sms("PAY") == [f"Check your phone for an M-Pesa prompt for {kes(b.total)}."]
    assert Payment.objects.get(booking=b).status == "pending"
    assert sms("lipa") == [f"Check your phone for an M-Pesa prompt for {kes(b.total)}."]
    assert Payment.objects.filter(booking=b).count() == 1  # a second request within the minute reuses the first
    pay(b)
    assert sms("PAY") == ["You're all paid up - thank you!"]


@pytest.mark.django_db
def test_status_shows_the_booking(homes, upcoming):
    [reply] = sms("status")
    assert reply == (
        f"{upcoming.ref}: Blue Reef Apartment, {upcoming.check_in:%a} {upcoming.check_in.day} {upcoming.check_in:%b} - "
        f"{upcoming.check_out:%a} {upcoming.check_out.day} {upcoming.check_out:%b}. Status: Confirmed. "
        f"Paid {kes(upcoming.total)} of {kes(upcoming.total)}. http://localhost:3000/trips/{upcoming.ref}"
    )


@pytest.mark.django_db
def test_cancel_asks_for_confirmation_no_keeps_yes_cancels(homes, host, wanjiru):
    b = stay(homes["Old Town Loft"], wanjiru, days(20), days(22))  # flexible policy: full refund
    [quote] = sms("CANCEL")
    assert quote.startswith(f"Cancel {b.ref} (Old Town Loft,") and f"You'll get {kes(b.total)} back (100%" in quote
    assert sms("no") == [f"Great - {b.ref} is still on. See you soon!"]
    b.refresh_from_db()
    assert b.status == "confirmed"
    sms(f"cancel {b.ref}")
    before = last_id()
    sms("YES")
    b.refresh_from_db()
    assert b.status == "cancelled" and b.amount_refunded == b.total
    [notice] = bodies(KE_GUEST, before)
    assert (
        notice.startswith(f"Your booking {b.ref} (Old Town Loft,")
        and f"Refund of {kes(b.total)} is on its way." in notice
    )
    assert any("cancelled by the guest" in m for m in bodies(HOST, before))


# ---------- booking by SMS ----------


@pytest.mark.django_db
def test_book_keyword_collects_dates_then_offers_homes_then_holds(homes):
    assert sms("BOOK", phone=NEW) == ["Which dates? e.g. 'this weekend', 'tonight', '5 Dec for 3 nights' or '5-8 Dec'."]
    ci = days(12)
    [offer] = sms(f"{ci.day} {ci:%b} for 3 nights, 2 people", phone=NEW)
    assert offer.startswith(f"Yes! {ci:%a} {ci.day} {ci:%b} - ") and "1) Nyali Breeze Studio (Nyali) KES" in offer
    assert "3) Diani Palm Suite (Diani) KES" in offer and offer.endswith(
        "Totals include fees. Reply 1, 2, 3 to hold it."
    )
    [held] = sms("3", phone=NEW)
    b = Booking.objects.get(guest__phone=NEW)
    assert b.unit.name == "Diani Palm Suite" and b.channel == "sms" and b.nights == 3 and b.adults == 2
    assert held.startswith(f"Holding Diani Palm Suite for {ci:%a} {ci.day} {ci:%b}") and f"Ref {b.ref}" in held
    assert Conversation.objects.get(phone=NEW).state == "awaiting_payment"
    before = last_id()
    pay(b)
    assert bodies(NEW, before)[0].startswith("Booked! Diani Palm Suite")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "ask",
    [
        "Do you have a place in Nyali for 2 people on {d} {m} for 3 nights?",
        "2 guests {d} {m}, 3 nights, Nyali",
        "we are 2 people arriving {m} {d} for 3 nights in Nyali",
    ],
)
def test_free_text_booking_in_english(homes, ask):
    ci = days(12)
    [offer] = sms(ask.format(d=ci.day, m=f"{ci:%b}"), phone=NEW)
    assert offer.startswith(f"Yes! {ci:%a} {ci.day} {ci:%b} - "), offer
    assert "1) Nyali Breeze Studio (Nyali)" in offer and "2) Blue Reef Apartment (Nyali)" in offer
    assert "Diani" not in offer  # Nyali only
    convo = Conversation.objects.get(phone=NEW)
    assert convo.state == "showing" and convo.data["guests"] == 2
    assert convo.data["check_in"] == ci.isoformat() and convo.data["check_out"] == (ci + timedelta(days=3)).isoformat()


@pytest.mark.django_db
def test_free_text_booking_in_kiswahili_is_answered_in_kiswahili(homes):
    [offer] = sms("Habari, naomba chumba Nyali kesho usiku 2 watu 2", phone=NEW)
    assert offer.startswith("Ndiyo! ") and "2) Blue Reef Apartment (Nyali)" in offer and offer.endswith("kuishikilia.")
    [held] = sms("2", phone=NEW)
    b = Booking.objects.get(guest__phone=NEW)
    assert held.startswith("Tumekuwekea Blue Reef Apartment") and b.check_in == days(1) and b.nights == 2
    assert b.lang == "sw"


@pytest.mark.django_db
def test_one_night_requests_only_offer_homes_that_take_one_night(homes):
    ci = days(12)
    [offer] = sms(f"Is anything free on {ci.day} {ci:%b} for 1 night?", phone=NEW)
    assert "Nyali Breeze Studio" in offer and "Old Town Loft" in offer and "Diani Palm Suite" not in offer
    [diani] = sms(f"Diani on {ci.day} {ci:%b} for 1 night please", phone=NEW)
    assert diani == (
        "Diani Palm Suite is free then, but has a minimum stay of 2 nights. Reply with your dates for 2 nights "
        f"or more, e.g. '{ci.day} {ci:%b} for 2 nights'."
    )
    assert not Booking.objects.exists() and not Waitlist.objects.exists()
    [offer] = sms(f"{ci.day} {ci:%b} for 2 nights", phone=NEW)  # Diani is remembered
    assert offer.startswith("Yes! ") and "1) Diani Palm Suite (Diani)" in offer and "Nyali" not in offer


@pytest.mark.django_db
def test_nothing_free_waitlists_and_a_released_home_is_offered(homes, wanjiru):
    ci = days(6)
    held = stay(homes["Old Town Loft"], wanjiru, ci, ci + timedelta(days=1))
    assert sms(f"Old Town {ci.day} {ci:%b} 1 night", phone=NEW) == [
        f"Sorry, nothing is free for {ci:%a} {ci.day} {ci:%b} - {(ci + timedelta(days=1)):%a} {(ci + timedelta(days=1)).day} "
        f"{(ci + timedelta(days=1)):%b}. We've added you to the waitlist and will text you if something opens up."
    ]
    from apps.bookings import services as bookings

    bookings.cancel(held, by="guest")
    offer = bodies(NEW, kind="waitlist_offer")
    assert offer and offer[0].startswith("Good news! Old Town Loft")
    [hold] = sms("BOOK", phone=NEW)
    assert hold.startswith("Holding Old Town Loft") and Booking.objects.get(guest__phone=NEW).status == "held"


# ---------- knowledge base, relay to Amina ----------


@pytest.mark.django_db
def test_knowledge_base_answers_in_the_guests_language(homes, wanjiru):
    # Wi-Fi and directions open 48 h before check-in (bookings.guest_context, the trip page's rule)
    stay(homes["Blue Reef Apartment"], wanjiru, days(1), days(3))  # 2pm check-in tomorrow: inside the 48 h
    assert sms("Is there parking?") == [
        "Yes - free secure parking at every home except the Old Town Loft (street parking; tuk-tuks recommended)."
    ]
    assert sms("wifi password") == ["Wi-Fi at Blue Reef Apartment: BlueReef / reef-sunrise-2026"]
    far = make_user(NEW, name="Far Ahead")
    stay(homes["Diani Palm Suite"], far, days(21), days(23))  # three weeks away
    [placeholder] = sms("wifi password", phone=NEW)
    assert placeholder == "Wi-Fi at Diani Palm Suite: shared 2 days before you arrive"
    assert homes["Diani Palm Suite"].wifi_password not in placeholder
    assert sms("what time is check-in")[0].startswith("Check-in is from 2pm and checkout by 11am.")
    wanjiru.lang = "sw"
    wanjiru.save()
    assert sms("kuna maegesho?") == ["Ndiyo - maegesho ya bure na salama kila nyumba isipokuwa Old Town Loft."]
    assert sms("saa ngapi kuingia?")[0].startswith("Kuingia ni kuanzia 2pm")
    assert inbound().handled == "auto" and inbound().kind == "faq:check_in"


@pytest.mark.django_db
def test_booking_only_answers_are_never_given_to_strangers(homes):
    [reply] = sms("what is the wifi password", phone=NEW)
    assert "reef-sunrise" not in reply and reply.startswith("Yes - every home has fast fibre Wi-Fi")


@pytest.mark.django_db
def test_unknown_questions_are_relayed_to_amina_who_replies_by_sms(homes, host, upcoming):
    [ack] = sms("Can my cousin visit us one evening?")
    assert (
        ack
        == "Thanks! Amina will reply here shortly (usually within 15 minutes, 7am-10pm). For anything urgent reply HELP."
    )
    thread = Thread.objects.get(phone=KE_GUEST)
    assert thread.needs_reply and thread.waiting_since
    assert inbound().handled == "relayed"
    [relay] = bodies(HOST, kind="relay")
    assert (
        relay
        == f"#{thread.pk} Wanjiru Kamau [{upcoming.ref} Blue Reef Apartment]: Can my cousin visit us one evening? (reply #{thread.pk} <text>)"
    )
    assert sms("And can we bring a cake?") == []  # acknowledged once per half hour, but still relayed
    assert len(bodies(HOST, kind="relay")) == 2

    before = last_id()
    assert sms("Of course, karibu!", phone=HOST) == []  # plain text answers the last guest waiting
    assert bodies(KE_GUEST, before) == ["Amina: Of course, karibu!"]
    thread.refresh_from_db()
    assert not thread.needs_reply and thread.waiting_since is None
    assert not Message.objects.filter(thread=thread, direction="in", handled="relayed").exists()
    assert sms("Thanks again", phone=HOST) == ["No guest is waiting for a reply. Start with #<thread> to pick a guest."]


@pytest.mark.django_db
def test_amina_replies_to_a_chosen_thread_with_hash(homes, host, wanjiru):
    other = make_user(NEW, name="Baraka")
    sms("Do you know a good tailor in town?", phone=NEW)
    sms("Is the beach walkable at night?")
    baraka = Thread.objects.get(phone=NEW)
    before = last_id()
    assert sms(f"#{baraka.pk} Yes - Mama Fatma at Biashara Street", phone=HOST) == []
    assert bodies(NEW, before) == ["Amina: Yes - Mama Fatma at Biashara Street"]
    assert not bodies(KE_GUEST, before)
    assert Thread.objects.get(phone=KE_GUEST).needs_reply and not Thread.objects.get(pk=baraka.pk).needs_reply
    assert sms("#99999 hello", phone=HOST) == ["No guest thread #99999."]
    assert other.threads.exists()


@pytest.mark.django_db
def test_amina_status_and_help_commands(homes, host, in_house):
    assert sms("STATUS", phone=HOST) == [
        "Today: 1 arriving, 0 leaving, 1 in-house, 0 breakfasts, 0 tasks, 0 chats waiting, 0 alerts."
    ]
    assert sms("help", phone=HOST)[0].startswith("Commands: #12 <text> reply to guest 12")


@pytest.mark.django_db
def test_a_co_host_manager_can_answer_guests_by_sms_too(homes, wanjiru):
    make_user("+254700000020", name="Rehema", role="manager")
    sms("Can I store my surfboard somewhere?")
    before = last_id()
    assert sms("Yes, in the store room by the gate", phone="+254700000020") == []
    assert bodies(KE_GUEST, before) == ["Amina: Yes, in the store room by the gate"]


# ---------- opt-out ----------


@pytest.mark.django_db
def test_stop_and_start(homes, wanjiru):
    wanjiru.marketing_opt_in = True
    wanjiru.save()
    assert sms("STOP")[0].startswith("You won't get promotional messages from Amina Stays any more.")
    wanjiru.refresh_from_db()
    assert wanjiru.sms_opt_out_at and not wanjiru.marketing_opt_in
    from apps.messaging import services as messaging

    assert messaging.send(KE_GUEST, "10% off this weekend!", marketing=True) is None
    assert messaging.send(KE_GUEST, "Your door code is 1234", kind="checkin_code") is not None  # service SMS still go
    assert sms("START") == ["You're subscribed to offers from Amina Stays. Reply STOP any time."]
    wanjiru.refresh_from_db()
    assert wanjiru.sms_opt_out_at is None and wanjiru.marketing_opt_in
    assert sms("ACHA")[0].startswith("You won't get promotional messages")


# ---------- safety ----------


@pytest.mark.django_db
def test_help_raises_an_sos_rings_amina_and_she_acknowledges_with_ok(homes, host, in_house):
    before = last_id()
    [ack] = sms("HELP someone is trying the door")
    assert (
        ack
        == "We are calling Amina right now. She will contact you immediately. If you are in danger call 999 or 112 (police/ambulance) now."
    )
    alert = Alert.objects.get()
    assert (alert.kind, alert.severity, alert.source, alert.status, alert.booking) == (
        "sos",
        "critical",
        "sms",
        "open",
        in_house,
    )
    assert alert.details == "someone is trying the door" and alert.call_status == "dry_run" and alert.calls_made == 1
    [urgent] = bodies(HOST, before)
    assert urgent.startswith(f"URGENT HELP (sms): Wanjiru Kamau ({KE_GUEST}), staying at Blue Reef Apartment, Nyali")
    assert 'They said: "someone is trying the door"' in urgent
    assert inbound().handled == "escalated"

    assert sms("OK", phone=HOST) == [f"Alert #{alert.pk} acknowledged."]
    alert.refresh_from_db()
    assert alert.status == "acknowledged" and alert.acknowledged_by == host
    assert sms("ok", phone=HOST) == ["No open alerts."]


@pytest.mark.django_db
def test_msaada_in_kiswahili(homes, host, wanjiru):
    wanjiru.lang = "sw"
    wanjiru.save()
    assert sms("MSAADA") == [
        "Tunampigia Amina simu sasa hivi. Atawasiliana nawe mara moja. Ukiwa hatarini piga 999 au 112 (polisi/ambulensi) sasa."
    ]
    assert Alert.objects.get().source == "sms"


# ---------- problems, check-in acknowledgement, checkout ----------


@pytest.mark.django_db
def test_problems_become_tasks_for_the_right_person(homes, team, in_house):
    before = last_id()
    [logged] = sms("PROBLEM the toilet is blocked")
    task = Task.objects.get()
    assert logged.startswith(f"Sorry about that! Logged as #{task.pk} - Juma has been notified")
    assert (task.category, task.priority, task.assignee, task.booking) == (
        "plumbing",
        "high",
        team["caretaker"],
        in_house,
    )
    assert bodies(KE_GUEST, before, kind="issue_logged")[0].startswith(f"Sorry about that! Logged as #{task.pk} - Juma")
    assert bodies(HOST, before)[0] == f"Issue #{task.pk} at Blue Reef Apartment (Wanjiru Kamau): the toilet is blocked"
    assert bodies(team["caretaker"].phone, before, kind="staff_task")
    sms("The AC is not working in the bedroom")  # no keyword needed
    assert Task.objects.filter(category="ac").exists()


@pytest.mark.django_db
def test_settled_in_reply_is_acknowledged(homes, in_house):
    assert sms("1") == ["Asante! Have a lovely stay."]
    assert sms("all good") == ["Asante! Have a lovely stay."]


@pytest.mark.django_db
def test_checkout_by_sms(homes, team, in_house):
    [thanks] = sms("CHECKOUT")
    in_house.refresh_from_db()
    assert in_house.status == "completed" and in_house.checked_out_at
    assert (
        thanks == "Thanks for staying with Amina Stays! Your door code is now deactivated. Safe travels - karibu tena!"
    )
    assert Task.objects.filter(type="turnover", assignee=team["cleaner"]).exists()
    assert sms("toka") == ["We couldn't find an active booking for this number. Reply BOOK to make one."]


@pytest.mark.django_db
def test_review_by_sms_after_the_stay(homes, host, wanjiru):
    b = stay(homes["Old Town Loft"], wanjiru, days(0), days(1), checked_in=True)
    from apps.bookings import services as bookings

    bookings.check_out(b)
    assert request_review(b)
    assert sms("5") == ["Thank you! Anything you'd like to tell us or future guests? Reply with a comment, or SKIP."]
    assert sms("Lovely loft, great location") == [
        "Asante sana for the 5/5! We'd love to host you again - just text us next time."
    ]
    review = Review.objects.get(booking=b)
    assert review.rating == 5 and review.comment == "Lovely loft, great location" and review.channel == "sms"


@pytest.mark.django_db
def test_a_poor_review_reaches_amina(homes, host, wanjiru):
    b = stay(homes["Old Town Loft"], wanjiru, days(0), days(1), checked_in=True)
    from apps.bookings import services as bookings

    bookings.check_out(b)
    request_review(b)
    before = last_id()
    assert sms("2")[0].startswith("We're sorry it wasn't great.")
    assert any(m.startswith("Low review (2/5) from Wanjiru Kamau") for m in bodies(HOST, before))
    assert Alert.objects.filter(kind="low_review").exists()
    sms("The water was off all day")
    assert Review.objects.get(booking=b).comment == "The water was off all day"
    assert any(m.startswith("Review comment from Wanjiru Kamau (2/5") for m in bodies(HOST, before))


# ---------- staff by SMS ----------


@pytest.mark.django_db
def test_staff_close_their_tasks_by_sms(homes, team, in_house):
    cleaner = team["cleaner"]
    assert sms("TASKS", phone=cleaner.phone) == ["No open tasks. Asante!"]
    task = Task.objects.create(
        type="turnover", title="Turnover clean - Blue Reef", unit=in_house.unit, assignee=cleaner
    )
    assert sms("kazi", phone=cleaner.phone) == [
        f"#{task.pk} Turnover clean - Blue Reef. Reply DONE <id> when finished."
    ]
    assert sms(f"START {task.pk}", phone=cleaner.phone) == [
        f"Task #{task.pk} started. Reply DONE {task.pk} when finished."
    ]
    task.refresh_from_db()
    assert task.status == "in_progress"
    assert sms(f"DONE {task.pk} all fresh", phone=cleaner.phone) == [f"Task #{task.pk} closed. Asante Fatuma!"]
    task.refresh_from_db()
    assert task.status == "done" and task.completion_note == "all fresh"
    assert sms("DONE 99999", phone=cleaner.phone) == ["No task #99999."]


@pytest.mark.django_db
def test_a_bare_done_closes_the_only_open_task(homes, team, in_house):
    caretaker = team["caretaker"]
    sms("PROBLEM no water in the shower")
    task = Task.objects.get(assignee=caretaker)
    before = last_id()
    assert sms("DONE", phone=caretaker.phone) == [f"Task #{task.pk} closed. Asante Juma!"]
    task.refresh_from_db()
    assert task.status == "done"
    assert bodies(KE_GUEST, before, kind="issue_fixed")[0].startswith(f"Update on #{task.pk}: Water has been fixed.")
    second = Task.objects.create(type="maintenance", title="Fix gate light", assignee=caretaker)
    third = Task.objects.create(type="maintenance", title="Replace bulb", assignee=caretaker)
    [which] = sms("imeisha", phone=caretaker.phone)
    assert f"#{second.pk}" in which and f"#{third.pk}" in which and "DONE <id>" in which
    assert sms("Starting late today, sorry", phone=caretaker.phone) == [
        "Sent to Amina. Commands: TASKS, DONE <id>, START <id>"
    ]
    assert Task.objects.get(pk=second.pk).status == "open"  # "starting" is not START


@pytest.mark.django_db
def test_cook_gets_the_breakfast_sheet_and_guard_the_gate_list(homes, team, in_house):
    cook, guard = team["cook"], team["security"]
    assert sms("BREAKFAST", phone=cook.phone) == ["No breakfasts booked for tomorrow."]
    sms("BREAKFAST")
    sms("2 gluten free")
    [sheet] = sms("jikoni", phone=cook.phone)
    assert sheet.startswith("Breakfasts for ") and "08:00 Blue Reef Apartment: 2x Continental (GLUTEN)" in sheet
    assert sms("GATE", phone=guard.phone) == ["Blue Reef Apartment: Wanjiru Kamau"]
    before = last_id()
    assert sms("BREAKFAST", phone=guard.phone) == ["Sent to Amina. Commands: TASKS, DONE <id>, START <id>"]
    assert bodies(HOST, before) == ["Staff Hassan Omar (Security): BREAKFAST"]


@pytest.mark.django_db
def test_anything_else_from_staff_goes_to_amina(homes, team):
    before = last_id()
    assert sms("Running late, matatu broke down", phone=team["cleaner"].phone) == [
        "Sent to Amina. Commands: TASKS, DONE <id>, START <id>"
    ]
    assert bodies(HOST, before) == ["Staff Fatuma Ali (Cleaner): Running late, matatu broke down"]
    assert sms("hello", phone=team["cook"].phone)[0].endswith(", BREAKFAST")


# ---------- web chat ----------


@pytest.mark.django_db
def test_web_chat_shares_the_thread_and_is_answered_on_the_web(homes, host, upcoming, wanjiru, api):
    from rest_framework.test import APIClient

    assert APIClient().get("/api/messages").status_code == 403
    api.force_authenticate(wanjiru)
    sms("Is there parking?")  # an earlier SMS question shows in the same conversation
    r = api.post("/api/messages", {"body": "What is the wifi password?"}, format="json")
    assert r.status_code == 200 and r.data["host"] == "Amina"
    last = r.data["messages"][-1]
    assert last["direction"] == "out" and last["channel"] == "web" and last["body"].startswith("Wi-Fi at Blue Reef")
    assert any(m["channel"] == "sms" and m["body"] == "Is there parking?" for m in r.data["messages"])

    r = api.post("/api/messages", {"body": "Could the caretaker carry our bags upstairs?"}, format="json")
    ack = r.data["messages"][-1]
    assert ack["kind"] == "relay_ack" and ack["channel"] == "web" and ack["status"] == "sent"
    thread = Thread.objects.get(phone=KE_GUEST)
    assert thread.needs_reply and thread.unread > 0
    assert any("Could the caretaker carry our bags upstairs?" in m for m in bodies(HOST, kind="relay"))
    assert api.post("/api/messages", {"body": "  "}, format="json").status_code == 400
    assert api.get("/api/messages").status_code == 200
    thread.refresh_from_db()
    assert thread.unread == 0


@pytest.mark.django_db
def test_web_chat_sos_and_booking_work_like_sms(homes, host, wanjiru, api):
    api.force_authenticate(wanjiru)
    r = api.post("/api/messages", {"body": "HELP"}, format="json")
    assert r.data["messages"][-1]["body"].startswith("We are calling Amina right now.")
    assert Alert.objects.filter(phone=KE_GUEST, source="sms").exists()
    ci = days(15)
    r = api.post("/api/messages", {"body": f"Nyali {ci.day} {ci:%b} for 2 nights, 2 people"}, format="json")
    assert r.data["messages"][-1]["body"].startswith("Yes! ") and r.data["messages"][-1]["channel"] == "web"
    assert re.search(r"Reply 1(, 2)? to hold it\.$", r.data["messages"][-1]["body"])
