"""The scheduler: every job in core.scheduler.JOBS does its work at the right moment (and not before), runs once
per window, survives a failing neighbour and another scheduler, and the `tick` / `run_scheduler` commands work."""

import io
import signal
from datetime import timedelta
from unittest import mock

import pytest
from django.core.management import CommandError, call_command
from django.db import connections
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.services import set_identity
from apps.bookings import services as bookings
from apps.bookings.models import AccessCode, Booking, BookingGuest, Waitlist
from apps.core import scheduler
from apps.core.management.commands.seed_demo import Command as SeedDemo
from apps.core.management.commands.seed_demo import sample_ics
from apps.core.models import JobRun, OnceMarker, SiteSettings
from apps.core.utils import nice_date
from apps.messaging import services as messaging
from apps.messaging.automations import ensure_defaults
from apps.messaging.models import Conversation, Message
from apps.operations.models import Task
from apps.payments import services as payments
from apps.payments.models import Payment
from apps.properties.models import CalendarBlock, ICalFeed
from apps.reviews.models import Review
from apps.rewards import services as rewards
from apps.safety.models import Alert
from apps.safety.services import escalate

from .conftest import days
from .flowkit import KE_GUEST, bodies, build_catalogue, frozen, kenya, last_id, make_user, pay, sms, stay, with_id

HOST = "+254700000001"


@pytest.fixture
def homes(db):
    homes = build_catalogue()[1]
    ensure_defaults()
    return homes


@pytest.fixture
def wanjiru(db):
    return with_id(make_user(KE_GUEST, name="Wanjiru Kamau"))


def run(*jobs, at=None):
    """Force the given jobs (the Demo Lab's 'run now'), optionally at a frozen Kenya time."""
    if at is None:
        return scheduler.run_due(only=list(jobs))
    with frozen(at):
        return scheduler.run_due(only=list(jobs))


def due(at):
    """One normal scheduler pass at a frozen time."""
    with frozen(at):
        return scheduler.run_due()


def kinds(phone, after=0):
    return [m.kind for m in Message.objects.filter(phone=phone, direction="out", id__gt=after).order_by("id")]


# ---------- expire_holds ----------


@pytest.mark.django_db
def test_unpaid_holds_expire_the_dates_are_released_and_the_waitlist_hears(homes, wanjiru):
    loft = homes["Old Town Loft"]
    phone_hold = bookings.create_hold(unit=loft, guest=wanjiru, check_in=days(5), check_out=days(6), channel="ussd")
    payments.start_payment(phone_hold)
    waiting = make_user("+254733200001", name="Waiting")
    Waitlist.objects.create(guest=waiting, area=loft.area, check_in=days(5), check_out=days(6), guests=1)
    other = make_user("+447700900321", name="Web Guest")
    web_hold = bookings.create_hold(
        unit=homes["Diani Palm Suite"], guest=other, check_in=days(5), check_out=days(7), channel="web"
    )

    assert run("expire_holds", at=timezone.now() + timedelta(minutes=9)) == {"expire_holds": 0}
    assert run("expire_holds", at=timezone.now() + timedelta(minutes=11)) == {"expire_holds": 2}
    phone_hold.refresh_from_db()
    web_hold.refresh_from_db()
    assert phone_hold.status == web_hold.status == "expired"
    assert Payment.objects.get(booking=phone_hold).status == "expired"
    assert bodies(KE_GUEST, kind="hold_expired") == [
        f"We didn't receive payment in time, so Old Town Loft for {bookings.dates_text(days(5), days(6))} was released. Reply BOOK to try again."
    ]
    assert not bodies(other.phone, kind="hold_expired")  # the web checkout shows it on screen
    assert bodies(waiting.phone, kind="waitlist_offer")[0].startswith("Good news! Old Town Loft")
    assert Conversation.objects.get(phone=waiting.phone).state == "offer"
    assert run("expire_holds", at=timezone.now() + timedelta(minutes=30)) == {"expire_holds": 0}


# ---------- outbox ----------


@pytest.mark.django_db
def test_outbox_redispatches_queued_and_stuck_messages(homes, wanjiru, settings):
    settings.OUTBOX_MODE = "queue"  # nothing goes out until the scheduler picks it up
    fresh = messaging.send(KE_GUEST, "fresh")
    stuck = messaging.send(KE_GUEST, "stuck")
    given_up = messaging.send(KE_GUEST, "given up")
    Message.objects.filter(pk=stuck.pk).update(status="sending", attempts=1)
    Message.objects.filter(pk=given_up.pk).update(attempts=messaging.MAX_ATTEMPTS)  # used up its retries
    assert run("outbox", at=timezone.now() + timedelta(seconds=5)) == {"outbox": 0}  # under 20 s: a worker may have it
    assert run("outbox", at=timezone.now() + timedelta(minutes=3)) == {"outbox": 1}
    fresh.refresh_from_db()
    assert fresh.status == "logged" and fresh.attempts == 1 and fresh.sent_at  # dry run without an AT key
    assert Message.objects.get(pk=stuck.pk).status == "queued"  # a dead worker's message is put back…
    assert run("outbox", at=timezone.now() + timedelta(minutes=4)) == {"outbox": 1}
    assert Message.objects.get(pk=stuck.pk).status == "logged"  # …and sent on the next pass
    assert Message.objects.get(pk=given_up.pk).status == "queued"


