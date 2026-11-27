"""USSD end to end. Every menu path a guest (and Amina and her staff) can dial, replayed exactly the way
Africa's Talking posts it: the whole input chain on every hop. The `ussd()` helper checks every screen
(160 characters including the CON/END prefix, no menu cut off) on every single hop."""

from datetime import timedelta
from unittest import mock

import pytest

from apps.accounts.models import User
from apps.bookings.models import AccessCode, Addon, Booking, BookingAddon, Waitlist
from apps.core.utils import kes, today, weekend_start
from apps.messaging.models import Conversation, Message, Thread
from apps.operations.models import Task
from apps.operations.services import kitchen_sheet
from apps.payments.models import Payment
from apps.properties.models import Amenity, PriceOverride, Unit
from apps.properties.services import from_price
from apps.properties.services import quote as price_quote
from apps.safety.models import Alert
from apps.support.models import Ticket

from .conftest import days
from .flowkit import (
    KE_GUEST,
    bodies,
    build_catalogue,
    ddmm,
    frozen,
    kenya,
    last_id,
    make_user,
    options,
    pay,
    sms,
    stay,
    ussd,
    with_id,
)

NEW = "+254799000111"  # a number that has never contacted us
HOST = "+254700000001"


@pytest.fixture
def homes(db):
    return build_catalogue()[1]


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
def wanjiru(db):
    return with_id(make_user(KE_GUEST, name="Wanjiru Kamau"))


@pytest.fixture
def in_house(homes, wanjiru):
    """Wanjiru checked in to Blue Reef today for three nights, with two adults."""
    return stay(homes["Blue Reef Apartment"], wanjiru, days(0), days(3), adults=2, checked_in=True)


def breakfast_addon():
    return Addon.objects.get(code="breakfast")


# ---------- who is calling ----------


@pytest.mark.django_db
def test_an_unknown_number_gets_the_welcome_menu_and_an_account(homes):
    home = ussd("", phone=NEW)
    assert home.startswith("CON Karibu Amina Stays\n")
    assert options(home) == [str(i) for i in range(1, 10)]
    assert "9. EMERGENCY" in home
    user = User.objects.get(phone=NEW)
    assert user.first_channel == "ussd" and user.lang == "en" and user.role == "guest"


@pytest.mark.django_db
def test_a_returning_guest_is_welcomed_back_by_first_name(homes, wanjiru):
    assert ussd("").startswith("CON Karibu Amina Stays")  # no stay yet: the plain welcome
    stay(homes["Old Town Loft"], wanjiru, days(4), days(5))
    assert ussd("").startswith("CON Karibu tena Wanjiru!\n1. Book a stay")


# ---------- 1. Book a stay ----------


@pytest.mark.django_db
def test_book_a_stay_with_breakfast_pay_in_full_then_m_pesa_confirms(homes, settings):
    settings.SIM_PAY_DELAY_SECONDS = 6  # the demo's simulated M-Pesa: the guest "approves" after a few seconds
    ci, co = days(10), days(12)
    unit = homes["Diani Palm Suite"]
    where = ussd("1", phone=NEW)
    assert where == "CON Where?\n1. Nyali\n2. Diani\n3. Old Town\n4. Bamburi\n5. Mtwapa\n6. Anywhere"
    when = ussd("1*2", phone=NEW)
    assert when.startswith("CON Check-in:\n1. Tonight\n2. Tomorrow\n3. This weekend\n4. Next weekend\n5. Enter date")
    assert ussd("1*2*5", phone=NEW) == "CON Enter check-in date as DDMM, e.g. 0512"
    chain = f"1*2*5*{ddmm(ci)}"
    assert ussd(chain, phone=NEW) == "CON How many nights? (1-14)"
    assert ussd(f"{chain}*2", phone=NEW) == "CON How many guests? (1-8)"
    pick = ussd(f"{chain}*2*2", phone=NEW)
    plain = price_quote(unit, ci, co, guests=2)
    assert pick == f"CON Pick a home ({ci:%d/%m}-{co:%d/%m}):\n1. Diani Palm Suite {kes(plain['total'])}"
    bf = ussd(f"{chain}*2*2*1", phone=NEW)
    assert bf.startswith("CON Add breakfast? (KES 650/person/day)\n1. Swahili") and "5. No thanks" in bf
    q = price_quote(
        unit, ci, co, guests=2, addons=[{"addon": breakfast_addon(), "quantity": 2}], payment_plan="deposit"
    )
    plan = ussd(f"{chain}*2*2*1*1", phone=NEW)
    assert plan == f"CON Total {kes(q['total'])}\n1. Pay all now\n2. Pay 30% now ({kes(q['deposit'])})"

    with mock.patch("apps.payments.providers.threading.Timer") as timer:
        done = ussd(f"{chain}*2*2*1*1*1", phone=NEW)
    b = Booking.objects.get(guest__phone=NEW)
    assert done.startswith(f"END Holding Diani Palm Suite ({b.ref}). ") and "M-Pesa" in done
    assert done.endswith(f"{kes(q['total'])}.")  # the prompt is for the full total
    assert (b.status, b.channel, b.unit, b.check_in, b.check_out, b.adults) == ("held", "ussd", unit, ci, co, 2)
    assert b.payment_plan == "full" and b.total == q["total"] and b.amount_due_now == q["total"]
    meal = b.addons.get(addon__code="breakfast")
    assert meal.details["style"] == "swahili" and meal.quantity == 2 and meal.status == "confirmed"
    prompt = Payment.objects.get(booking=b)
    assert (prompt.method, prompt.status, prompt.amount, prompt.phone) == ("mpesa", "pending", q["total"], NEW)
    assert not bodies(NEW)  # nothing is texted until M-Pesa confirms

    delay, callback = timer.call_args.args[:2]
    assert delay == 6 and timer.call_args.kwargs["args"] == (prompt.pk,) and timer.return_value.start.called
    before = last_id()
    with mock.patch("apps.payments.providers.close_old_connections"):
        callback(prompt.pk)  # the timer fires: the simulated M-Pesa callback settles the payment
    b.refresh_from_db()
    assert b.status == "confirmed" and b.payment_status == "paid"
    assert Payment.objects.get(booking=b).transaction_id.startswith("SIM")
    [confirmation] = bodies(NEW, before)
    assert confirmation.startswith("Booked! Diani Palm Suite") and b.ref in confirmation
    assert f"Paid {kes(q['total'])}" in confirmation and "Balance" not in confirmation
    assert any(f"New booking {b.ref} via USSD" in m for m in bodies(HOST, before))
    [row] = kitchen_sheet(ci + timedelta(days=1))  # the cook sees it the first morning
    assert (row["ref"], row["style"], row["people"]) == (b.ref, "swahili", 2)


