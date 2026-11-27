"""Periodic jobs. `manage.py run_scheduler` loops every SCHEDULER_INTERVAL_SECONDS; `manage.py tick`
runs one pass (cron-friendly). Interval jobs remember their last run in JobRun; daily jobs claim a
per-day OnceMarker so a restart never repeats the morning digest."""

import contextlib
import logging
import time
import traceback
from datetime import timedelta

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from .models import JobRun, OnceMarker

log = logging.getLogger("amina.scheduler")


def _expire_holds():
    from apps.bookings.services import expire_stale_holds

    return len(expire_stale_holds())


def _release_codes():
    from apps.bookings.models import Booking
    from apps.bookings.services import release_code
    from apps.core.models import SiteSettings
    from apps.core.utils import at_local, today
    from apps.safety.services import balance_unpaid_on_arrival

    s, t, now = SiteSettings.load(), today(), timezone.now()
    released = 0
    for b in Booking.objects.filter(status="confirmed", check_in__lte=t, check_out__gt=t):
        if b.check_in < t or now >= at_local(t, s.code_release_time):
            outcome = release_code(b)  # "too_early" (not check-in day yet) simply waits for its day
            if outcome == "waiting_balance":
                balance_unpaid_on_arrival(b)
            released += outcome == "released"
    return released


def _auto_checkout():
    from apps.bookings.models import Booking
    from apps.bookings.services import check_out, effective_checkout_time
    from apps.core.utils import at_local, today

    t, now, n = today(), timezone.now(), 0
    for b in Booking.objects.filter(status="checked_in", check_out__lte=t):
        if b.check_out < t or now >= at_local(b.check_out, effective_checkout_time(b)) + timedelta(minutes=30):
            check_out(b, by="system", auto=True)
            n += 1
    return n


def _reviews():
    from apps.bookings.models import Booking
    from apps.core.models import SiteSettings
    from apps.reviews.services import request_review

    s = SiteSettings.load()
    h = timezone.localtime().hour
    if h >= s.quiet_hours_start or h < s.quiet_hours_end:
        return 0
    now = timezone.now()
    due = Booking.objects.filter(
        status="completed",
        review__isnull=True,
        checked_out_at__lte=now - timedelta(minutes=s.review_delay_minutes),
        checked_out_at__gte=now - timedelta(days=7),
    ).exclude(channel__in=("airbnb", "booking_com"))
    return sum(request_review(b) for b in due.select_related("guest", "unit"))


def _outbox():
    from apps.messaging.services import dispatch_pending

    return dispatch_pending()


def _automations():
    from apps.messaging.automations import run_automations

    return run_automations()


def _followups():
    from apps.safety.services import followups

    followups()


def _reconcile():
    from apps.payments.services import reconcile_pending

    reconcile_pending()


def _ical():
    from apps.properties.services import sync_all_feeds

    return len(sync_all_feeds())


def _digest():
    from apps.operations.services import send_host_digest

    send_host_digest()


def _gate():
    from apps.operations.services import send_gate_list

    return send_gate_list()


def _kitchen():
    from apps.operations.services import send_kitchen_sheet

    return send_kitchen_sheet()


def _retention():
    from apps.accounts.services import purge_expired_ids

    return purge_expired_ids()


def _levy_reminder():
    from apps.bookings.services import notify_host
    from apps.core.utils import kes, today
    from apps.insights.services import tra_return

    t = today()
    if t.day != 5:
        return 0
    prev = t.replace(day=1) - timedelta(days=1)
    r = tra_return(prev.year, prev.month)
    notify_host(
        f"Reminder: Tourism Levy for {prev:%B} ({kes(r['tourism_levy'])}) and the TRA monthly return are due by the 10th. Both are ready in the console under Compliance."
    )
    return 1


def _balance_ladder():
    from apps.messaging.automations import run_balance_ladder

    return run_balance_ladder()


def _licence_reminder():
    from apps.safety.services import licence_reminder

    return licence_reminder()


def _changes_expire():
    from apps.bookings import services as bookings

    expire = getattr(bookings, "expire_stale_changes", None)  # date changes / extensions (bookings app)
    return expire() if expire else 0


def _service_notices():
    from apps.notices.services import run

    return run()


def _support_escalation():
    from apps.support.services import escalate_overdue

    return escalate_overdue()


def _rewards():
    from apps.rewards.services import run

    return run()


