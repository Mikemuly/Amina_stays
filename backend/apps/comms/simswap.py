"""SIM-swap check (Africa's Talking Insights) before a door code goes out.

A recently swapped SIM is the classic M-Pesa / account-takeover fraud signal in Kenya: whoever holds
the new SIM receives the guest's door code. If the number was swapped in the last 7 days we hold the
code and ask Amina to call the guest. Simulation: numbers ending in 999 report a fresh swap.
"""

import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from . import at
from .models import SimSwapCheck

log = logging.getLogger("amina.simswap")
PENDING_TIMEOUT = timedelta(minutes=10)
RECENT = timedelta(days=7)
DATE_FORMATS = ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y")  # AT's docs show "01-01-1900"; the live format isn't documented


def _simulated():
    return settings.SIM_SWAP_PROVIDER == "simulate" or (settings.SIM_SWAP_PROVIDER == "" and not at.configured())


def request_check(booking):
    phone = booking.guest.phone
    check = SimSwapCheck.objects.create(phone=phone, booking=booking)
    if _simulated():
        swapped = phone.endswith("999")
        check.status = "Swapped" if swapped else "NoSwapDate"
        check.last_swap_date = timezone.now() - timedelta(days=1) if swapped else None
        check.raw = {"simulated": True}
    else:
        try:
            res = at.sim_swap_check([phone])
            first = res.get("responses") or res.get("data") or [{}]
            first = first[0] if isinstance(first, list) and first else res
            check.request_id = str(first.get("requestId") or first.get("transactionId") or "")[:80]
            check.status = first.get("status") or "Queued"
            check.last_swap_date = _swap_date(first.get("lastSimSwapDate"))
            check.raw = res
        except Exception as e:
            log.warning("SIM swap request failed: %s", e)
            check.status, check.raw = "Failed", {"error": str(e)}
    check.save()
    _sync_booking(check)
    return check


def _sync_booking(check):
    if check.booking_id:
        from apps.bookings.models import Booking

        Booking.objects.filter(pk=check.booking_id).update(
            sim_swap_status=check.status, sim_swap_checked_at=timezone.now(), sim_swap_request_id=check.request_id
        )


def _swap_date(value):
    """lastSimSwapDate as an aware datetime: dd-mm-yyyy, yyyy-mm-dd, dd/mm/yyyy or an ISO datetime. None (and a
    warning in the log) when there's nothing we can read."""
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in DATE_FORMATS:
        try:
            return timezone.make_aware(datetime.strptime(text, fmt))
        except ValueError:
            pass
    try:
        when = parse_datetime(text)
    except ValueError:
        when = None
    if when is None:
        log.warning("unreadable SIM swap date %r", value)
        return None
    return when if timezone.is_aware(when) else timezone.make_aware(when)


def _state(check):
    if check.status == "Queued":
        return "pending" if timezone.now() - check.created_at < PENDING_TIMEOUT else "unavailable"
    if check.status == "Swapped":
        # only a swap inside the window holds the code: an old date (AT's "01-01-1900") or an unreadable one doesn't
        if check.last_swap_date and timezone.now() - check.last_swap_date <= RECENT:
            return "swapped"
        return "clear"
    if check.status == "NoSwapDate":
        return "clear"
    return "unavailable"  # Failed / Invalid / Unsupported / InsufficientBalance — fail open, but it's recorded


def status_for(booking):
    check = SimSwapCheck.objects.filter(booking=booking).order_by("-id").first()
    if check is None or (check.status != "Queued" and timezone.now() - check.updated_at > timedelta(hours=12)):
        check = request_check(booking)
    return _state(check)


def on_callback(data):
    rid = str(data.get("requestId") or data.get("transactionId") or "")
    check = SimSwapCheck.objects.filter(request_id=rid).order_by("-id").first() if rid else None
    if check is None and data.get("phoneNumber"):
        check = SimSwapCheck.objects.filter(phone=data["phoneNumber"], status="Queued").order_by("-id").first()
    if check is None:
        return None
    check.status = data.get("status") or check.status
    check.last_swap_date = _swap_date(data.get("lastSimSwapDate"))
    check.raw = {**check.raw, "callback": data}
    check.save()
    _sync_booking(check)
    return check