@pytest.mark.django_db
def test_book_with_a_deposit_then_pay_the_balance_from_my_booking(homes):
    ci = days(15)
    chain = f"1*2*5*{ddmm(ci)}*3*2*1*5*2"  # Diani, 3 nights, 2 guests, no breakfast, pay 30% now
    unit = homes["Diani Palm Suite"]
    q = price_quote(unit, ci, ci + timedelta(days=3), guests=2, payment_plan="deposit")
    assert ussd(chain[:-2], phone=NEW).endswith(f"2. Pay 30% now ({kes(q['deposit'])})")
    done = ussd(chain, phone=NEW)
    b = Booking.objects.get(guest__phone=NEW)
    assert done.startswith(f"END Holding Diani Palm Suite ({b.ref}). ") and "M-Pesa" in done
    assert done.endswith(f"{kes(q['deposit'])}.")  # the prompt is for the deposit only
    assert b.payment_plan == "deposit" and b.amount_due_now == q["deposit"] and not b.addons.exists()

    before = last_id()
    pay(b)
    balance = q["total"] - q["deposit"]
    assert b.status == "confirmed" and b.payment_status == "deposit_paid" and b.balance_due == balance
    [confirmation] = bodies(NEW, before)
    assert f"Paid {kes(q['deposit'])}. Balance {kes(balance)} due" in confirmation

    mine = ussd("3", phone=NEW)
    assert mine.startswith(f"CON {b.ref} Diani Palm Suite\n")
    assert f"Paid {kes(q['deposit'])} of {kes(q['total'])}" in mine and "4. Cancel booking" in mine
    pay_balance = ussd("3*2", phone=NEW)
    assert pay_balance.startswith("END ") and "M-Pesa" in pay_balance and pay_balance.endswith(f"{kes(balance)}.")
    balance_prompt = Payment.objects.filter(booking=b, status="pending").get()
    assert balance_prompt.amount == balance and balance_prompt.purpose == "balance"
    before = last_id()
    pay(b)
    assert b.balance_due == 0 and b.payment_status == "paid"
    assert bodies(NEW, before) == [f"Payment received: {kes(balance)} for {b.ref}. You're fully paid - thank you!"]
    assert ussd("3*2", phone=NEW) == "END You're fully paid - asante!"


@pytest.mark.django_db
def test_tomorrow_is_pay_in_full_only_and_breakfast_can_be_declined(homes):
    chain = "1*6*2*1*1*1*5"  # anywhere, tomorrow, 1 night, 1 guest, first home, no breakfast
    assert ussd(chain, phone=NEW).endswith("\n1. Confirm & pay")  # balance would be due before arrival
    done = ussd(f"{chain}*1", phone=NEW)
    b = Booking.objects.get(guest__phone=NEW)
    assert done.startswith(f"END Holding {b.unit.name} ({b.ref})")
    assert b.check_in == days(1) and b.nights == 1 and b.payment_plan == "full" and not b.addons.exists()


@pytest.mark.django_db
def test_homes_with_a_longer_minimum_stay_are_not_offered_for_one_night(homes):
    pick = ussd("1*6*1*1*1", phone=NEW)  # anywhere, tonight, 1 night, 1 guest
    one_night_ok = [u.name for u in Unit.objects.order_by("sort_order") if u.min_nights <= 1]
    assert one_night_ok == ["Nyali Breeze Studio", "Old Town Loft"]
    assert "Nyali Breeze Studi" in pick and "Old Town Loft" in pick
    assert "Diani Palm Suite" not in pick and "Blue Reef" not in pick and "98. More" not in pick
    assert ussd("1*6*1*1*1*2*5*1", phone=NEW).startswith("END Holding Old Town Loft (AMS-")


