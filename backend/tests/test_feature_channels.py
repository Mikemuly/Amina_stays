"""Channels and scheduler features: the balance ladder (C3), the TRA licence reminder and instant changes (C7), the
changes_expire job, and hardening of the Africa's Talking channels - USSD never waits on Daraja, SMS status codes
and retries, repeated inbound webhooks, and outbound calls nobody answers."""

import json
import re
from datetime import date, timedelta
from unittest import mock

import pytest
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.bookings import services as bookings
from apps.bookings.models import Booking
from apps.comms import deferred
from apps.comms import voice as ivr
from apps.comms.at import ATError
from apps.comms.views import process_voice
from apps.core import scheduler
from apps.core.models import Activity, JobRun, SiteSettings
from apps.core.utils import kes, nice_date
from apps.messaging import services as messaging
from apps.messaging.automations import ensure_defaults
from apps.messaging.models import Automation, Message, Thread
from apps.operations.models import Task
from apps.payments.models import Payment
from apps.payments.providers import PaymentError
from apps.payments.services import paybill_number
from apps.safety.models import Alert
from apps.safety.services import escalate, followups, licence_text

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

HOST = "+254700000001"
BACKUP = "+254700000099"


@pytest.fixture
def homes(db):
    homes = build_catalogue()[1]
    ensure_defaults()
    return homes


@pytest.fixture
def wanjiru(db):
    return with_id(make_user(KE_GUEST, name="Wanjiru Kamau"))


def run(*jobs, at):
    """The Demo Lab's 'run now' for these jobs, at a frozen Kenya time."""
    with frozen(at):
        return scheduler.run_due(only=list(jobs))


def balance_due_days(n):
    s = SiteSettings.load()
    s.balance_due_days = n
    s.save()


# ---------- the balance ladder ----------


@pytest.mark.django_db
def test_the_balance_request_goes_out_on_the_due_day_guests_were_given(homes, wanjiru, host_api):
    balance_due_days(6)  # further ahead than the timeline used to look
    b = stay(homes["Diani Palm Suite"], wanjiru, days(14), days(17), plan="deposit")
    assert bookings.guest_context(b)["due_date"] == nice_date(days(8))  # what the confirmation SMS promised
    assert run("automations", at=kenya(days(7), "09:00")) == {"automations": 0}
    assert run("automations", at=kenya(days(8), "08:59")) == {"automations": 0}
    assert run("automations", at=kenya(days(8), "09:00")) == {"automations": 1}
    assert bodies(KE_GUEST, kind="balance_due")[0].startswith(f"Hi Wanjiru, the balance of {kes(b.balance_due)}")
    prompt = Payment.objects.get(booking=b, status="pending")
    assert (prompt.purpose, prompt.amount) == ("balance", b.balance_due)

    # the console's timeline shows that day, and points Amina to Settings to move it
    auto = next(a for a in host_api.get("/api/host/automations").json() if a["key"] == "balance_due")
    assert (auto["anchor"], auto["offset_days"], auto["send_time"]) == ("check_in", -6, "09:00")
    r = host_api.patch(f"/api/host/automations/{auto['id']}", {"offset_days": -2, "send_time": "09:00"}, format="json")
    assert r.status_code == 400 and "6 days before arrival" in r.json()["error"]
    r = host_api.patch(f"/api/host/automations/{auto['id']}", {"offset_days": -6, "send_time": "08:30"}, format="json")
    assert r.status_code == 200 and Automation.objects.get(key="balance_due").send_time == "08:30"


@pytest.mark.django_db
def test_a_week_before_arrival_the_guest_gets_one_balance_heads_up(homes, wanjiru):
    b = stay(homes["Diani Palm Suite"], wanjiru, days(20), days(23), plan="deposit")  # booked three weeks ahead
    soon = make_user("+254733200010", name="Late Booker")
    stay(homes["Blue Reef Apartment"], soon, days(5), days(7), plan="deposit")  # booked only 5 days ahead
    assert run("balance_ladder", at=kenya(days(0), "10:00")) == {"balance_ladder": 0}
    assert run("balance_ladder", at=kenya(days(12), "10:00")) == {"balance_ladder": 0}  # 8 days out
    assert run("balance_ladder", at=kenya(days(13), "07:30")) == {"balance_ladder": 0}  # quiet hours
    assert run("balance_ladder", at=kenya(days(13), "10:00")) == {"balance_ladder": 1}
    assert bodies(KE_GUEST, kind="balance_reminder_soon") == [
        f"Hi Wanjiru, a quick heads-up: the balance of {kes(b.balance_due)} for {b.ref} (Diani Palm Suite) is due "
        f"on {nice_date(days(19))}. Pay any time by M-Pesa or card: {bookings.trip_link(b)}"
    ]
    assert b.events.filter(kind="balance_reminder").exists()
    assert run("balance_ladder", at=kenya(days(14), "10:00")) == {"balance_ladder": 0}  # once per booking
    assert not bodies(soon.phone, kind="balance_reminder_soon")
    assert not Payment.objects.filter(booking=b, purpose="balance").exists()  # a heads-up, not a prompt