@pytest.mark.django_db
def test_seeded_demo_people_never_get_real_sms(homes, settings):
    settings.OUTBOX_MODE, settings.AT_API_KEY = "queue", "live-key"
    make_user("+254700000011", name="Fatuma", role="cleaner", tags=["seed"])
    m = messaging.send("+254700000011", "New task")
    with mock.patch("apps.comms.at._post") as post:
        run("outbox", at=timezone.now() + timedelta(minutes=1))
    post.assert_not_called()
    m.refresh_from_db()
    assert m.status == "logged"


# ---------- release_codes ----------


@pytest.mark.django_db
def test_door_codes_go_out_at_the_release_time_on_arrival_day(homes, wanjiru):
    b = stay(homes["Blue Reef Apartment"], wanjiru, days(0), days(2), adults=2)
    later = stay(homes["Diani Palm Suite"], make_user("+254733200002", name="Later"), days(1), days(3))
    assert run("release_codes", at=kenya(days(0), "07:59")) == {"release_codes": 0}
    b.refresh_from_db()
    assert b.status == "confirmed" and not bodies(KE_GUEST, kind="checkin_code")
    before = last_id()
    assert run("release_codes", at=kenya(days(0), "08:00")) == {"release_codes": 1}
    b.refresh_from_db()
    code = AccessCode.objects.get(booking=b, revoked_at__isnull=True)
    assert b.status == "checked_in" and b.code_released_at and code.sent_at
    assert kinds(KE_GUEST, before) == ["checkin_code", "local_tips"]
    assert code.code in bodies(KE_GUEST, before)[0]
    assert run("release_codes", at=kenya(days(0), "09:00")) == {"release_codes": 0}  # nothing twice
    later.refresh_from_db()
    assert later.status == "confirmed"  # tomorrow's guest waits for tomorrow


@pytest.mark.django_db
def test_a_late_arrival_from_yesterday_still_gets_the_code_early_next_morning(homes, wanjiru):
    b = stay(homes["Blue Reef Apartment"], wanjiru, days(0), days(3))
    with frozen(kenya(days(1), "06:00")):
        assert scheduler.run_due(only=["release_codes"]) == {"release_codes": 1}
    b.refresh_from_db()
    assert b.status == "checked_in"


@pytest.mark.django_db
def test_an_unpaid_balance_holds_the_code_and_asks_once_then_releases(homes, wanjiru):
    b = stay(homes["Blue Reef Apartment"], wanjiru, days(0), days(2))
    bookings.add_addon(b, "airport_pickup", channel="web")  # added an extra, not paid yet
    b.refresh_from_db()
    assert b.balance_due > 0
    assert run("release_codes", at=kenya(days(0), "08:01")) == {"release_codes": 0}
    [waiting] = bodies(KE_GUEST, kind="code_waiting_balance")
    assert waiting.startswith("Your door code for Blue Reef Apartment is ready once the balance of KES ")
    prompt = Payment.objects.get(booking=b, status="pending")
    assert prompt.purpose == "balance" and prompt.amount == b.balance_due
    run("release_codes", at=kenya(days(0), "08:30"))
    assert (
        len(bodies(KE_GUEST, kind="code_waiting_balance")) == 1
        and Payment.objects.filter(status="pending").count() == 1
    )
    pay(b)
    assert run("release_codes", at=kenya(days(0), "08:31")) == {"release_codes": 1}
    assert bodies(KE_GUEST, kind="checkin_code")


@pytest.mark.django_db
def test_a_missing_id_holds_the_code_until_the_register_is_complete(homes):
    guest = make_user("+447700900101", name="Sarah Thompson", nationality="GB")
    b = stay(homes["Old Town Loft"], guest, days(0), days(1))
    run("release_codes", at=kenya(days(0), "08:05"))
    assert bodies(guest.phone, kind="code_waiting_id")
    assert not Payment.objects.filter(booking=b, status="pending").exists()  # no M-Pesa for a UK number
    set_identity(guest, id_type="passport", id_number="P1234567", consent=True)
    assert run("release_codes", at=kenya(days(0), "08:10")) == {"release_codes": 1}
    assert len(bodies(guest.phone, kind="code_waiting_id")) == 1 and bodies(guest.phone, kind="checkin_code")


@pytest.mark.django_db
def test_a_fresh_sim_swap_holds_the_code_and_alerts_amina(homes, host):
    swapped = with_id(make_user("+254722333999", name="Swapped Sim"))  # simulation: numbers ending 999 were swapped
    b = stay(homes["Old Town Loft"], swapped, days(0), days(1))
    assert run("release_codes", at=kenya(days(0), "08:05")) == {"release_codes": 0}
    b.refresh_from_db()
    assert b.status == "confirmed" and b.sim_swap_status == "Swapped"
    assert bodies(swapped.phone, kind="code_security_hold")[0].startswith(
        "For your security we need to confirm your number"
    )
    alert = Alert.objects.get(kind="security")
    assert alert.booking == b and "SIM swap detected" in alert.summary
    assert any(m.startswith("ALERT: SIM swap detected on +254722333999") for m in bodies(HOST, kind="alert"))
    run("release_codes", at=kenya(days(0), "08:30"))
    assert (
        Alert.objects.filter(kind="security").count() == 1
        and len(bodies(swapped.phone, kind="code_security_hold")) == 1
    )
    assert bookings.release_code(b, force=True) == "released"  # Amina called the guest and overrides