@pytest.mark.django_db
def test_a_too_short_stay_asks_for_more_nights_instead_of_saying_nothing_is_free(homes):
    ci = days(10)
    chain = f"1*2*5*{ddmm(ci)}*1*2"  # Diani for one night: its only home takes two or more
    assert ussd(chain, phone=NEW) == "CON Homes free then need 2+ nights. How many nights? (2-14)"
    assert (
        ussd(f"{chain}*1", phone=NEW) == "CON Invalid choice. Homes free then need 2+ nights. How many nights? (2-14)"
    )
    pick = ussd(f"{chain}*3", phone=NEW)
    assert pick.startswith(f"CON Pick a home ({ci:%d/%m}-{(ci + timedelta(days=3)):%d/%m}):\n1. Diani Palm Suite")
    ussd(f"{chain}*3*1*5*1", phone=NEW)
    assert Booking.objects.get(guest__phone=NEW).nights == 3 and not Waitlist.objects.exists()


@pytest.mark.django_db
def test_nothing_free_puts_the_caller_on_the_waitlist(homes, wanjiru):
    ci = days(5)
    stay(homes["Old Town Loft"], wanjiru, ci, ci + timedelta(days=2))  # Old Town's only home is taken
    out = ussd(f"1*3*5*{ddmm(ci)}*2*1", phone=NEW)
    assert out == "END Nothing free then. We'll SMS you if something opens up."
    w = Waitlist.objects.get(guest__phone=NEW)
    assert (w.area.name, w.check_in, w.check_out, w.guests, w.channel) == (
        "Old Town",
        ci,
        ci + timedelta(days=2),
        1,
        "ussd",
    )


@pytest.mark.django_db
def test_check_in_shortcuts_pick_the_right_dates(homes):
    t = today()
    for choice, ci in (
        ("1", t),
        ("2", t + timedelta(days=1)),
        ("3", weekend_start(t)),
        ("4", weekend_start(t) + timedelta(days=7)),
    ):
        co = ci + timedelta(days=2)
        pick = ussd(f"1*6*{choice}*2*1", phone=NEW)
        assert pick.startswith(f"CON Pick a home ({ci:%d/%m}-{co:%d/%m}):\n1. "), (choice, pick)


@pytest.mark.django_db
def test_more_pages_through_the_homes_and_back(homes):
    chain = f"1*6*5*{ddmm(days(20))}*2*2"
    first = ussd(chain, phone=NEW)
    assert options(first) == ["1", "2", "3", "98"] and first.endswith("\n98. More")
    second = ussd(f"{chain}*98", phone=NEW)
    assert options(second) == ["4", "5", "6"] and "5. Bamburi Family Hou" in second and "98" not in second
    assert ussd(f"{chain}*98*0", phone=NEW) == first  # 0 = back to the first page
    assert ussd(f"{chain}*98*5*5*1", phone=NEW).startswith("END Holding Bamburi Family House (AMS-")


# ---------- 2. Prices & homes ----------


@pytest.mark.django_db
def test_prices_and_homes_lists_every_home_and_texts_the_details(homes):
    page1 = ussd("2", phone=NEW)
    assert page1.startswith("CON Pick a home (/night):\n1. Nyali Breeze Studi KES ") and page1.endswith("98. More")
    nyali = homes["Nyali Breeze Studio"]
    assert f"1. Nyali Breeze Studi {kes(from_price(nyali))}" in page1
    page2 = ussd("2*98", phone=NEW)
    assert options(page2) == ["5", "6"] and "Mtwapa Creek Cotta" in page2
    mtwapa = homes["Mtwapa Creek Cottage"]
    out = ussd("2*98*6", phone=NEW)
    assert out == (
        f"END Mtwapa Creek Cottage, Mtwapa: 2 bed, sleeps 4. From {kes(from_price(mtwapa))}/night. "
        "Breakfast KES 650. Details sent by SMS."
    )
    [details] = bodies(NEW)
    assert details.startswith("Mtwapa Creek Cottage (Mtwapa): ") and details.endswith("/stays/mtwapa-creek-cottage")


# ---------- 3. My booking ----------


@pytest.mark.django_db
def test_my_booking_without_a_booking_and_the_other_stay_menus(homes):
    for chain in ("3", "5", "7"):
        assert ussd(chain, phone=NEW) == "END No active booking for this number. Dial again and choose 1 to book."
    assert ussd("4", phone=NEW) == (
        "END Breakfast KES 650/person/day, 7:30-10:00: Swahili, Continental, Full English, Vegetarian. "
        "Choose it when you book (1)."
    )


@pytest.mark.django_db
def test_my_booking_screen_keeps_all_four_options_in_english_and_kiswahili(homes, wanjiru):
    b = stay(homes["Bamburi Family House"], wanjiru, days(9), days(12), adults=6, plan="deposit")
    for lang, last_option, paid in (("en", "4. Cancel booking", "Paid"), ("sw", "4. Ghairi", "Umelipa")):
        wanjiru.lang = lang
        wanjiru.save()
        mine = ussd("3")
        assert mine.startswith(f"CON {b.ref} Bamburi Family Hou") and mine.endswith(last_option), mine
        assert f"{b.check_in:%d/%m}-{b.check_out:%d/%m}" in mine
        assert f"{paid} {kes(b.amount_paid)}" in mine and kes(b.total) in mine