@pytest.mark.django_db
def test_an_overdue_balance_gets_one_sms_and_one_automatic_prompt_a_day_until_arrival(homes, wanjiru):
    balance_due_days(3)
    b = stay(homes["Diani Palm Suite"], wanjiru, days(10), days(13), plan="deposit")  # balance due days(7)
    owed = b.balance_due
    assert run("balance_ladder", at=kenya(days(7), "10:00")) == {"balance_ladder": 0}  # the due day: the automation's
    before = last_id()
    assert run("balance_ladder", at=kenya(days(8), "10:00")) == {"balance_ladder": 2}  # the SMS and a prompt
    [overdue] = bodies(KE_GUEST, before)
    assert overdue == (
        f"Hi Wanjiru, the balance of {kes(owed)} for {b.ref} (Diani Palm Suite) was due on {nice_date(days(7))} and "
        f"is still unpaid. Pay by M-Pesa or card on your trip page: {bookings.trip_link(b)} Or pay {kes(owed)} by "
        f"M-Pesa Paybill {paybill_number()}, account {b.ref}. Your door code is sent once it's paid."
    )
    prompt = Payment.objects.get(booking=b, status="pending")
    assert (prompt.method, prompt.purpose, prompt.amount) == ("mpesa", "balance", owed)
    assert Activity.objects.filter(kind="payment", title=f"Balance overdue: {b.ref} still owes {kes(owed)}").exists()
    assert run("balance_ladder", at=kenya(days(8), "15:00")) == {"balance_ladder": 0}  # nothing twice a day
    assert run("balance_ladder", at=kenya(days(9), "10:00")) == {"balance_ladder": 1}  # one more prompt, no SMS
    assert len(bodies(KE_GUEST, kind="balance_overdue")) == 1
    assert Payment.objects.filter(booking=b, purpose="balance").count() == 2
    assert run("balance_ladder", at=kenya(days(10), "10:00")) == {"balance_ladder": 0}  # arrival day: release_code's


@pytest.mark.django_db
def test_no_automatic_prompt_on_top_of_the_guests_own_or_for_card_and_platform_guests(homes, wanjiru):
    balance_due_days(3)
    b = stay(homes["Diani Palm Suite"], wanjiru, days(10), days(13), plan="deposit")
    emma = make_user("+447700900321", name="Emma Stone", nationality="GB")
    card = stay(homes["Old Town Loft"], emma, days(10), days(12), plan="deposit")  # paid her deposit by card
    ota = stay(homes["Nyali Breeze Studio"], make_user("+254733200011", name="Via Airbnb"), days(10), days(12))
    Booking.objects.filter(pk=ota.pk).update(channel="airbnb", amount_paid=0)  # Airbnb collects, not us
    with frozen(kenya(days(8), "09:30")):
        assert ussd("3*2") == f"END Check your phone for the M-Pesa prompt of {kes(b.balance_due)}."
    assert run("balance_ladder", at=kenya(days(8), "10:00")) == {"balance_ladder": 2}  # two SMS, no prompt
    assert Payment.objects.filter(booking=b, purpose="balance").count() == 1  # the one Wanjiru asked for
    assert bodies(emma.phone, kind="balance_overdue") and Payment.objects.filter(booking=card).count() == 1
    assert not bodies(ota.guest.phone, kind="balance_overdue")


@pytest.mark.django_db
def test_arrival_morning_with_the_balance_unpaid_withholds_the_code_and_alerts_amina_once(homes, wanjiru, host):
    b = stay(homes["Blue Reef Apartment"], wanjiru, days(0), days(2))
    bookings.add_addon(b, "airport_pickup", channel="web")  # an extra added after paying
    b.refresh_from_db()
    owed = b.balance_due
    assert run("release_codes", at=kenya(days(0), "08:01")) == {"release_codes": 0}
    alert = Alert.objects.get(kind="payment")
    summary = f"Balance {kes(owed)} unpaid - {b.ref} (Wanjiru Kamau) arrives today; door code withheld."
    assert (alert.summary, alert.severity, alert.status, alert.booking) == (summary, "high", "open", b)
    assert bodies(HOST, kind="alert") == [f"ALERT: {summary} Reply OK when handled."]
    run("release_codes", at=kenya(days(0), "08:30"))
    assert Alert.objects.filter(kind="payment").count() == 1
    pay(b)
    assert run("release_codes", at=kenya(days(0), "08:31")) == {"release_codes": 1}