@pytest.mark.django_db
def test_a_queued_sim_swap_check_waits_for_africas_talking(homes, settings, client):
    settings.SIM_SWAP_PROVIDER, settings.AT_API_KEY = "africastalking", "live-key"
    g = with_id(make_user("+254722444555", name="Checked"))
    b = stay(homes["Old Town Loft"], g, days(0), days(1))
    queued = {"responses": [{"phoneNumber": g.phone, "requestId": "ATSwpid_9", "status": "Queued"}]}
    with mock.patch("apps.comms.at._post", return_value=queued):
        assert run("release_codes", at=kenya(days(0), "08:05")) == {"release_codes": 0}
    b.refresh_from_db()
    assert b.status == "confirmed" and b.sim_swap_status == "Queued"
    client.post(
        "/at/insights/simswap", {"requestId": "ATSwpid_9", "status": "NoSwapDate"}, content_type="application/json"
    )
    with mock.patch("apps.comms.at._post", return_value=queued):
        assert run("release_codes", at=kenya(days(0), "08:06")) == {"release_codes": 1}


# ---------- automations (the guest message timeline) ----------


@pytest.mark.django_db
def test_pre_arrival_goes_out_three_days_before_at_ten_once(homes, wanjiru):
    stay(homes["Blue Reef Apartment"], wanjiru, days(3), days(5))
    assert run("automations", at=kenya(days(0), "09:59")) == {"automations": 0}
    assert run("automations", at=kenya(days(0), "10:00")) == {"automations": 1}
    [pre] = bodies(KE_GUEST, kind="pre_arrival")
    assert pre.startswith("Hi Wanjiru! Blue Reef Apartment is ready for you on") and "BREAKFAST" in pre
    assert run("automations", at=kenya(days(0), "15:00")) == {"automations": 0}
    assert OnceMarker.seen(f"auto:pre_arrival:{Booking.objects.get().ref}")


@pytest.mark.django_db
def test_nothing_goes_out_in_quiet_hours(homes, wanjiru):
    stay(homes["Blue Reef Apartment"], wanjiru, days(3), days(5))
    assert run("automations", at=kenya(days(0), "21:30")) == {"automations": 0}
    assert run("automations", at=kenya(days(1), "07:30")) == {"automations": 0}
    assert not bodies(KE_GUEST, kind="pre_arrival")
    assert run("automations", at=kenya(days(1), "08:00")) == {"automations": 1}  # caught up in the morning


@pytest.mark.django_db
def test_day_before_balance_id_and_directions(homes):
    g = make_user("+254733200003", name="Otieno")  # no ID registered yet
    b = stay(homes["Diani Palm Suite"], g, days(10), days(12), plan="deposit")
    Booking.objects.filter(pk=b.pk).update(check_in=days(2), check_out=days(4))  # the stay has come closer
    assert run("automations", at=kenya(days(0), "11:00"))["automations"] == 2  # pre-arrival (catch-up) + ID request
    assert kinds(g.phone)[-2:] == ["pre_arrival", "id_request"]
    before = last_id()
    run("automations", at=kenya(days(1), "09:00"))
    assert kinds(g.phone, before) == ["balance_due"]
    prompt = Payment.objects.get(booking=b, status="pending")
    assert prompt.purpose == "balance" and prompt.amount == Booking.objects.get(pk=b.pk).balance_due
    run("automations", at=kenya(days(1), "15:59"))
    assert "directions" not in kinds(g.phone, before)
    run("automations", at=kenya(days(1), "16:00"))
    [directions] = bodies(g.phone, before, kind="directions")
    assert (
        directions.startswith(f"Karibu on {nice_date(days(2))}! Diani Palm Suite:") and "Wi-Fi: DianiPalm" in directions
    )


@pytest.mark.django_db
def test_disabled_automations_stay_quiet(homes, wanjiru):
    from apps.messaging.models import Automation

    Automation.objects.filter(key="pre_arrival").update(enabled=False)
    stay(homes["Blue Reef Apartment"], wanjiru, days(3), days(5))
    assert run("automations", at=kenya(days(0), "10:30")) == {"automations": 0}