@pytest.mark.django_db
def test_resend_check_in_info_sends_what_the_stay_is_ready_for(homes, wanjiru, in_house):
    code = AccessCode.objects.get(booking=in_house, revoked_at__isnull=True)
    before = last_id()
    assert ussd("3*1") == "END Sent to you by SMS."
    [sent] = bodies(KE_GUEST, before)
    assert sent.startswith("Welcome to Blue Reef Apartment! Door code: ") and code.code in sent

    guest2 = with_id(make_user("+254733000222", name="Otieno"))
    soon = stay(homes["Diani Palm Suite"], guest2, days(2), days(4))  # check-in at 2pm, two days from now
    with frozen(kenya(days(0), "13:59")):  # a minute short of 48 h before: the confirmation again
        assert ussd("3*1", phone=guest2.phone) == "END Sent to you by SMS."
    assert len(bodies(guest2.phone, before, kind="booking_confirmed")) == 2
    assert not bodies(guest2.phone, before, kind="directions")
    with frozen(kenya(days(0), "14:00")):  # 48 h before check-in: directions and Wi-Fi open, as on the trip page
        ussd("3*1", phone=guest2.phone)
    [directions] = bodies(guest2.phone, before, kind="directions")
    assert "Wi-Fi: DianiPalm" in directions and soon.access_codes.get().code not in directions

    guest3 = make_user("+254733000333", name="Akinyi")
    later = stay(homes["Mtwapa Creek Cottage"], guest3, days(20), days(23))
    ussd("3*1", phone=guest3.phone)
    assert (
        bodies(guest3.phone, before)[-1].startswith("Booked! Mtwapa Creek Cottage")
        and later.ref in bodies(guest3.phone)[-1]
    )


@pytest.mark.django_db
def test_my_booking_late_checkout_is_requested_from_amina(homes, in_house):
    before = last_id()
    assert ussd("3*3") == "END Late checkout (KES 1,500) is requested from Amina. You'll get an SMS."
    req = BookingAddon.objects.get(booking=in_house, addon__code="late_checkout")
    assert req.status == "requested"
    assert any(
        m.startswith(f"REQUEST #{req.pk}:") and f"Reply YES {req.pk} or NO {req.pk}" in m for m in bodies(HOST, before)
    )
    assert ussd("3*3") == "END Late checkout (until 2pm) is already on this booking."
    from apps.bookings import services as bookings

    bookings.decide_addon(req, True)  # Amina says yes: the door code and the auto-checkout move to 2pm
    code = AccessCode.objects.get(booking=in_house, revoked_at__isnull=True)
    assert code.valid_until.astimezone().strftime("%H:%M") == "14:30"
    assert bookings.effective_checkout_time(in_house) == "14:00"


@pytest.mark.django_db
def test_my_booking_cancel_asks_first_then_cancels_with_the_refund(homes, wanjiru):
    b = stay(homes["Old Town Loft"], wanjiru, days(30), days(32))  # flexible: full refund this far out
    quote = ussd("3*4")
    assert quote.startswith(f"CON You'll get {kes(b.amount_paid)} back (100% of what you paid).\n1. Yes, cancel\n2. No")
    assert ussd("3*4*2") == "END Your booking is kept. See you soon!"
    b.refresh_from_db()
    assert b.status == "confirmed"
    before = last_id()
    assert ussd("3*4*1") == f"END You'll get {kes(b.amount_paid)} back (100% of what you paid)."
    b.refresh_from_db()
    assert b.status == "cancelled" and b.cancelled_by == "guest" and b.amount_refunded == b.amount_paid
    assert any(m.startswith(f"Your booking {b.ref}") and "is cancelled" in m for m in bodies(KE_GUEST, before))
    assert any(f"{b.ref}" in m and "cancelled by the guest" in m for m in bodies(HOST, before))


# ---------- 4. Breakfast ----------


@pytest.mark.django_db
def test_breakfast_choose_change_and_cancel_for_an_in_house_guest(homes, in_house):
    menu = ussd("4")
    assert menu.startswith("CON Breakfast (KES 650/person/day):\n1. Swahili")
    assert ussd("4*1") == "CON For how many people? (1-2)"
    assert ussd("4*1*3") == "CON Invalid choice. For how many people? (1-2)"
    out = ussd("4*1*2")
    assert out == "END Breakfast saved: 2 x Swahili (mahamri, chai, mbaazi, fruit), at 08:00. Kitchen told."
    [row] = kitchen_sheet(days(1))
    assert (row["ref"], row["style"], row["people"]) == (in_house.ref, "swahili", 2)

    assert ussd("4*3*1") == "END Breakfast saved: 1 x Full English, at 08:00. Kitchen told."  # change it
    live = in_house.addons.filter(addon__code="breakfast").exclude(status="cancelled")
    assert live.count() == 1 and live.get().details["style"] == "english" and live.get().quantity == 1

    assert ussd("4*5") == "END Breakfast saved: -. Kitchen told."  # no thanks
    assert not kitchen_sheet(days(1))