# ---------- TRA licence, instant changes, the jobs themselves ----------


@pytest.mark.django_db
def test_tra_licence_reminders_go_out_once_per_step_and_a_renewal_closes_them(homes, host):
    assert run("licence_reminder", at=kenya(days(0), "09:00")) == {"licence_reminder": 0}  # no expiry date set
    s = SiteSettings.load()
    s.tra_licence_number, s.tra_licence_expiry = "TRA/MSA/0042", days(46)
    s.save()
    expiry = f"{days(46).day} {days(46):%b %Y}"
    assert run("licence_reminder", at=kenya(days(0), "09:00")) == {"licence_reminder": 0}  # 46 days: not yet
    assert run("licence_reminder", at=kenya(days(1), "09:00")) == {"licence_reminder": 1}
    first = (
        f"Your TRA licence TRA/MSA/0042 expires on {expiry} (45 days). Renew on the TRA portal - licences run to "
        "31 December."
    )
    assert bodies(HOST, kind="licence_reminder") == [first]
    alert = Alert.objects.get(kind="compliance")
    assert (alert.summary, alert.severity, alert.status) == (first, "medium", "open")
    assert run("licence_reminder", at=kenya(days(2), "09:00")) == {"licence_reminder": 0}  # still the 45-day step
    assert run("licence_reminder", at=kenya(days(16), "09:00")) == {"licence_reminder": 1}  # 30 days
    alert.refresh_from_db()
    assert (alert.status, alert.resolution_note) == ("resolved", "Replaced by a newer reminder")
    # the scheduler was off for weeks: the step it has reached goes out, not the 14-day one it missed
    assert run("licence_reminder", at=kenya(days(40), "09:00")) == {"licence_reminder": 1}
    assert run("licence_reminder", at=kenya(days(45), "09:00")) == {"licence_reminder": 1}
    assert run("licence_reminder", at=kenya(days(46), "09:00")) == {"licence_reminder": 1}
    assert run("licence_reminder", at=kenya(days(50), "09:00")) == {"licence_reminder": 0}  # once on/after the day
    sent = bodies(HOST, kind="licence_reminder")
    assert [re.search(r"\((.*?)\)", m)[1] for m in sent] == ["45 days", "30 days", "6 days", "1 day", expiry]
    assert sent[-1].startswith(f"Your TRA licence TRA/MSA/0042 expires today ({expiry}).")
    [still_open] = Alert.objects.filter(kind="compliance").exclude(status="resolved")
    assert still_open.severity == "high" and still_open.summary == sent[-1]
    assert licence_text("", date(2026, 12, 31), -3) == (
        "Your TRA licence expired on 31 Dec 2026 (3 days ago). Renew on the TRA portal - licences run to 31 December."
    )
    s.tra_licence_expiry = days(46) + timedelta(days=365)  # renewed
    s.save()
    assert run("licence_reminder", at=kenya(days(51), "09:00")) == {"licence_reminder": 0}
    still_open.refresh_from_db()
    assert still_open.status == "resolved" and still_open.resolution_note.startswith("Licence renewed")


@pytest.mark.django_db
def test_instant_changes_is_a_host_setting(host_api):
    assert host_api.get("/api/host/settings").json()["instant_changes"] is True
    r = host_api.patch("/api/host/settings", {"instant_changes": False}, format="json")
    assert r.status_code == 200 and r.json()["instant_changes"] is False
    assert SiteSettings.load().instant_changes is False


@pytest.mark.django_db
def test_the_new_jobs_run_on_their_schedule_and_report_plain_json(homes):
    with mock.patch("apps.bookings.services.expire_stale_changes", return_value=2) as expire:
        early = run_pass(kenya(days(1), "08:59"))
        late = run_pass(kenya(days(1), "10:00"))
    assert expire.call_count == 2  # every pass: it also applies changes whose payment hook was missed
    assert early["changes_expire"] == 2 and "licence_reminder" not in early and "balance_ladder" not in early
    assert late["licence_reminder"] == 0 and late["balance_ladder"] == 0
    json.dumps(late)  # what the Demo Lab's "run now" and `tick` print


def run_pass(at):
    with frozen(at):
        return scheduler.run_due()