@pytest.mark.django_db
def test_settled_in_mid_stay_and_checkout_reminders_during_the_stay(homes, wanjiru):
    stay(homes["Blue Reef Apartment"], wanjiru, days(0), days(5), checked_in=True)
    run("automations", at=kenya(days(0), "18:59"))
    assert "welcome_check" not in kinds(KE_GUEST)
    run("automations", at=kenya(days(0), "19:00"))
    assert bodies(KE_GUEST, kind="welcome_check") == [
        "Settled in at Blue Reef Apartment, Wanjiru? Reply 1 if all is good, or just tell us what you need."
    ]
    run("automations", at=kenya(days(2), "10:00"))
    [mid] = bodies(KE_GUEST, kind="mid_stay")
    assert (
        mid
        == "Hope you're enjoying Nyali! Fancy a mid-stay clean with fresh towels (KES 1,500)? Reply CLEAN. Anything else, just reply."
    )
    run("automations", at=kenya(days(4), "19:00"))
    [reminder] = bodies(KE_GUEST, kind="checkout_reminder")
    assert reminder.startswith("Checkout is tomorrow by 11am.") and "Reply LATE" in reminder
    assert kinds(KE_GUEST).count("welcome_check") == 1


@pytest.mark.django_db
def test_short_stays_get_no_mid_stay_offer(homes, wanjiru):
    stay(homes["Blue Reef Apartment"], wanjiru, days(0), days(3), checked_in=True)
    run("automations", at=kenya(days(2), "10:00"))
    assert "mid_stay" not in kinds(KE_GUEST)


@pytest.mark.django_db
def test_come_back_offer_three_weeks_later_only_to_opted_in_direct_guests(homes, wanjiru):
    wanjiru.marketing_opt_in = True
    wanjiru.save()
    b = stay(homes["Old Town Loft"], wanjiru, days(0), days(1), checked_in=True)
    bookings.check_out(b)
    ota = make_user("+447700900102", name="Airbnb Guest", marketing_opt_in=True)
    o = stay(homes["Nyali Breeze Studio"], ota, days(0), days(1), checked_in=True)
    Booking.objects.filter(pk=o.pk).update(channel="airbnb")
    bookings.check_out(o)
    stopped = make_user("+254733200004", name="Stopped", marketing_opt_in=True)
    s = stay(homes["Bamburi Family House"], stopped, days(0), days(2), checked_in=True)
    bookings.check_out(s)
    sms("STOP", phone=stopped.phone)
    Booking.objects.filter(pk=s.pk).update(check_out=days(1))

    run("automations", at=kenya(days(22), "09:59"))
    assert "rebook_offer" not in kinds(KE_GUEST)
    run("automations", at=kenya(days(22), "10:00"))
    [offer] = Message.objects.filter(phone=KE_GUEST, kind="rebook_offer")
    assert offer.is_marketing and offer.body.startswith("Missing the coast, Wanjiru? Book Old Town Loft again")
    assert "/stays/old-town-loft" in offer.body and offer.body.endswith("Reply STOP to opt out.")
    assert "rebook_offer" not in kinds(ota.phone) and "rebook_offer" not in kinds(stopped.phone)


# ---------- auto_checkout ----------


@pytest.mark.django_db
def test_guests_still_in_at_checkout_time_are_checked_out_half_an_hour_later(homes, wanjiru):
    cleaner = make_user("+254700000011", name="Fatuma", role="cleaner")
    b = stay(homes["Old Town Loft"], wanjiru, days(0), days(1), checked_in=True)
    assert run("auto_checkout", at=kenya(days(1), "11:29")) == {"auto_checkout": 0}
    assert run("auto_checkout", at=kenya(days(1), "11:30")) == {"auto_checkout": 1}
    b.refresh_from_db()
    assert b.status == "completed" and not AccessCode.objects.filter(booking=b, revoked_at__isnull=True).exists()
    assert bodies(KE_GUEST, kind="auto_checkout") == [
        f"Checkout time has passed, so your door code for {b.ref} is now deactivated. Thank you and safe travels!"
    ]
    assert Task.objects.get(type="turnover").assignee == cleaner


@pytest.mark.django_db
def test_an_approved_late_checkout_moves_the_automatic_checkout(homes, host, wanjiru):
    b = stay(homes["Old Town Loft"], wanjiru, days(0), days(1), checked_in=True)
    sms("LATE")
    from apps.bookings.models import BookingAddon

    sms(f"YES {BookingAddon.objects.get().pk}", phone=HOST)
    assert run("auto_checkout", at=kenya(days(1), "11:45")) == {"auto_checkout": 0}
    assert run("auto_checkout", at=kenya(days(1), "14:30")) == {"auto_checkout": 1}
    b.refresh_from_db()
    assert b.status == "completed"


# ---------- reviews ----------


@pytest.mark.django_db
def test_review_requests_an_hour_after_checkout_outside_quiet_hours(homes, wanjiru):
    b = stay(homes["Old Town Loft"], wanjiru, days(0), days(1), checked_in=True)
    bookings.check_out(b)
    Booking.objects.filter(pk=b.pk).update(checked_out_at=kenya(days(1), "10:30"))
    assert run("reviews", at=kenya(days(1), "11:29")) == {"reviews": 0}
    assert run("reviews", at=kenya(days(1), "11:31")) == {"reviews": 1}
    assert bodies(KE_GUEST, kind="review_request") == [
        "Asante for staying at Old Town Loft! How was it? Reply 1 (poor) to 5 (excellent)."
    ]
    assert Conversation.objects.get(phone=KE_GUEST).state == "review"
    assert run("reviews", at=kenya(days(1), "15:00")) == {"reviews": 0}
    sms("4")
    assert Review.objects.get(booking=b).rating == 4