@pytest.mark.django_db
def test_breakfast_at_a_home_without_a_kitchen_explains_instead_of_crashing(homes, wanjiru):
    loft = homes["Old Town Loft"]
    Unit.objects.filter(pk=loft.pk).update(breakfast_available=False)
    stay(loft, wanjiru, days(0), days(2), checked_in=True)
    out = ussd("4")
    assert out.startswith("END ") and "Breakfast isn't available at this home" in out


# ---------- 5. Report a problem ----------


@pytest.mark.django_db
def test_report_a_problem_opens_a_task_for_the_caretaker_and_tells_everyone(homes, team, in_house):
    menu = ussd("5")
    assert options(menu) == [str(i) for i in range(1, 9)] and "6. Lock/keys" in menu
    before = last_id()
    out = ussd("5*1")
    task = Task.objects.get(booking=in_house)
    assert out == f"END Logged #{task.pk}. Juma has been told and will sort it. Reply HELP by SMS if urgent."
    assert (task.category, task.priority, task.type, task.source) == ("water", "high", "maintenance", "guest")
    assert task.assignee == team["caretaker"] and task.unit == in_house.unit
    staff_sms = bodies(team["caretaker"].phone, before, kind="staff_task")[0]
    assert staff_sms.startswith(f"Kazi mpya #{task.pk}: Water: No water (reported by USSD) at Blue Reef Apartment")
    assert bodies(KE_GUEST, before, kind="issue_logged") == [
        f"Sorry about that! Logged as #{task.pk} - Juma has been notified and will sort it out. Reply HELP if it's an emergency."
    ]
    assert f"Issue #{task.pk} at Blue Reef Apartment via USSD: No water (Wanjiru Kamau)" in bodies(HOST, before)
    assert not Alert.objects.exists()

    ussd("5*6")  # locked out is urgent: a safety alert as well as a task
    lock = Task.objects.get(category="lock")
    assert lock.priority == "urgent"
    alert = Alert.objects.get(kind="urgent_issue")
    assert alert.booking == in_house and alert.source == "ussd"
    assert any(m.startswith("ALERT: Lock reported at Blue Reef Apartment") for m in bodies(HOST))


# ---------- 6. Talk to Amina ----------


@pytest.mark.django_db
def test_talk_to_amina_call_back_request(homes, in_house):
    assert ussd("6") == ("CON Talk to Amina\n1. Call me back\n2. Ask a question\n3. Make a complaint\n4. My requests")
    before = last_id()
    assert ussd("6*1") == "END Amina will call you back shortly."
    thread = Thread.objects.get(phone=KE_GUEST)
    assert thread.needs_reply and thread.waiting_since
    asked = Message.objects.get(thread=thread, direction="in", channel="ussd")
    assert asked.body == "[USSD] Please call me back" and asked.handled == "relayed"
    ticket = Ticket.objects.get(category="callback")  # on the support desk, with a reply-by time
    assert ticket.channel == "ussd" and ticket.booking == in_house
    assert bodies(HOST, before) == [
        f"CALL BACK {ticket.ref}: Wanjiru Kamau {KE_GUEST} ({in_house.ref} Blue Reef Apartment) asked by USSD. "
        f"Reply CALL {ticket.ref} to be connected."
    ]
    assert bodies(KE_GUEST, before, kind="ticket_callback")  # the guest gets the reference by SMS


@pytest.mark.django_db
def test_a_typed_question_is_answered_on_screen_and_logged_for_amina(homes, in_house):
    assert ussd("6*2") == "CON Ask anything, e.g. prices, free suites this weekend, breakfast, check-in time:"
    before = last_id()
    # this guest's own Wi-Fi, from the knowledge base
    assert ussd("6*2*wifi password") == "END Wi-Fi at Blue Reef Apartment: BlueReef / reef-sunrise-2026"
    thread = Thread.objects.get(phone=KE_GUEST)
    asked = Message.objects.get(thread=thread, direction="in", channel="ussd")
    assert asked.body == "[USSD] wifi password" and asked.handled == "auto" and asked.kind == "faq:wifi"
    assert bodies(KE_GUEST, before, channel="ussd") == ["Wi-Fi at Blue Reef Apartment: BlueReef / reef-sunrise-2026"]
    assert bodies(KE_GUEST, before, channel="sms") == [] and bodies(HOST, before) == []
    assert not Thread.objects.get(pk=thread.pk).needs_reply
    # an answer longer than a screen: the start on screen, all of it by SMS
    out = ussd("6*2*Is breakfast available?")
    assert out.startswith("END Yes! Breakfast is KES 650 per person per day") and out.endswith("... More by SMS.")
    [full] = bodies(KE_GUEST, before, channel="sms")
    assert full.startswith("Yes! Breakfast is KES 650") and full.endswith(
        "Booked guests can reply BREAKFAST to choose."
    )