@pytest.mark.django_db
def test_a_job_whose_sql_fails_cannot_spoil_the_rest_of_the_pass(homes):
    def broken():
        with connection.cursor() as cur:
            cur.execute("SELECT * FROM no_such_table")

    jobs = [("broken", 0, broken), ("things", 0, lambda: ["a", "b"]), ("outbox", 0, scheduler._outbox)]
    with mock.patch.object(scheduler, "JOBS", jobs):
        results = scheduler.run_due()
    assert results["broken"].startswith("error:") and results["things"] == 2 and results["outbox"] == 0
    assert JobRun.objects.get(key="broken").last_ok is False and JobRun.objects.get(key="outbox").last_ok


# ---------- USSD never waits on Daraja ----------


@pytest.mark.django_db
def test_ussd_answers_at_once_and_the_m_pesa_prompt_follows_the_screen(
    homes, settings, django_capture_on_commit_callbacks
):
    settings.PAYMENTS_INLINE = False  # production: no Daraja call inside the USSD request
    new = "+254799000222"
    with django_capture_on_commit_callbacks() as callbacks:
        done = ussd("1*6*2*1*1*1*5*1", phone=new)  # anywhere, tomorrow, 1 night, 1 guest, first home, no breakfast
    b = Booking.objects.get(guest__phone=new)
    assert done == f"END Holding {b.unit.name} ({b.ref}). Check your phone for the M-Pesa prompt of {kes(b.total)}."
    assert not Payment.objects.filter(booking=b).exists()  # the screen went back first
    with (
        mock.patch.object(deferred._executor, "submit", side_effect=lambda fn, *args: fn(*args)),
        mock.patch("apps.comms.deferred.close_old_connections"),
    ):
        for callback in callbacks:
            callback()
    prompt = Payment.objects.get(booking=b)
    assert (prompt.method, prompt.status, prompt.amount, prompt.phone) == ("mpesa", "pending", b.total, new)


@pytest.mark.django_db
def test_a_prompt_that_cannot_start_after_the_screen_is_explained_by_sms(homes):
    sw = make_user("+254799000333", name="Baraka", lang="sw")
    with mock.patch("apps.payments.providers.SimulatedMpesa.request", side_effect=PaymentError("M-Pesa is busy")):
        done = ussd("1*6*2*1*1*1*5*1", phone=sw.phone)
    b = Booking.objects.get(guest=sw)
    assert done == f"END Tumekuwekea {b.unit.name} ({b.ref}). Angalia simu yako upate ombi la M-Pesa la {kes(b.total)}."
    assert bodies(sw.phone, kind="pay_prompt_failed") == [
        f"Hatukuweza kutuma ombi la M-Pesa kwa {b.ref} (M-Pesa is busy). Jibu PAY kujaribu tena, au lipa kwa kadi "
        f"hapa: {bookings.trip_link(b)}"
    ]


@pytest.mark.django_db
def test_my_booking_on_ussd_shows_and_sends_no_wifi_before_the_48_hour_reveal(homes, wanjiru):
    b = stay(homes["Blue Reef Apartment"], wanjiru, days(20), days(22))
    before = last_id()
    screens = [ussd("3"), ussd("3*1")]  # My booking, then "Resend check-in info"
    sent = bodies(KE_GUEST, before)
    assert sent and all(m.startswith("Booked! Blue Reef Apartment") for m in sent)  # the confirmation again
    for text in screens + sent:
        assert b.unit.wifi_password not in text and b.unit.directions not in text


def walk(phone, lang, *, wide):
    """Every USSD screen a caller can reach, posted the way Africa's Talking does: all options on the first `wide`
    levels, then the first and last option (and More) of deeper menus, a typed answer where one is asked for, and a
    wrong key on every menu. flowkit.ussd checks each screen: 160 characters with CON/END, no option cut off."""
    screens, queue = {}, [""]
    while queue and len(screens) < 400:
        chain = queue.pop(0)
        if chain in screens:
            continue
        User.objects.filter(phone=phone).update(lang=lang)  # the Language menu is walked too
        screens[chain] = screen = ussd(chain, phone=phone, session=f"walk-{len(screens)}")
        if screen.startswith("END "):
            continue
        nums, depth = options(screen), chain.count("*") + 1 if chain else 0
        if nums:
            ussd(f"{chain}*77" if chain else "77", phone=phone)  # a key that isn't on the menu
            picks = nums if depth < wide else list(dict.fromkeys([nums[0], *[n for n in nums if n == "98"], nums[-1]]))
        else:
            picks = [typed_answer(screen)]
        queue += [f"{chain}*{p}" if chain else p for p in picks]
    return screens