@pytest.mark.django_db
def test_reviews_wait_out_quiet_hours_and_skip_ota_guests(homes, wanjiru):
    b = stay(homes["Old Town Loft"], wanjiru, days(0), days(1), checked_in=True)
    bookings.check_out(b)
    Booking.objects.filter(pk=b.pk).update(checked_out_at=kenya(days(1), "19:30"))
    assert run("reviews", at=kenya(days(1), "21:00")) == {"reviews": 0}
    assert run("reviews", at=kenya(days(2), "08:00")) == {"reviews": 1}
    ota = make_user("+447700900103", name="Booking Com")
    o = stay(homes["Nyali Breeze Studio"], ota, days(0), days(1), checked_in=True)
    bookings.check_out(o)
    Booking.objects.filter(pk=o.pk).update(channel="booking_com", checked_out_at=kenya(days(1), "10:00"))
    assert run("reviews", at=kenya(days(2), "09:00")) == {"reviews": 0}


# ---------- alert_followups ----------


@pytest.mark.django_db
def test_an_unacknowledged_sos_rings_the_backup_then_amina_three_calls_at_most(homes, host, wanjiru, site):
    site.backup_phone = "+254700000099"
    site.save()
    rung = []

    def voice_call(to, client_request_id=""):
        rung.append(to)
        return {"dry_run": True, "entries": [{"phoneNumber": to, "status": "NotConfigured"}]}

    with mock.patch("apps.comms.at.voice_call", side_effect=voice_call):
        alert = escalate(KE_GUEST, "sms")
        start = alert.last_call_at
        run("alert_followups", at=start + timedelta(minutes=2))
        run("alert_followups", at=start + timedelta(minutes=4))
        run("alert_followups", at=start + timedelta(minutes=8))
        run("alert_followups", at=start + timedelta(minutes=12))
        run("alert_followups", at=start + timedelta(minutes=30))
    assert rung == [HOST, "+254700000099", HOST]
    alert.refresh_from_db()
    assert alert.calls_made == 3


@pytest.mark.django_db
def test_an_acknowledged_sos_is_not_followed_up(homes, host, wanjiru):
    alert = escalate(KE_GUEST, "sms")
    sms("OK", phone=HOST)
    with mock.patch("apps.comms.at.voice_call") as call:
        run("alert_followups", at=alert.last_call_at + timedelta(minutes=10))
    call.assert_not_called()


# ---------- payments_reconcile ----------


@pytest.mark.django_db
def test_silent_m_pesa_prompts_are_failed_after_half_an_hour(homes, wanjiru):
    b = stay(homes["Old Town Loft"], wanjiru, days(3), days(4))
    bookings.add_addon(b, "airport_pickup", channel="web")
    payments.start_payment(b, method="mpesa", purpose="balance")
    p = Payment.objects.get(booking=b, status="pending")
    run("payments_reconcile", at=p.created_at + timedelta(minutes=20))
    p.refresh_from_db()
    assert p.status == "pending"
    run("payments_reconcile", at=p.created_at + timedelta(minutes=31))
    p.refresh_from_db()
    assert p.status == "failed" and p.failure_reason == "no confirmation received"


@pytest.mark.django_db
def test_daraja_prompts_are_queried_and_settled(homes, wanjiru, settings):
    held = bookings.create_hold(
        unit=homes["Old Town Loft"], guest=wanjiru, check_in=days(3), check_out=days(4), channel="sms"
    )
    payments.start_payment(held)
    other = bookings.create_hold(
        unit=homes["Nyali Breeze Studio"], guest=wanjiru, check_in=days(3), check_out=days(4), channel="sms"
    )
    payments.start_payment(other)
    ok, cancelled = Payment.objects.get(booking=held), Payment.objects.get(booking=other)
    Payment.objects.filter(pk=ok.pk).update(provider="daraja", transaction_id="ws_CO_ok")
    Payment.objects.filter(pk=cancelled.pk).update(provider="daraja", transaction_id="ws_CO_no")
    settings.MPESA_PROVIDER = "daraja"
    answers = {
        "ws_CO_ok": {"ResultCode": "0", "ResultDesc": "ok"},
        "ws_CO_no": {"ResultCode": "1032", "ResultDesc": "Request cancelled by user"},
    }
    with mock.patch("apps.payments.providers.DarajaMpesa.query", side_effect=lambda p: answers[p.transaction_id]):
        run("payments_reconcile", at=timezone.now() + timedelta(minutes=3))
    held.refresh_from_db()
    other.refresh_from_db()
    assert held.status == "confirmed" and Payment.objects.get(pk=ok.pk).status == "success"
    assert Payment.objects.get(pk=cancelled.pk).failure_reason == "cancelled on the phone"
    assert bodies(KE_GUEST, kind="payment_failed")[0].startswith(
        f"Your payment for {other.ref} didn't go through (cancelled on the phone)."
    )


# ---------- ical_sync ----------