# (key, every-N-seconds | "daily@HH:MM", function)
JOBS = [
    ("expire_holds", 0, _expire_holds),
    ("outbox", 0, _outbox),
    ("release_codes", 0, _release_codes),
    ("automations", 0, _automations),
    ("auto_checkout", 0, _auto_checkout),
    ("reviews", 0, _reviews),
    ("alert_followups", 0, _followups),
    ("changes_expire", 0, _changes_expire),
    ("service_notices", 0, _service_notices),
    ("support_escalation", 60, _support_escalation),
    ("rewards", 60, _rewards),
    ("payments_reconcile", 120, _reconcile),
    ("ical_sync", 900, _ical),
    ("host_digest", "daily@07:00", _digest),
    ("gate_list", "daily@07:30", _gate),
    ("kitchen_sheet", "daily@18:00", _kitchen),
    ("levy_reminder", "daily@09:00", _levy_reminder),
    ("licence_reminder", "daily@09:00", _licence_reminder),
    ("balance_ladder", "daily@10:00", _balance_ladder),
    ("retention", "daily@03:00", _retention),
]


def _due(key, schedule, now):
    if isinstance(schedule, str) and schedule.startswith("daily@"):
        hh, mm = (int(x) for x in schedule[6:].split(":"))
        local = timezone.localtime(now)
        if (local.hour, local.minute) < (hh, mm):
            return False
        return not OnceMarker.seen(f"daily:{key}:{local.date()}")
    run = JobRun.objects.filter(key=key).first()
    return run is None or run.last_run_at is None or (now - run.last_run_at).total_seconds() >= schedule


def run_due(only=None):
    """One scheduler pass. A Postgres advisory lock makes overlapping schedulers (two terminals,
    two containers) skip instead of double-running jobs."""
    with connection.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(%s)", [ADVISORY_LOCK_ID])
        if not cur.fetchone()[0]:
            log.info("another scheduler holds the lock - skipping this pass")
            return {}
    try:
        return _run_due(only)
    finally:
        with connection.cursor() as cur:
            cur.execute("SELECT pg_advisory_unlock(%s)", [ADVISORY_LOCK_ID])


ADVISORY_LOCK_ID = 4_206_2026


def _contained():
    """Inside an outer transaction (an atomic request, a test) each job gets a savepoint, so one whose SQL fails
    can't poison the rest of the pass or the advisory unlock. The scheduler loop itself runs in autocommit and keeps
    it: jobs make network calls (SMS, M-Pesa, iCal) that must not sit inside, or be rolled back with, a transaction."""
    return transaction.atomic() if connection.in_atomic_block else contextlib.nullcontext()


def _plain(result):
    """Job results go back as JSON (the Demo Lab's 'run now', `tick`): a count for a list of things done, text for
    anything else that isn't a plain value."""
    if result is None or isinstance(result, bool | int | float | str):
        return result
    if isinstance(result, list | tuple | set):
        return len(result)
    if isinstance(result, dict):
        return {str(k): _plain(v) for k, v in result.items()}
    return str(result)


def _run_due(only=None):
    now = timezone.now()
    results = {}
    for key, schedule, fn in JOBS:
        if only and key not in only:
            continue
        if not only and not _due(key, schedule, now):
            continue
        if (
            isinstance(schedule, str)
            and not only
            and not OnceMarker.mark(f"daily:{key}:{timezone.localtime(now).date()}")
        ):
            continue
        run, _ = JobRun.objects.get_or_create(key=key)
        try:
            with _contained():
                results[key] = _plain(fn())
            run.last_ok, run.last_error = True, ""
        except Exception as e:
            log.error("job %s failed: %s", key, e)
            results[key] = f"error: {e}"
            run.last_ok, run.last_error = False, traceback.format_exc()[-2000:]
        run.last_run_at, run.run_count = timezone.now(), run.run_count + 1
        run.save()
    return results


def loop(interval=None, stop=None):
    interval = interval or settings.SCHEDULER_INTERVAL_SECONDS
    log.info("Scheduler running every %ss", interval)
    while not (stop and stop()):
        started = time.monotonic()
        try:
            from django.db import close_old_connections

            close_old_connections()
            done = {k: v for k, v in run_due().items() if v}
            if done:
                log.info("scheduler: %s", done)
        except Exception:
            log.exception("scheduler pass failed")
        time.sleep(max(1.0, interval - (time.monotonic() - started)))