def typed_answer(screen):
    if "DDMM" in screen or "SSMM" in screen:
        return ddmm(days(9))
    if "message" in screen:  # Amina's broadcast
        return "Karibu"
    allowed = re.search(r"\((\d+)-\d+\)", screen)  # nights, guests, people, discount %
    return allowed[1] if allowed else "1"


@pytest.mark.django_db
def test_every_ussd_screen_fits_160_characters_for_guests_amina_and_staff(homes, wanjiru, host):
    b = stay(homes["Blue Reef Apartment"], wanjiru, days(0), days(3), adults=2, checked_in=True)
    bookings.set_breakfast(b, "swahili", people=2, channel="web")
    bookings.add_addon(b, "late_checkout", channel="web")  # a request waiting for Amina
    stay(homes["Diani Palm Suite"], with_id(make_user("+254733200020", name="Otieno Arrives")), days(0), days(2))
    cleaner = make_user("+254700000011", name="Fatuma Ali", role="cleaner", lang="sw")
    Task.objects.create(title="Fresh towels for Blue Reef", unit=b.unit, assignee=cleaner)
    baraka = make_user("+254799000444", name="Baraka", lang="sw")
    ends = []
    for phone, lang, wide in ((baraka.phone, "sw", 1), (KE_GUEST, "en", 1), (HOST, "en", 2), (cleaner.phone, "sw", 2)):
        screens = walk(phone, lang, wide=wide)
        assert len(screens) > 8, phone
        ends += [s for s in screens.values() if s.startswith("END ")]
    assert any(e.startswith("END Tumekuwekea ") and "ombi la M-Pesa" in e for e in ends)  # a Kiswahili booking
    assert any(e.startswith("END Logged #") for e in ends) and any("Task #" in e for e in ends)


# ---------- SMS: what Africa's Talking answers ----------


def at_answer(code, status):
    recipient = {"number": KE_GUEST, "status": status, "statusCode": code, "messageId": f"ATXid_{code}", "cost": "0"}
    return {"SMSMessageData": {"Message": "Sent to 0/1", "Recipients": [recipient]}}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("code", "status", "reason"),
    [
        (402, "InvalidSenderId", "Sender ID not registered with this network (402 InvalidSenderId)"),
        (404, "UnsupportedNumberType", "This number can't receive SMS (404 UnsupportedNumberType)"),
    ],
)
def test_a_message_africas_talking_cannot_deliver_fails_at_once_and_is_never_retried(
    settings, homes, wanjiru, code, status, reason
):
    settings.AT_API_KEY = "live-key"
    m = messaging.send(KE_GUEST, "Your door code is 4821")
    with mock.patch("apps.comms.at._post", return_value=at_answer(code, status)) as post:
        messaging.dispatch(m.pk)
        with frozen(timezone.now() + timedelta(hours=1)):
            assert messaging.dispatch_pending() == 0
    m.refresh_from_db()
    assert (m.status, m.failure_reason, m.attempts, m.next_attempt_at) == ("failed", reason, 1, None)
    assert post.call_count == 1


@pytest.mark.django_db
def test_a_guest_who_blocked_our_sms_is_marked_opted_out_and_start_brings_them_back(settings, homes, wanjiru):
    settings.AT_API_KEY = "live-key"
    with mock.patch("apps.comms.at._post", return_value=at_answer(406, "UserInBlacklist")):
        m = messaging.send(KE_GUEST, "Your booking is confirmed")
        messaging.dispatch(m.pk)
        wanjiru.refresh_from_db()
        opted_out = wanjiru.sms_opt_out_at
        messaging.dispatch(messaging.send(KE_GUEST, "Your door code is 4821").pk)
    m.refresh_from_db()
    assert m.status == "failed" and m.failure_reason.endswith("text START to opt back in (406 UserInBlacklist)")
    wanjiru.refresh_from_db()
    assert opted_out and wanjiru.sms_opt_out_at == opted_out  # the first refusal is the one on record
    assert Activity.objects.filter(kind="guest", phone=KE_GUEST, title__contains="406 UserInBlacklist").count() == 1
    assert messaging.send(KE_GUEST, "10% off", marketing=True) is None  # no promotions any more
    assert sms("START") == ["You're subscribed to offers from Amina Stays. Reply STOP any time."]
    wanjiru.refresh_from_db()
    assert wanjiru.sms_opt_out_at is None and wanjiru.marketing_opt_in


