"""Slow provider calls that must not hold up a callback.

A USSD hop has to be answered within seconds (Airtel allows 15) while a Daraja STK push can take ~35 s (token
and push timeouts), so the push goes to a small worker pool once the response is on its way - the screen has
already told the guest to check their phone. Paystack's webhook is answered the same way, before its Verify
Transaction call. PAYMENTS_INLINE=True runs it inline instead (the default under tests, so flows stay deterministic).
"""

import logging
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.db import close_old_connections, transaction

log = logging.getLogger("amina.comms")
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="comms-pay")


def inline():
    flag = getattr(settings, "PAYMENTS_INLINE", None)
    return bool(getattr(settings, "TESTING", False) if flag is None else flag)


def after_response(fn, *args):
    """fn(*args) after the current transaction commits, off the request thread (or right now when inline)."""
    if inline():
        return fn(*args)
    transaction.on_commit(lambda: _executor.submit(_run, fn, *args), robust=True)
    return None


def _run(fn, *args):
    try:
        fn(*args)
    except Exception:
        log.exception("deferred %s%s failed", getattr(fn, "__name__", fn), args)
    finally:
        close_old_connections()


def push_payment(booking_id):
    """The M-Pesa prompt (or card link by SMS) a screen has promised. If it can't start, the guest is told by SMS."""
    from apps.bookings.models import Booking
    from apps.bookings.services import guest_context
    from apps.messaging import services as messaging
    from apps.payments.services import start_remote_payment

    b = Booking.objects.select_related("guest", "unit", "unit__area").get(pk=booking_id)
    r = start_remote_payment(b)
    if r.get("error"):
        body = messaging.render("pay_prompt_failed", b.lang, **guest_context(b), reason=r["error"].rstrip("."))
        messaging.send(b.guest.phone, body, booking=b, kind="pay_prompt_failed")
    return r