class FakeCalendar:
    calls = []

    def __init__(self, *a, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, headers=None):
        FakeCalendar.calls.append(url)
        resp = mock.Mock(text=sample_ics(url.rsplit("/", 1)[-1].removesuffix(".ics")))
        resp.raise_for_status.return_value = None
        return resp


@pytest.mark.django_db
def test_ical_feeds_import_blocks_and_flag_a_double_booking(homes, host, wanjiru):
    unit = homes["Blue Reef Apartment"]
    clash = stay(unit, wanjiru, days(15), days(17))
    feed = ICalFeed.objects.create(
        unit=unit, name="Airbnb", url="https://www.airbnb.com/calendar/ical/blue-reef-apartment.ics"
    )
    FakeCalendar.calls = []
    with mock.patch("httpx.Client", FakeCalendar):
        assert run("ical_sync") == {"ical_sync": 1}
    assert FakeCalendar.calls == [feed.url]
    blocks = CalendarBlock.objects.filter(feed=feed).order_by("start_date")
    assert [(b.start_date, b.end_date) for b in blocks] == [(days(14), days(17)), (days(30), days(34))]
    alert = Alert.objects.get(kind="conflict")
    assert alert.severity == "critical" and alert.booking == clash
    assert any(
        m.startswith("ALERT: Double booking risk: Airbnb blocks Blue Reef Apartment")
        for m in bodies(HOST, kind="alert")
    )
    with mock.patch("httpx.Client", FakeCalendar):
        run("ical_sync")
    assert CalendarBlock.objects.filter(feed=feed).count() == 2 and Alert.objects.filter(kind="conflict").count() == 1


@pytest.mark.django_db
def test_an_unreachable_calendar_is_recorded_not_raised(homes):
    feed = ICalFeed.objects.create(
        unit=homes["Old Town Loft"], name="Booking.com", url="https://example.invalid/cal.ics"
    )
    with mock.patch("httpx.Client.get", side_effect=OSError("no route to host")):
        assert run("ical_sync") == {"ical_sync": 1}
    feed.refresh_from_db()
    assert feed.last_ok is False and "no route to host" in feed.last_error


@pytest.mark.django_db
@pytest.mark.parametrize("demo", [True, False])
def test_the_seeded_airbnb_calendar_auto_syncs_only_in_demo_mode(homes, settings, demo):
    """Its stand-in feed (/api/demo/ical/…) 404s without DEMO, so a non-demo seed imports it once and leaves it."""
    settings.DEMO = demo
    seed = SeedDemo()
    seed.units = homes
    seed.extras()
    feed = ICalFeed.objects.get(unit=homes["Mtwapa Creek Cottage"])
    assert feed.active is demo and feed.last_ok and CalendarBlock.objects.filter(feed=feed).count() == 2
    FakeCalendar.calls = []
    with mock.patch("httpx.Client", FakeCalendar):
        run("ical_sync")
    assert FakeCalendar.calls == ([feed.url] if demo else [])


SIM_PHONES = ["+254711000001", "+254711000002", "+254711000003", "+254711000004", "+254711000005"]


@pytest.mark.django_db
def test_simulator_guests_are_real_guests_each_at_another_point_of_a_stay(
    homes, host, settings, django_capture_on_commit_callbacks
):
    settings.SIMULATOR_GUESTS = SIM_PHONES
    out = io.StringIO()
    call_command("simulator_guests", stdout=out)
    assert out.getvalue().splitlines()[0] == "+254711000001 Asha Njeri: no booking"
    users = [User.objects.get(phone=p) for p in SIM_PHONES]
    assert [u.name for u in users] == ["Asha Njeri", "Kevin Mutua", "Grace Atieno", "Daniel Kiprono", "Halima Abdalla"]
    assert all(u.tags == [] and u.has_id for u in users)
    asha, kevin, grace, daniel, halima = users
    assert not asha.bookings.exists()
    [arriving] = kevin.bookings.all()
    assert arriving.status == "confirmed" and arriving.check_in > days(0) and arriving.balance_due == 0
    [staying] = grace.bookings.all()
    assert staying.status == "checked_in" and staying.check_in <= days(0) < staying.check_out
    [upcoming] = daniel.bookings.all()
    assert (
        upcoming.status == "confirmed"
        and upcoming.payment_plan == "deposit"
        and 0 < upcoming.amount_paid < upcoming.total
    )
    [stayed] = halima.bookings.all()
    assert stayed.status == "completed" and stayed.check_out < days(0) and halima.lang == "sw"
    assert rewards.balance(halima) >= rewards.program().redeem_points  # enough to redeem airtime

    # nothing that fell due before they existed goes out at once...
    before = last_id()
    run("automations", "balance_ladder", "reviews", "rewards", "release_codes", at=kenya(days(0), "12:00"))
    assert not Message.objects.filter(phone__in=SIM_PHONES, id__gt=before).exists()
    # ...but what they're sent really goes out through Africa's Talking, unlike the seeded people's messages
    accepted = {"recipients": [{"statusCode": 101, "messageId": "ATXid_1", "status": "Success"}]}
    with (
        mock.patch("apps.comms.at.send_sms", return_value=accepted) as at_sms,
        django_capture_on_commit_callbacks(execute=True),
    ):
        messaging.send(grace.phone, "Karibu!")
    at_sms.assert_called_once_with(grace.phone, "Karibu!")
    assert Message.objects.filter(phone=grace.phone).latest("id").status == "sent"

    call_command("simulator_guests", stdout=io.StringIO())  # again: nothing new
    assert Booking.objects.filter(guest__in=users).count() == 4
    seed = SeedDemo()
    assert seed.simulator_guests([HOST]) == [f"{HOST}: skipped - Amina's or a staff number, not a guest's"]