@pytest.mark.django_db
def test_no_credit_alerts_amina_once_keeps_booking_messages_and_drops_promotions(settings, homes, wanjiru):
    settings.AT_API_KEY = "live-key"
    t0 = timezone.now()
    code_sms = messaging.send(KE_GUEST, "Your door code is 4821")
    promo = messaging.send(KE_GUEST, "10% off this weekend", marketing=True)
    old = messaging.send(KE_GUEST, "Welcome!")
    with mock.patch("apps.comms.at._post", return_value=at_answer(405, "InsufficientBalance")):
        with frozen(t0 + timedelta(minutes=1)):
            assert messaging.dispatch_pending() == 3
        assert Alert.objects.filter(kind="sms").count() == 1  # three refusals, one alert that day
        with frozen(t0 + timedelta(hours=25)):
            messaging.dispatch(old.pk)  # still no credit a day later: it gives up
    assert Alert.objects.filter(kind="sms").count() == 2  # ...and the next day gets its own alert
    code_sms.refresh_from_db(), promo.refresh_from_db(), old.refresh_from_db()
    assert (code_sms.status, code_sms.attempts) == ("queued", 0)  # waiting for a top-up uses up no retries
    assert code_sms.next_attempt_at == t0 + timedelta(minutes=31) and "waiting for a top-up" in code_sms.failure_reason
    assert promo.status == "failed" and promo.failure_reason.endswith("promotions are not retried")
    assert old.status == "failed" and old.failure_reason.endswith("for a whole day - not sent")
    alert = Alert.objects.filter(kind="sms").first()
    assert alert.severity == "high" and "Top up" in alert.summary and not bodies(HOST)  # Amina's SMS couldn't go
    with mock.patch("apps.comms.at._post", return_value=at_answer(101, "Success")):  # topped up
        with frozen(t0 + timedelta(minutes=20)):
            assert messaging.dispatch_pending() == 0
        with frozen(t0 + timedelta(minutes=31)):
            assert messaging.dispatch_pending() == 1
    code_sms.refresh_from_db()
    assert (code_sms.status, code_sms.failure_reason, code_sms.attempts) == ("sent", "", 1)


@pytest.mark.django_db
def test_gateway_and_network_errors_retry_after_one_then_five_minutes_then_stay_failed(settings, homes, wanjiru):
    settings.AT_API_KEY = "live-key"
    t0 = timezone.now()
    m = messaging.send(KE_GUEST, "Your door code is 4821")
    with mock.patch("apps.comms.at._post", return_value=at_answer(500, "InternalServerError")):
        with frozen(t0 + timedelta(seconds=30)):
            assert messaging.dispatch_pending() == 1
        with frozen(t0 + timedelta(seconds=80)):
            assert messaging.dispatch_pending() == 0  # waits out its minute
    m.refresh_from_db()
    assert (m.status, m.attempts, m.next_attempt_at) == ("queued", 1, t0 + timedelta(seconds=90))
    assert m.failure_reason == "InternalServerError (500)"
    with mock.patch("apps.comms.at._post", side_effect=ATError("network error: timeout")):
        with frozen(t0 + timedelta(seconds=90)):
            assert messaging.dispatch_pending() == 1
    m.refresh_from_db()
    assert (m.status, m.attempts, m.next_attempt_at) == ("queued", 2, t0 + timedelta(minutes=6, seconds=30))
    with mock.patch("apps.comms.at._post", return_value=at_answer(407, "CouldNotRoute")):
        with frozen(t0 + timedelta(minutes=6, seconds=30)):
            assert messaging.dispatch_pending() == 1
    m.refresh_from_db()
    assert (m.status, m.attempts, m.next_attempt_at) == ("failed", messaging.MAX_ATTEMPTS, None)
    assert m.failure_reason == "CouldNotRoute (407)"
    with frozen(t0 + timedelta(hours=3)):
        assert messaging.dispatch_pending() == 0  # used up: never sent again


