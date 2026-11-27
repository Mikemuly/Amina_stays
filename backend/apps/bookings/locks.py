"""Door-code providers. The code lifecycle is real; the lock is pluggable.

simulated  — the console's lock panel plays the role of the keypad (hackathon default)
igloohome  — algoPIN: the PIN carries its own validity window and works offline at the lock,
             which suits Mombasa's patchy power/Wi-Fi (needs IGLOOHOME_API_BASE + IGLOOHOME_API_KEY)
lockbox / caretaker — physical handover; we still issue a reference code for the gate log
"""

import logging
import secrets
from datetime import timedelta

import httpx
from django.conf import settings
from django.utils import timezone

from apps.core.utils import at_local

from .models import AccessCode

log = logging.getLogger("amina.locks")


def _random_code():
    while True:
        code = f"{secrets.randbelow(900000) + 100000}"
        if len(set(code)) > 2 and code not in "0123456789" and code not in "9876543210":
            return code


class SimulatedLock:
    name = "simulated"

    def issue(self, booking, valid_from, valid_until):
        return _random_code(), ""

    def revoke(self, access_code):
        return True


class IgloohomeLock(SimulatedLock):
    name = "igloohome"

    def issue(self, booking, valid_from, valid_until):
        device = booking.unit.lock_device_id
        if not (settings.LOCK_PROVIDER_API_BASE and settings.IGLOOHOME_API_KEY and device):
            log.info("igloohome not configured for %s - issuing a simulated code", booking.unit)
            return super().issue(booking, valid_from, valid_until)
        fmt = "%Y-%m-%dT%H:00:00%z"
        body = {
            "variance": 1,
            "startDate": timezone.localtime(valid_from).strftime(fmt),
            "endDate": timezone.localtime(valid_until + timedelta(hours=1)).strftime(fmt),
            "accessName": f"{booking.ref} {booking.guest.name or booking.guest.phone}"[:40],
        }
        try:
            with httpx.Client(timeout=15) as client:
                r = client.post(
                    f"{settings.LOCK_PROVIDER_API_BASE.rstrip('/')}/devices/{device}/algopin/hourly",
                    json=body,
                    headers={"Authorization": f"Bearer {settings.IGLOOHOME_API_KEY}", "Accept": "application/json"},
                )
            r.raise_for_status()
            data = r.json()
            return str(data["pin"]), str(data.get("pinId", ""))
        except Exception as e:
            log.error("igloohome algoPIN failed (%s) — issuing a simulated code", e)
            return super().issue(booking, valid_from, valid_until)


PROVIDERS = {"simulated": SimulatedLock(), "igloohome": IgloohomeLock()}


def provider_for(unit):
    return PROVIDERS.get(unit.access_method, PROVIDERS["simulated"])


def code_window(booking):
    from .services import effective_checkin_time, effective_checkout_time

    valid_from = at_local(booking.check_in, effective_checkin_time(booking)) - timedelta(hours=1)
    valid_until = at_local(booking.check_out, effective_checkout_time(booking)) + timedelta(minutes=30)
    return valid_from, valid_until


def create_code(booking):
    """Generated at confirmation, withheld until arrival day (an old confirmation SMS never carries a live code)."""
    existing = booking.access_codes.filter(revoked_at__isnull=True).first()
    if existing:
        return existing
    valid_from, valid_until = code_window(booking)
    provider = provider_for(booking.unit)
    code, external_id = provider.issue(booking, valid_from, valid_until)
    return AccessCode.objects.create(
        booking=booking,
        code=code,
        provider=provider.name,
        external_id=external_id,
        valid_from=valid_from,
        valid_until=valid_until,
    )


def revoke_all(booking, reason):
    now = timezone.now()
    for c in booking.access_codes.filter(revoked_at__isnull=True):
        try:
            provider_for(booking.unit).revoke(c)
        except Exception:
            log.exception("lock revoke failed for %s", booking.ref)
        c.revoked_at, c.revoke_reason = now, reason[:40]
        c.save(update_fields=["revoked_at", "revoke_reason"])


def refresh_window(booking):
    """Late checkout / early check-in approved: move the code's validity window."""
    c = booking.access_codes.filter(revoked_at__isnull=True).first()
    if c:
        c.valid_from, c.valid_until = code_window(booking)
        c.save(update_fields=["valid_from", "valid_until"])
    return c