# ---------- the daily jobs ----------


@pytest.mark.django_db
def test_host_digest_every_morning_at_seven_once(homes, host, wanjiru):
    stay(homes["Blue Reef Apartment"], wanjiru, days(0), days(2), adults=2, checked_in=True)
    assert "host_digest" not in due(kenya(days(0), "06:59"))
    assert "host_digest" in due(kenya(days(0), "07:00"))
    [digest] = bodies(HOST, kind="host_digest")
    assert digest.startswith("Good morning Amina! Today: 1 arriving, 0 leaving, 1 in-house, 0 breakfasts")
    assert "host_digest" not in due(kenya(days(0), "07:20"))
    assert "host_digest" in due(kenya(days(1), "07:01"))
    assert len(bodies(HOST, kind="host_digest")) == 2


@pytest.mark.django_db
def test_gate_list_for_the_guard_at_half_past_seven(homes, wanjiru):
    guard = make_user("+254700000014", name="Hassan Omar", role="security", lang="sw")
    b = stay(homes["Blue Reef Apartment"], wanjiru, days(0), days(2), adults=2)
    bookings.set_eta(b, "15:00")
    assert "gate_list" not in due(kenya(days(0), "07:29"))
    assert due(kenya(days(0), "07:30"))["gate_list"] == 1
    [gate] = bodies(guard.phone, kind="gate_list")
    assert gate.startswith("Orodha ya geti ") and gate.endswith(
        "Blue Reef Apartment: Wanjiru Kamau, 2 guest(s), ETA 15:00"
    )
    assert due(kenya(days(1), "07:30"))["gate_list"] == 0  # no arrivals tomorrow


@pytest.mark.django_db
def test_kitchen_sheet_for_the_cook_at_six_pm(homes, wanjiru):
    cook = make_user("+254700000013", name="Mama Zawadi", role="cook", lang="sw")
    stay(homes["Blue Reef Apartment"], wanjiru, days(0), days(2), adults=2, checked_in=True)
    sms("BREAKFAST")
    sms("3 gluten free")
    assert "kitchen_sheet" not in due(kenya(days(0), "17:59"))
    assert due(kenya(days(0), "18:00"))["kitchen_sheet"] == 1
    [sheet] = bodies(cook.phone, kind="kitchen_sheet")
    assert sheet.endswith("08:00 Blue Reef Apartment: 2x Full English (GLUTEN)")
    assert due(kenya(days(0), "20:00")).get("kitchen_sheet") is None  # once a day


@pytest.mark.django_db
def test_kitchen_sheet_goes_to_amina_when_there_is_no_cook(homes, host, wanjiru):
    stay(homes["Blue Reef Apartment"], wanjiru, days(0), days(2), adults=2, checked_in=True)
    sms("BREAKFAST")
    sms("1")
    assert run("kitchen_sheet") == {"kitchen_sheet": 1}
    assert bodies(HOST, kind="kitchen_sheet")


def _fifth(day):
    return day.replace(day=5) if day.day <= 5 else (day.replace(day=28) + timedelta(days=8)).replace(day=5)


@pytest.mark.django_db
def test_levy_reminder_on_the_fifth_only(homes, host):
    fifth = _fifth(days(0))
    assert due(kenya(fifth - timedelta(days=1), "09:00"))["levy_reminder"] == 0
    assert due(kenya(fifth, "08:59")).get("levy_reminder") is None
    assert due(kenya(fifth, "09:00"))["levy_reminder"] == 1
    prev = fifth.replace(day=1) - timedelta(days=1)
    [reminder] = bodies(HOST, kind="host_notice")
    assert reminder.startswith(
        f"Reminder: Tourism Levy for {prev:%B} (KES 0) and the TRA monthly return are due by the 10th."
    )


@pytest.mark.django_db
def test_retention_erases_old_id_numbers_at_three_am(homes, wanjiru):
    site = SiteSettings.load()
    site.id_retention_days = 1
    site.save()
    b = stay(homes["Old Town Loft"], wanjiru, days(0), days(1), checked_in=True)
    bookings.check_out(b)
    from django.contrib.auth import get_user_model

    get_user_model().objects.filter(pk=wanjiru.pk).update(id_submitted_at=timezone.now() - timedelta(days=2))
    assert "retention" not in due(kenya(days(3), "02:59"))
    assert due(kenya(days(3), "03:00"))["retention"] == 2
    lead = BookingGuest.objects.get(booking=b)
    assert (
        lead.id_number_enc == "" and lead.id_last4 == "" and lead.full_name == "Wanjiru Kamau"
    )  # the register line stays
    wanjiru.refresh_from_db()
    assert not wanjiru.has_id