@pytest.mark.django_db
def test_without_a_sender_id_sms_go_out_from_the_two_way_shortcode(settings, homes, wanjiru):
    settings.AT_API_KEY = "live-key"
    senders = []
    with mock.patch("apps.comms.at._post", return_value=at_answer(101, "Success")) as post:
        for sender_id, shortcode in (("", "22384"), ("AMINASTAYS", "22384"), ("", "")):
            settings.AT_SENDER_ID, settings.AT_SMS_NUMBER = sender_id, shortcode
            messaging.dispatch(messaging.send(KE_GUEST, "Your login code is 482113").pk)
            senders.append(post.call_args.kwargs["data"].get("from"))
    assert senders == ["22384", "AMINASTAYS", None]  # None: AT's default sender, which reaches Airtel only


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("answer", "status"),
    [
        ({"messageId": "wamid.1", "status": "SENT"}, "sent"),
        ({"messageId": "wamid.2", "status": "DELIVERED"}, "sent"),
        ({"status": "FAILED", "errorMessage": "Outside the 24 hour window"}, "queued"),
        ({"messageId": "wamid.4", "status": "DELETED"}, "queued"),
    ],
)
def test_a_whatsapp_message_is_sent_only_when_africas_talking_took_it(settings, homes, wanjiru, answer, status):
    settings.AT_API_KEY, settings.AT_WHATSAPP_NUMBER = "live-key", "+254711000222"
    settings.AT_USERNAME, settings.AT_SANDBOX = "aminastays", False  # WhatsApp has no sandbox
    m = messaging.send(KE_GUEST, "Your door code is 4821", channel="whatsapp")
    with mock.patch("apps.comms.at._post", return_value=answer):
        messaging.dispatch(m.pk)
    m.refresh_from_db()
    assert (m.status, m.provider_status) == (status, answer["status"])
    if status == "queued":  # a failed send: retried like any other, then left failed
        assert m.attempts == 1 and m.next_attempt_at and answer["status"] in m.failure_reason


# ---------- inbound SMS: Africa's Talking retries webhooks ----------


@pytest.mark.django_db
def test_a_repeated_incoming_sms_webhook_is_answered_once(client, homes):
    form = {"from": KE_GUEST, "to": "22384", "text": "PRICES", "id": "ATXid_rep1"}
    assert client.post("/at/sms/incoming", form).status_code == 200
    assert client.post("/at/sms/incoming", form).status_code == 200  # AT thought it timed out
    assert Message.objects.filter(direction="in").count() == 1 and len(bodies(KE_GUEST)) == 1
    assert Thread.objects.get(phone=KE_GUEST).unread == 1
    client.post("/at/sms/incoming", {**form, "id": "ATXid_rep2"})  # the same words in a new message are new
    assert Message.objects.filter(direction="in").count() == 2 and len(bodies(KE_GUEST)) == 2


@pytest.mark.django_db
def test_the_database_keeps_one_inbound_row_per_provider_id(homes, wanjiru):
    first = messaging.record_inbound(KE_GUEST, "hi", provider_id="ATXid_db1")
    with pytest.raises(IntegrityError), transaction.atomic():
        Message.objects.create(thread=first.thread, phone=KE_GUEST, direction="in", body="hi", provider_id="ATXid_db1")
    Message.objects.create(thread=first.thread, phone=KE_GUEST, direction="out", body="x", provider_id="ATXid_db1")
    messaging.record_inbound(KE_GUEST, "a USSD callback request")
    messaging.record_inbound(KE_GUEST, "another one")  # no provider id: never a repeat
    checks = iter([lambda provider_id: None, messaging._first_inbound])  # two deliveries racing past the check
    with mock.patch.object(messaging, "_first_inbound", side_effect=lambda pid: next(checks)(pid)):
        again = messaging.record_inbound(KE_GUEST, "hi", provider_id="ATXid_db1")
    assert again.pk == first.pk and again.duplicate
    assert Message.objects.filter(direction="in").count() == 3


# ---------- voice: outbound calls nobody answers ----------


def call_over(session, phone, request_id, state="NotAnswered", cause="NO_ANSWER"):
    return process_voice(
        {
            "sessionId": session,
            "isActive": "0",
            "direction": "Outbound",
            "destinationNumber": phone,
            "clientRequestId": request_id,
            "callSessionState": state,
            "hangupCause": cause,
            "durationInSeconds": "0",
        }
    )


@pytest.mark.django_db
def test_an_unanswered_welcome_call_becomes_one_welcome_sms(homes, wanjiru):
    b = stay(homes["Blue Reef Apartment"], wanjiru, days(0), days(2), checked_in=True)
    queued = {"entries": [{"phoneNumber": KE_GUEST, "status": "Queued", "sessionId": "ATVId_w1"}]}
    with mock.patch("apps.comms.at.voice_call", return_value=queued):
        ivr.place_welcome_call(b)
    before = last_id()
    assert call_over("ATVId_w1", KE_GUEST, f"welcome-{b.ref}") == ""
    call_over("ATVId_w1", KE_GUEST, f"welcome-{b.ref}")  # the final notification, repeated
    call_over("ATVId_w2", KE_GUEST, f"welcome-{b.ref}")  # a second unanswered call for the same stay
    [fallback] = bodies(KE_GUEST, before)
    assert fallback.startswith("Karibu Wanjiru! We called to welcome you to Blue Reef Apartment - sorry we missed you.")
    assert bookings.trip_link(b) in fallback and b.events.filter(kind="welcome_call").exists()

    otieno = with_id(make_user("+254733200030", name="Otieno"))
    other = stay(homes["Old Town Loft"], otieno, days(0), days(1), checked_in=True)
    call_over("ATVId_w3", otieno.phone, f"welcome-{other.ref}", state="Completed", cause="NORMAL_CLEARING")
    assert not bodies(otieno.phone, kind="welcome_call_missed")  # answered
    call_over("ATVId_w4", otieno.phone, f"welcome-{other.ref}", state="Completed", cause="USER_BUSY")
    assert bodies(otieno.phone, kind="welcome_call_missed")  # busy, and known only by its clientRequestId