@pytest.mark.django_db
def test_a_typed_question_about_homes_shows_what_a_booking_would_get_and_its_price(homes, wanjiru):
    nyali, blue, loft, diani = (
        homes[n] for n in ("Nyali Breeze Studio", "Blue Reef Apartment", "Old Town Loft", "Diani Palm Suite")
    )
    stay(nyali, wanjiru, days(1), days(3))

    def dates(nights):
        return f"{days(1):%d/%m}-{days(1 + nights):%d/%m}"

    def cost(u, nights):
        return kes(price_quote(u, days(1), days(1 + nights), guests=2)["total"])

    tail = "\nRedial & choose 1 to book. Links by SMS."
    before = last_id()
    # tomorrow, no length given: one night, so only the homes that take one (Blue Reef and most others need two)
    assert ussd("6*2*room for 2 tomorrow", phone=NEW) == f"END Free {dates(1)}:\nOld Town Loft {cost(loft, 1)}{tail}"
    assert bodies(NEW, before, channel="sms") == [
        f"Old Town Loft (Old Town) {cost(loft, 1)}: http://localhost:3000/stays/{loft.slug}"
    ]
    # an area: Nyali Breeze is taken and Blue Reef needs two nights, so the shortest stay it takes is shown
    assert (
        ussd("6*2*Nyali tomorrow for 2", phone=NEW)
        == f"END Free {dates(2)}:\nBlue Reef Apartment {cost(blue, 2)}{tail}"
    )
    stay(blue, wanjiru, days(1), days(4))
    assert ussd("6*2*Nyali tomorrow for 2", phone=NEW) == (
        f"END Nothing free {dates(1)}. Try other dates, or redial and choose 1: we'll SMS you if one opens."
    )
    # one home by name: its details on screen, its page by SMS
    before = last_id()
    out = ussd("6*2*Blue Reef", phone=NEW)
    assert out.startswith(f"END Blue Reef Apartment, Nyali: 2 bed, sleeps 4. From {kes(from_price(blue))}/night.")
    assert out.endswith(" Details sent by SMS.")
    assert bodies(NEW, before, channel="sms") == [
        f"Blue Reef Apartment (Nyali): {blue.summary} Photos & booking: http://localhost:3000/stays/{blue.slug}"
    ]
    # an amenity: the homes that have it
    pool = Amenity.objects.create(code="pool", name="Shared pool", icon="waves", category="outdoor")
    blue.amenities.add(pool)
    diani.amenities.add(pool)
    assert ussd("6*2*is there a pool?", phone=NEW) == (
        f"END With pool, per night from:\nBlue Reef Apartment {kes(from_price(blue))}\n"
        f"Diani Palm Suite {kes(from_price(diani))}{tail}"
    )
    # a place with something the knowledge base answers is a question for it, not a list of homes
    assert ussd("6*2*Nyali parking", phone=NEW) == (
        "END Yes - free secure parking at every home except the Old Town Loft (street parking; tuk-tuks recommended)."
    )


@pytest.mark.django_db
def test_a_question_only_amina_can_answer_goes_to_her_phone_and_her_reply_comes_back(homes, host, in_house):
    before = last_id()
    assert ussd("6*2*Can my cousin visit us one evening?") == (
        "END Asante! Amina has your question and will reply by SMS shortly."
    )
    thread = Thread.objects.get(phone=KE_GUEST)
    assert thread.needs_reply and Message.objects.get(thread=thread, direction="in").handled == "relayed"
    assert bodies(HOST, before) == [
        f"#{thread.pk} Wanjiru Kamau [{in_house.ref} Blue Reef Apartment]: Can my cousin visit us one evening? "
        f"(reply #{thread.pk} <text>)"
    ]
    sms(f"#{thread.pk} Of course, karibu!", phone=HOST)
    assert bodies(KE_GUEST, before) == ["Amina: Of course, karibu!"]
    assert not Thread.objects.get(pk=thread.pk).needs_reply


# ---------- 7. Check out ----------


@pytest.mark.django_db
def test_check_out_by_ussd_revokes_the_code_and_books_the_cleaner(homes, team, in_house):
    assert ussd("7") == ("CON Check out of Blue Reef Apartment now? Your door code will stop working.\n1. Yes\n2. No")
    assert ussd("7*2") == "END Your booking is kept. See you soon!"
    in_house.refresh_from_db()
    assert in_house.status == "checked_in"
    before = last_id()
    assert ussd("7*1") == "END Checked out. Asante, safe travels!"
    in_house.refresh_from_db()
    assert in_house.status == "completed" and in_house.checked_out_at
    assert not AccessCode.objects.filter(booking=in_house, revoked_at__isnull=True).exists()
    turnover = Task.objects.get(type="turnover", unit=in_house.unit)
    assert turnover.assignee == team["cleaner"]
    assert in_house.unit.__class__.objects.get(pk=in_house.unit_id).housekeeping == "dirty"
    assert bodies(KE_GUEST, before, kind="checkout_thanks")
    assert ussd("7") == "END No active booking for this number. Dial again and choose 1 to book."


# ---------- 8. Language ----------


