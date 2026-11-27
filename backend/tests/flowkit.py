"""Shared helpers for the end-to-end flow tests: drive a channel the way Africa's Talking would, build a
realistic catalogue from the seed data, settle payments like the provider callback, and freeze the clock."""

import re
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from unittest import mock

from apps.accounts.models import User
from apps.bookings import services as bookings
from apps.bookings.models import Addon
from apps.comms.views import process_incoming_sms, process_ussd, process_voice
from apps.core import seed_data as D
from apps.core.utils import at_local, today
from apps.messaging.models import FAQ, Message
from apps.payments import services as payments
from apps.payments.models import Payment
from apps.properties.models import Area, Unit

KE_GUEST = "+254722333444"


# ---------- the clock ----------


@contextmanager
def frozen(when):
    """Pin timezone.now() (and so today(), auto_now fields and every 'is it due?' check) to `when`."""
    with mock.patch("django.utils.timezone.now", return_value=when):
        yield when


def kenya(day, hhmm):
    return at_local(day, hhmm)


# ---------- messages ----------


def last_id():
    m = Message.objects.order_by("-id").first()
    return m.id if m else 0


def outbox(phone, after=0, **filters):
    return list(Message.objects.filter(phone=phone, direction="out", id__gt=after, **filters).order_by("id"))


def bodies(phone, after=0, **filters):
    return [m.body for m in outbox(phone, after, **filters)]


# ---------- channels ----------


def ussd(chain, phone=KE_GUEST, session="s-flow"):
    """One USSD hop. Every screen must fit Safaricom's 160 characters (prefix included), say CON or END, use
    plain ASCII (telcos can't render special characters), and a menu must never lose an option to truncation."""
    out = process_ussd(phone, chain, session)
    assert out.startswith(("CON ", "END ")), out
    assert len(out) <= 160, f"{chain!r} answers {len(out)} chars:\n{out}"
    assert out.isascii(), f"{chain!r} has characters a phone may not show:\n{out}"
    if out.startswith("CON") and options(out):
        assert not out.endswith("..."), f"{chain!r} cuts its menu off:\n{out}"
        nums = [int(n) for n in options(out) if n != "98"]
        assert nums == list(range(nums[0], nums[0] + len(nums))), f"{chain!r} skips options:\n{out}"
    return out


def options(screen):
    return re.findall(r"^(\d+)\. ", screen, re.MULTILINE)


def ddmm(day):
    return f"{day:%d%m}"


def sms(text, phone=KE_GUEST):
    """Text the Ask Amina line; returns the bodies of everything sent back to this phone."""
    inbound = process_incoming_sms(phone, text, provider_id=f"t-{last_id()}")
    return [m.body for m in outbox(phone, inbound.id)]


def voice(digits="", session="v-flow", phone=KE_GUEST, **extra):
    payload = {
        "sessionId": session,
        "isActive": "1",
        "direction": "Inbound",
        "callerNumber": phone,
        "destinationNumber": "+254711082000",
        "dtmfDigits": digits,
        **extra,
    }
    xml = process_voice(payload)
    return ET.fromstring(xml) if xml else None


def spoken(root):
    return " ".join(" ".join(s.itertext()) for s in root.iter("Say"))


# ---------- data ----------


def build_catalogue():
    """The seeded homes, add-ons and knowledge base (no photos, price rules or history)."""
    areas = {
        a["slug"]: Area.objects.create(name=a["name"], slug=a["slug"], tips=a["tips"], sort_order=i)
        for i, a in enumerate(D.AREAS)
    }
    units = {}
    for i, u in enumerate(D.UNITS):
        units[u["name"]] = Unit.objects.create(
            name=u["name"],
            area=areas[u["area"]],
            property_type=u["property_type"],
            summary=u["summary"],
            bedrooms=u["bedrooms"],
            beds=u["beds"],
            max_guests=u["max_guests"],
            base_price=u["base_price"],
            weekend_price=u["weekend_price"],
            cleaning_fee=u["cleaning_fee"],
            min_nights=u["min_nights"],
            cancellation_policy=u["cancellation_policy"],
            address=u["address"],
            directions=u["directions"],
            landmark=u["landmark"],
            map_link=f"https://maps.google.com/?q={u['lat']},{u['lng']}",
            wifi_name=u["wifi_name"],
            wifi_password=u["wifi_password"],
            parking=u["parking"],
            sort_order=i,
        )
    for i, a in enumerate(D.ADDONS):
        Addon.objects.create(
            code=a["code"],
            name=a["name"],
            category=a["category"],
            price=a["price"],
            pricing=a["pricing"],
            requires_approval=a.get("requires_approval", False),
            options=a.get("options", {}),
            sort_order=i,
        )
    load_faqs()
    return areas, units


def load_faqs():
    for i, (cat, q, kw, en, sw) in enumerate(D.FAQS):
        FAQ.objects.get_or_create(
            question=q, defaults=dict(category=cat, keywords=kw, answer_en=en, answer_sw=sw, sort_order=i)
        )


def make_user(phone, name="", role="guest", lang="en", **extra):
    return User.objects.create_user(phone, name=name, role=role, lang=lang, **extra)


def with_id(user, number="12345678"):
    user.set_id_number(number)
    user.id_type = "national_id" if user.phone.startswith("+254") else "passport"
    user.save()
    return user


def pay(booking):
    """Settle the newest pending payment exactly as the provider's success callback would."""
    p = Payment.objects.filter(booking=booking, status="pending").order_by("-id").first()
    if p is None:
        payments.start_payment(booking)
        p = Payment.objects.filter(booking=booking, status="pending").order_by("-id").first()
    payments.on_success(p, transaction_id=f"QFLOW{p.pk}", provider_ref=f"QFLOW{p.pk}")
    booking.refresh_from_db()
    return booking


def stay(unit, guest, check_in, check_out, *, checked_in=False, channel="web", adults=1, addons=None, plan="full"):
    """A paid, confirmed booking (optionally already checked in with its door code sent)."""
    b = bookings.create_hold(
        unit=unit,
        guest=guest,
        check_in=check_in,
        check_out=check_out,
        channel=channel,
        adults=adults,
        addons=addons,
        payment_plan=plan,
    )
    pay(b)
    assert b.status == "confirmed", b.status
    if checked_in:
        assert bookings.release_code(b, force=True) == "released"
        b.refresh_from_db()
    return b


def this_morning(hhmm="09:00"):
    return kenya(today(), hhmm)