@pytest.mark.django_db
def test_an_sos_call_nobody_answers_rings_the_next_person_at_once(homes, host, wanjiru, site):
    site.backup_phone = BACKUP
    site.save()
    rung = []

    def voice_call(to, client_request_id=""):
        rung.append(to)
        return {"entries": [{"phoneNumber": to, "status": "Queued", "sessionId": f"ATVId_sos{len(rung)}"}]}

    with mock.patch("apps.comms.at.voice_call", side_effect=voice_call):
        alert = escalate(KE_GUEST, "sms")
        call_over("ATVId_sos1", HOST, f"alert-{alert.pk}")
        call_over("ATVId_sos1", HOST, f"alert-{alert.pk}")  # repeated notification: no extra call
        alert.refresh_from_db()
        assert rung == [HOST, BACKUP] and alert.calls_made == 2  # no 3-minute wait
        with frozen(alert.last_call_at + timedelta(minutes=2)):
            followups()  # the timer counts from the latest call
        assert rung == [HOST, BACKUP]
        call_over("ATVId_sos2", BACKUP, f"alert-{alert.pk}", state="Completed", cause="USER_BUSY")
        call_over("ATVId_sos3", HOST, f"alert-{alert.pk}")  # three calls is the whole ladder
    alert.refresh_from_db()
    assert rung == [HOST, BACKUP, HOST] and alert.calls_made == 3
    assert Activity.objects.filter(kind="alert", title__contains="call not answered (NotAnswered)").exists()


@pytest.mark.django_db
def test_an_unanswered_call_for_an_acknowledged_sos_rings_nobody(homes, host, wanjiru):
    queued = {"entries": [{"phoneNumber": HOST, "status": "Queued", "sessionId": "ATVId_ack"}]}
    with mock.patch("apps.comms.at.voice_call", return_value=queued) as call:
        alert = escalate(KE_GUEST, "sms")
        sms("OK", phone=HOST)  # Amina saw the SMS and acknowledged it
        call_over("ATVId_ack", HOST, f"alert-{alert.pk}")
    assert call.call_count == 1


# ---------- the channels page ----------


@pytest.mark.django_db
def test_the_channels_page_lists_the_paybill_callbacks(host_api, settings):
    settings.PUBLIC_URL = "https://amina.example"

    def mpesa():
        return next(p for p in host_api.get("/api/host/channels").json()["products"] if p["key"] == "payments")

    callbacks = mpesa()["callbacks"]
    assert {"AT checkout", "Daraja"} <= set(callbacks)
    assert callbacks["Paybill validation"].startswith("https://amina.example/api/payments/daraja/c2b/validation/")
    assert callbacks["Paybill confirmation"].startswith("https://amina.example/api/payments/daraja/c2b/confirmation/")
    settings.MPESA_PROVIDER = "daraja"
    assert mpesa()["detail"] == "daraja - run manage.py register_c2b once"
    settings.AT_WEBHOOK_SECRET, settings.DARAJA_CALLBACK_SECRET = "at-secret", "d4r4j4"
    callbacks = mpesa()["callbacks"]  # the M-Pesa prompt callback shares the Paybill ones' secret
    assert callbacks["Daraja"] == "https://amina.example/api/payments/daraja/callback/d4r4j4"
    assert callbacks["Paybill confirmation"].endswith("/confirmation/d4r4j4")


@pytest.mark.django_db
@pytest.mark.parametrize("key", ["UserData", "userData"])  # AT's docs spell it both ways
def test_the_channels_page_shows_the_africas_talking_balance(host_api, settings, key):
    settings.AT_API_KEY = "live-key"
    with mock.patch("apps.comms.at.httpx.Client") as client:
        client.return_value.__enter__.return_value.get.return_value.json.return_value = {key: {"balance": "KES 1,250"}}
        assert host_api.get("/api/host/channels?balance=1").json()["balance"] == "KES 1,250"