@pytest.mark.django_db
def test_switching_to_kiswahili_changes_every_menu_and_the_texts(homes):
    assert ussd("8", phone=NEW) == "CON More\n1. Explore the area\n2. Service status\n3. Rewards\n4. Language"
    assert ussd("8*4", phone=NEW) == (
        "CON Language / Lugha\n1. English\n2. Kiswahili\n3. Italiano\n4. Deutsch\n5. Francais"
    )
    assert ussd("8*4*2", phone=NEW) == "END Lugha imehifadhiwa."
    assert User.objects.get(phone=NEW).lang == "sw"
    home = ussd("", phone=NEW)
    assert home.startswith("CON Karibu Amina Stays\n1. Weka nafasi\n2. Bei na nyumba") and "9. DHARURA" in home
    assert ussd("1", phone=NEW).startswith("CON Wapi?\n1. Nyali")
    assert ussd("1*2", phone=NEW).startswith("CON Kuingia:\n1. Leo usiku\n2. Kesho")
    assert ussd("3", phone=NEW) == "END Hakuna nafasi kwa nambari hii. Piga tena uchague 1."
    ussd(f"1*2*5*{ddmm(days(10))}*2*2*1*5*1", phone=NEW)
    b = Booking.objects.get(guest__phone=NEW)
    assert b.lang == "sw"
    pay(b)
    assert bodies(NEW)[-1].startswith("Imethibitishwa! Diani Palm Suite")


@pytest.mark.django_db
def test_other_languages_keep_english_menus_but_change_the_texts(homes):
    assert ussd("8*4*4", phone=NEW) == "END Language saved."
    assert User.objects.get(phone=NEW).lang == "de"
    assert ussd("", phone=NEW).startswith("CON Karibu Amina Stays\n1. Book a stay")


# ---------- 9. EMERGENCY ----------


@pytest.mark.django_db
def test_emergency_alerts_amina_rings_her_and_tells_the_backup(homes, in_house, site):
    site.backup_phone = "+254700000099"
    site.save()
    before = last_id()
    assert ussd("9") == "END Amina is being alerted and called now. If you are in danger call 999 or 112."
    alert = Alert.objects.get()
    assert (alert.kind, alert.severity, alert.source, alert.status) == ("sos", "critical", "ussd", "open")
    assert alert.booking == in_house and alert.phone == KE_GUEST and alert.call_status == "dry_run"
    [urgent] = bodies(HOST, before)
    assert urgent.startswith(f"URGENT HELP (ussd): Wanjiru Kamau ({KE_GUEST}), staying at Blue Reef Apartment")
    assert "Calling you now. Reply OK when handled." in urgent
    assert bodies("+254700000099", before)[0].startswith("URGENT for Amina: guest Wanjiru Kamau")


@pytest.mark.django_db
def test_emergency_in_kiswahili(homes, wanjiru):
    wanjiru.lang = "sw"
    wanjiru.save()
    assert ussd("9") == "END Amina anaarifiwa na kupigiwa sasa. Ukiwa hatarini piga 999 au 112."
    assert Alert.objects.filter(phone=KE_GUEST, kind="sos").exists()


# ---------- invalid input and navigation ----------


@pytest.mark.django_db
def test_invalid_choices_reprompt_and_a_retry_carries_on(homes):
    bad = ussd("77", phone=NEW)
    assert bad.startswith("CON Invalid choice.") and bad.endswith("9. EMERGENCY")  # the whole menu survives
    assert ussd("1*9", phone=NEW).startswith("CON Invalid choice.\nWhere?\n1. Nyali")
    assert ussd("1*9*2", phone=NEW).startswith("CON Check-in:")  # the retry is read from the same chain
    assert ussd("1*2*3*20", phone=NEW) == "CON Invalid choice. How many nights? (1-14)"
    assert ussd("1*2*3*20*2", phone=NEW) == "CON How many guests? (1-8)"
    assert ussd("1*2*3*2*9", phone=NEW) == "CON Invalid choice. How many guests? (1-8)"


@pytest.mark.django_db
def test_a_mistyped_date_is_asked_again_instead_of_ending_the_session(homes):
    assert ussd("1*2*5*3299", phone=NEW) == "CON Invalid choice. Enter check-in date as DDMM, e.g. 0512"
    assert ussd("1*2*5*hello", phone=NEW) == "CON Invalid choice. Enter check-in date as DDMM, e.g. 0512"
    assert ussd(f"1*2*5*3299*{ddmm(days(10))}", phone=NEW) == "CON How many nights? (1-14)"


@pytest.mark.django_db
def test_zero_goes_back_and_double_zero_goes_home(homes):
    home = ussd("", phone=NEW)
    assert ussd("1*0", phone=NEW) == home
    assert ussd("1*2*0", phone=NEW) == ussd("1", phone=NEW)
    assert ussd("1*2*3*0", phone=NEW) == ussd("1*2", phone=NEW)
    assert ussd("1*2*3*00", phone=NEW) == home
    assert ussd("1*2*00*2", phone=NEW) == ussd("2", phone=NEW)
    assert ussd("0", phone=NEW) == home


@pytest.mark.django_db
def test_every_screen_a_staying_guest_can_reach_fits_in_both_languages(homes, team, in_house, wanjiru):
    skip = ("9", "7*1", "3*4*1", "8")  # emergency, checkout, cancel and a language switch change the story
    for lang in ("en", "sw"):
        wanjiru.lang = lang
        wanjiru.save()
        seen, queue = set(), [""]
        while queue:
            chain = queue.pop(0)
            if chain in seen or chain.startswith(skip) or chain.count("*") > 2:
                continue
            seen.add(chain)
            out = ussd(chain)  # asserts the size, the prefix and that no menu is cut
            if out.startswith("CON"):
                queue += [f"{chain}*{n}" if chain else n for n in options(out)]
        assert len(seen) > 30, lang