# ---------- once per window, failures, overlap ----------


@pytest.mark.django_db
def test_a_normal_pass_runs_interval_jobs_by_their_clock_and_records_them(homes):
    t0 = kenya(days(1), "12:00")
    first = due(t0)
    assert {"expire_holds", "outbox", "release_codes", "automations", "payments_reconcile", "ical_sync"} <= set(first)
    assert "payments_reconcile" not in due(t0 + timedelta(seconds=60))
    assert "payments_reconcile" in due(t0 + timedelta(seconds=121))
    assert "ical_sync" not in due(t0 + timedelta(minutes=10))
    assert "ical_sync" in due(t0 + timedelta(minutes=15, seconds=1))
    reconcile = JobRun.objects.get(key="payments_reconcile")  # ran at 0 s, 121 s, 10 min and 15 min
    assert (
        reconcile.run_count == 4
        and reconcile.last_ok
        and reconcile.last_run_at == t0 + timedelta(minutes=15, seconds=1)
    )
    assert JobRun.objects.get(key="ical_sync").run_count == 2
    assert JobRun.objects.get(key="outbox").run_count == 5  # every pass


@pytest.mark.django_db
def test_a_failing_job_is_recorded_and_the_others_still_run(homes, host):
    with mock.patch("apps.operations.services.send_host_digest", side_effect=RuntimeError("SMS gateway down")):
        results = due(kenya(days(1), "07:05"))
    assert results["host_digest"] == "error: SMS gateway down"
    assert "gate_list" not in results and results["expire_holds"] == 0
    failed = JobRun.objects.get(key="host_digest")
    assert failed.last_ok is False and "SMS gateway down" in failed.last_error
    assert JobRun.objects.get(key="outbox").last_ok is True
    assert "host_digest" not in due(kenya(days(1), "07:10"))  # the day's slot was used; tomorrow tries again


@pytest.mark.django_db(transaction=True)
def test_a_second_scheduler_skips_while_another_holds_the_lock(homes):
    other = connections.create_connection("default")
    try:
        with other.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", [scheduler.ADVISORY_LOCK_ID])
            assert cur.fetchone()[0], "the scheduler lock should be free between passes"
        assert scheduler.run_due() == {}
        assert not JobRun.objects.exists()
        with other.cursor() as cur:  # the other pass ends; a mere disconnect frees the lock only asynchronously
            cur.execute("SELECT pg_advisory_unlock(%s)", [scheduler.ADVISORY_LOCK_ID])
            assert cur.fetchone()[0]
    finally:
        other.close()
    assert "outbox" in scheduler.run_due()


# ---------- the management commands ----------


@pytest.mark.django_db
def test_tick_runs_one_pass_or_the_chosen_jobs(homes, host):
    out = io.StringIO()
    call_command("tick", "--job", "host_digest", "--job", "expire_holds", stdout=out)
    assert out.getvalue().splitlines() == ["expire_holds: 0", "host_digest: None"]
    assert bodies(HOST, kind="host_digest")
    out = io.StringIO()
    with frozen(kenya(days(1), "12:00")):
        call_command("tick", stdout=out)
    lines = out.getvalue().splitlines()
    assert "outbox: 1" in lines  # the digest queued above is sent now
    assert "release_codes: 0" in lines and "host_digest: None" in lines and "gate_list: 0" in lines
    assert "kitchen_sheet: 0" not in lines  # 18:00 hasn't come yet
    with pytest.raises(CommandError):
        call_command("tick", "--job", "make_coffee")


@pytest.mark.django_db
def test_run_scheduler_loops_until_told_to_stop(homes):
    handlers, sleeps = {}, []

    def fake_signal(sig, handler):
        handlers[sig] = handler

    def fake_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 2:
            handlers[signal.SIGTERM](signal.SIGTERM, None)  # systemd / docker stop

    with (
        mock.patch("apps.core.management.commands.run_scheduler.signal.signal", side_effect=fake_signal),
        mock.patch("apps.core.scheduler.time.sleep", side_effect=fake_sleep),
        mock.patch("django.db.close_old_connections"),
    ):
        call_command("run_scheduler", "--interval", "5")
    assert set(handlers) == {signal.SIGTERM, signal.SIGINT}
    assert len(sleeps) == 2 and all(1.0 <= s <= 5 for s in sleeps)
    assert JobRun.objects.get(key="outbox").run_count == 2


@pytest.mark.django_db
def test_the_loop_survives_a_broken_pass(homes, settings):
    settings.SCHEDULER_INTERVAL_SECONDS = 7
    passes = []

    def flaky():
        passes.append(1)
        if len(passes) == 1:
            raise RuntimeError("database restarting")
        return {"outbox": 0}

    with (
        mock.patch("apps.core.scheduler.run_due", side_effect=flaky),
        mock.patch("apps.core.scheduler.time.sleep") as sleep,
        mock.patch("django.db.close_old_connections"),
    ):
        scheduler.loop(stop=lambda: len(passes) >= 2)
    assert len(passes) == 2 and sleep.call_count == 2 and sleep.call_args.args[0] <= 7