# ---------- Amina's own menu ----------


@pytest.mark.django_db
def test_amina_runs_the_business_from_her_ussd_menu(homes, host, in_house, wanjiru):
    ops = ussd("", phone=HOST)
    assert ops.startswith("CON Amina ops\n1. Today\n2. Free tonight\n3. Arrivals/departures\n4. Requests")
    today_line = ussd("1", phone=HOST)
    assert today_line.startswith("END Today: 1 in, 0 out, 1 staying, 0 breakfasts")
    free = ussd("2", phone=HOST)
    assert free.startswith("END Free tonight: Nyali Breeze Studio KES 4,500") and "Blue Reef" not in free
    assert ussd("3", phone=HOST) == "END IN: Blue Reef Apartment. OUT: -"

    assert ussd("4", phone=HOST) == "END No pending requests."
    ussd("3*3")  # Wanjiru asks for a late checkout
    req = BookingAddon.objects.get(addon__code="late_checkout")
    requests = ussd("4", phone=HOST)
    assert requests.startswith("CON Requests\n1. Late checkout") and requests.endswith(in_house.ref)
    before = last_id()
    assert ussd("4*1*1", phone=HOST) == "END Approved. Guest told by SMS."
    req.refresh_from_db()
    assert req.status == "confirmed"
    assert bodies(KE_GUEST, before, kind="request_approved")[0].startswith("Good news - late checkout")

    before = last_id()
    assert ussd("5*1", phone=HOST) == "CON Type your message:"
    assert ussd("5*1*Water is off 10-12 today", phone=HOST) == "END Sent to 1 guest(s)."
    assert bodies(KE_GUEST, before) == ["Amina Stays: Water is off 10-12 today"]

    tasks = ussd("7", phone=HOST)
    assert tasks == "END Open tasks: none"


@pytest.mark.django_db
def test_amina_posts_a_last_minute_deal_and_the_waitlist_hears_first(homes, host):
    waiting = make_user("+254733444555", name="Baraka")
    Waitlist.objects.create(
        guest=waiting, area=homes["Old Town Loft"].area, check_in=days(0), check_out=days(1), guests=1
    )
    deal = ussd("6", phone=HOST)
    assert deal.startswith("CON Discount which?\n1. Nyali Breeze Studio KES 4,500")
    loft = options(deal)[
        [line.split(". ", 1)[1].startswith("Old Town Loft") for line in deal.splitlines()[1:]].index(True)
    ]
    assert ussd(f"6*{loft}", phone=HOST) == "CON Discount %? (10-50)"
    assert ussd(f"6*{loft}*60", phone=HOST) == "CON Invalid choice. Discount %? (10-50)"
    out = ussd(f"6*{loft}*20", phone=HOST)
    assert out == "END Old Town Loft tonight now KES 3,360. 1 waitlisted guest(s) told."
    assert PriceOverride.objects.get(unit__name="Old Town Loft", date=today()).price == 3360
    assert bodies(waiting.phone)[0].startswith("Good news! Old Town Loft")
    assert Conversation.objects.get(phone=waiting.phone).state == "offer"


# ---------- staff menu ----------


@pytest.mark.django_db
def test_staff_work_their_tasks_and_sheets_by_ussd(homes, team, in_house):
    cleaner, cook, guard = team["cleaner"], team["cook"], team["security"]
    assert ussd("", phone=cleaner.phone) == (
        "CON Amina Stays staff\n1. My tasks\n2. Breakfast tomorrow\n3. Today's arrivals"
    )
    assert ussd("1", phone=cleaner.phone) == "END No open tasks. Asante!"
    task = Task.objects.create(
        type="turnover", title="Turnover clean - Blue Reef Apartment", unit=in_house.unit, assignee=cleaner
    )
    mine = ussd("1", phone=cleaner.phone)
    assert mine == f"CON My tasks\n1. #{task.pk} Turnover clean - Blue Re"
    assert ussd("1*1", phone=cleaner.phone) == f"CON #{task.pk} Turnover clean - Blue Reef Apartment\n1. Start\n2. Done"
    assert ussd("1*1*1", phone=cleaner.phone) == f"END Task #{task.pk} started."
    task.refresh_from_db()
    assert task.status == "in_progress" and Unit.objects.get(pk=in_house.unit_id).housekeeping == "cleaning"
    assert ussd("1*1*2", phone=cleaner.phone) == f"END Task #{task.pk} done. Asante!"
    task.refresh_from_db()
    assert task.status == "done" and Unit.objects.get(pk=in_house.unit_id).housekeeping == "clean"

    assert ussd("2", phone=cook.phone) == "END No breakfasts tomorrow."
    ussd("4*2*2")  # Wanjiru orders a continental breakfast for two
    assert ussd("2", phone=cook.phone).startswith("END Breakfasts for ")
    assert "08:00 Blue Reef Apartment: 2x Continental" in ussd("2", phone=cook.phone)
    assert ussd("3", phone=guard.phone) == "END Arrivals: Blue Reef Apartment: Wanjiru Kamau"
