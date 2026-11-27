"""Availability, pricing and calendar sync.

Availability = no active booking (held-and-unexpired, confirmed, checked-in) and no calendar block
overlapping [check_in, check_out). The database exclusion constraint on bookings is the final word;
these queries keep the UI and the channels honest before we get that far.

Pricing = base price → weekend price → season/weekday rules → per-date overrides, then stay-level
length-of-stay and last-minute/early-bird discounts, cleaning, add-ons and the 2% Tourism Levy.
Guests always see one all-in total (total-price display, as Airbnb made standard in 2025).
"""

import logging
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from apps.core.models import SiteSettings
from apps.core.utils import daterange, kes, today

from .models import CalendarBlock, ICalFeed, PriceOverride, PriceRule, Unit

log = logging.getLogger("amina.properties")


# ---------- availability ----------


def _booking_overlap(unit_ref, check_in, check_out, exclude_booking_id=None):
    from apps.bookings.models import Booking

    qs = Booking.objects.filter(unit=unit_ref, check_in__lt=check_out, check_out__gt=check_in).filter(
        Q(status__in=("confirmed", "checked_in")) | Q(status="held", hold_expires_at__gt=timezone.now())
    )
    if exclude_booking_id:
        qs = qs.exclude(pk=exclude_booking_id)
    return qs


def _block_overlap(unit_ref, check_in, check_out):
    return CalendarBlock.objects.filter(unit=unit_ref, start_date__lt=check_out, end_date__gt=check_in)


def is_available(unit, check_in, check_out, exclude_booking_id=None):
    return (
        not _booking_overlap(unit, check_in, check_out, exclude_booking_id).exists()
        and not _block_overlap(unit, check_in, check_out).exists()
    )


def available_units(check_in, check_out, *, area=None, guests=None, qs=None, bookable=False):
    """Homes free for [check_in, check_out). bookable=True also applies each home's minimum and maximum stay, so
    the list holds only homes a booking would accept (web search). The phone channels apply that rule themselves on
    the full list, which also tells them which free homes need a longer stay."""
    qs = (qs if qs is not None else Unit.objects.filter(status="active")).select_related("area")
    if bookable:
        nights = (check_out - check_in).days
        qs = qs.filter(min_nights__lte=nights, max_nights__gte=nights)
    qs = qs.annotate(
        _busy=Exists(_booking_overlap(OuterRef("pk"), check_in, check_out)),
        _blocked=Exists(_block_overlap(OuterRef("pk"), check_in, check_out)),
    ).filter(_busy=False, _blocked=False)
    if area:
        qs = qs.filter(Q(area__slug__iexact=area) | Q(area__name__iexact=area))
    if guests:
        qs = qs.filter(max_guests__gte=guests)
    return qs


def unavailable_nights(unit, start, end):
    """Set of nights (dates) in [start, end) that can't be booked."""
    from apps.bookings.models import Booking

    nights = set()
    bookings = Booking.objects.filter(unit=unit, check_in__lt=end, check_out__gt=start).filter(
        Q(status__in=("confirmed", "checked_in")) | Q(status="held", hold_expires_at__gt=timezone.now())
    )
    for b in bookings.only("check_in", "check_out"):
        nights.update(daterange(max(b.check_in, start), min(b.check_out, end)))
    for blk in CalendarBlock.objects.filter(unit=unit, start_date__lt=end, end_date__gt=start):
        nights.update(daterange(max(blk.start_date, start), min(blk.end_date, end)))
    return nights


# ---------- pricing ----------


def _apply(price, rule):
    v = Decimal(rule.value)
    if rule.adjust_type == "percent":
        return price * (1 + v / 100)
    if rule.adjust_type == "amount":
        return price + v
    return v  # fixed nightly price


def nightly_rates(unit, check_in, check_out):
    """[(date, price, label)] for each night, before stay-level discounts."""
    rules = [
        r
        for r in PriceRule.objects.filter(active=True).filter(Q(unit=unit) | Q(unit__isnull=True))
        if r.kind in ("season", "weekday")
    ]
    overrides = {o.date: o for o in PriceOverride.objects.filter(unit=unit, date__gte=check_in, date__lt=check_out)}
    out = []
    for d in daterange(check_in, check_out):
        price = Decimal(unit.base_price)
        label = "Standard"
        if unit.weekend_price and d.weekday() in (4, 5):  # Friday and Saturday nights
            price, label = Decimal(unit.weekend_price), "Weekend"
        for r in rules:
            in_dates = (r.start_date is None or r.start_date <= d) and (r.end_date is None or d <= r.end_date)
            in_days = not r.weekdays or d.weekday() in r.weekdays
            if in_dates and in_days:
                price, label = _apply(price, r), r.name
        if d in overrides:
            price, label = Decimal(overrides[d].price), overrides[d].note or "Special price"
        out.append((d, int(max(price, 0).quantize(Decimal(1))), label))
    return out


def quote(unit, check_in, check_out, *, guests=1, addons=None, ref_today=None, payment_plan="full"):
    """All-in price for a stay. addons: [{"addon": Addon, "quantity": int, "details": {}}].
    On-request add-ons (requires_approval) are listed under "pending" and left out of the total until approved."""
    s = SiteSettings.load()
    t = ref_today or today()
    rates = nightly_rates(unit, check_in, check_out)
    n = len(rates)
    accommodation = sum(p for _, p, _ in rates)
    lines = []
    if n:
        avg = round(accommodation / n)
        nights = f"{n} night{'s' if n != 1 else ''}"
        # "KES 9,008 x 3 nights" next to KES 27,025 reads as a sum error, so averages only multiply when exact
        label = f"{kes(avg)} x {nights}" if avg * n == accommodation else f"{nights} (avg. {kes(avg)})"
        lines.append({"label": label, "amount": accommodation, "kind": "nights"})

    discount, discount_label = 0, ""
    if n >= 28 and unit.monthly_discount:
        discount, discount_label = (
            round(accommodation * unit.monthly_discount / 100),
            f"Monthly stay discount ({unit.monthly_discount}%)",
        )
    elif n >= 7 and unit.weekly_discount:
        discount, discount_label = (
            round(accommodation * unit.weekly_discount / 100),
            f"Weekly stay discount ({unit.weekly_discount}%)",
        )
    lead = (check_in - t).days
    for r in PriceRule.objects.filter(active=True, kind__in=("last_minute", "early_bird")).filter(
        Q(unit=unit) | Q(unit__isnull=True)
    ):
        hit = (r.kind == "last_minute" and r.days_before is not None and 0 <= lead <= r.days_before) or (
            r.kind == "early_bird" and r.days_before is not None and lead >= r.days_before
        )
        if hit and r.adjust_type == "percent" and r.value < 0:
            amount = round(accommodation * abs(Decimal(r.value)) / 100)
            if amount > discount:  # discounts don't stack: the best one wins
                discount, discount_label = amount, f"{r.name} ({abs(int(r.value))}% off)"
    if discount:
        lines.append({"label": discount_label, "amount": -discount, "kind": "discount"})

    if unit.cleaning_fee:
        lines.append({"label": "Cleaning fee", "amount": unit.cleaning_fee, "kind": "cleaning"})

    addons_total, addon_lines, pending_lines = 0, [], []
    for item in addons or []:
        a, qty = item["addon"], max(1, int(item.get("quantity") or 1))
        amount = a.price_for(n, guests, qty)
        unit_word = {
            "per_guest_night": f"{qty} guest{'s' if qty != 1 else ''} x {n} morning{'s' if n != 1 else ''}",
            "per_night": f"{n} night{'s' if n != 1 else ''}",
        }.get(a.pricing, f"x{qty}" if qty > 1 else "")
        line = {
            "label": f"{a.name}{' (' + unit_word + ')' if unit_word else ''}",
            "amount": amount,
            "kind": "addon",
            "code": a.code,
        }
        if a.requires_approval:  # on request: charged only once Amina approves it
            pending_lines.append(line)
            continue
        addons_total += amount
        addon_lines.append(line)
    lines.extend(addon_lines)

    taxable = accommodation - discount + unit.cleaning_fee + addons_total
    levy = round(taxable * Decimal(s.tourism_levy_percent) / 100)
    vat = round(taxable * Decimal(s.vat_percent) / 100) if s.vat_registered and s.vat_percent else 0
    if levy:
        lines.append(
            {"label": f"Tourism levy ({Decimal(s.tourism_levy_percent).normalize()}%)", "amount": levy, "kind": "levy"}
        )
    if vat:
        lines.append({"label": f"VAT ({Decimal(s.vat_percent).normalize()}%)", "amount": vat, "kind": "vat"})
    total = taxable + levy + vat
    deposit = -(-total * s.deposit_percent // 100)  # ceil
    due_now = deposit if payment_plan == "deposit" and s.deposit_percent < 100 and lead > s.balance_due_days else total
    return {
        "nights": n,
        "nightly": [{"date": d.isoformat(), "price": p, "label": lbl} for d, p, lbl in rates],
        "accommodation": accommodation,
        "discount": discount,
        "cleaning_fee": unit.cleaning_fee,
        "addons": addons_total,
        "levy": levy,
        "vat": vat,
        "total": total,
        "avg_nightly_all_in": round(total / n) if n else 0,
        "deposit": deposit,
        "due_now": due_now,
        "deposit_available": lead > s.balance_due_days and s.deposit_percent < 100,
        "balance_due_date": (check_in - timedelta(days=s.balance_due_days)).isoformat(),
        "lines": lines,
        "pending": pending_lines,
        "currency": "KES",
        "approx": {
            "USD": round(total / float(s.usd_rate)),
            "EUR": round(total / float(s.eur_rate)),
            "GBP": round(total / float(s.gbp_rate)),
        },
    }


def from_price(unit):
    """'From' price for cards/SMS when no dates are chosen: base nightly + a share of cleaning + levy."""
    s = SiteSettings.load()
    per_night = unit.base_price + (unit.cleaning_fee / max(unit.min_nights, 2))
    return round(per_night * (1 + float(s.tourism_levy_percent) / 100))


def price_list_text(limit=6):
    """Each home's all-in 'from' price per night, the same figure as the website, USSD and voice."""
    units = Unit.objects.filter(status="active").select_related("area")[:limit]
    return "; ".join(
        f"{u.name} ({u.area.name}, {u.bedrooms}BR, {u.max_guests} guests) {kes(from_price(u))}" for u in units
    )


# ---------- iCal (Airbnb / Booking.com / Vrbo calendar sync) ----------


def export_ics(unit):
    from apps.bookings.models import Booking

    stamp = timezone.now().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Amina Stays//Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{unit.name} (Amina Stays)",
    ]
    t = today() - timedelta(days=30)
    for b in Booking.objects.filter(unit=unit, status__in=("held", "confirmed", "checked_in"), check_out__gte=t):
        if b.status == "held" and not b.hold_active:
            continue
        lines += [
            "BEGIN:VEVENT",
            f"UID:{b.ref.lower()}@aminastays",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{b.check_in:%Y%m%d}",
            f"DTEND;VALUE=DATE:{b.check_out:%Y%m%d}",
            "SUMMARY:Reserved (Amina Stays)",
            "END:VEVENT",
        ]
    for blk in CalendarBlock.objects.filter(unit=unit, end_date__gte=t).exclude(reason="external"):
        lines += [
            "BEGIN:VEVENT",
            f"UID:block-{blk.pk}@aminastays",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{blk.start_date:%Y%m%d}",
            f"DTEND;VALUE=DATE:{blk.end_date:%Y%m%d}",
            "SUMMARY:Not available",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def _ics_date(value):
    value = value.strip()
    m = re.match(r"(\d{4})(\d{2})(\d{2})", value)
    if not m:
        return None
    d = date(int(m[1]), int(m[2]), int(m[3]))
    if "T" in value and value.endswith("Z"):  # a UTC datetime: convert to Kenya date
        try:
            dt = datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
            d = timezone.localtime(dt).date()
        except ValueError:
            pass
    return d


def parse_ics(text):
    """Minimal RFC 5545 reader: unfolds lines and returns [{uid, start, end, summary}] for VEVENTs."""
    unfolded = re.sub(r"\r?\n[ \t]", "", text or "")
    events, cur = [], None
    for line in unfolded.splitlines():
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line == "END:VEVENT" and cur is not None:
            if cur.get("start") and cur.get("end") is None:
                cur["end"] = cur["start"] + timedelta(days=1)
            if cur.get("start") and cur.get("end") and cur["end"] > cur["start"]:
                events.append(cur)
            cur = None
        elif cur is not None and ":" in line:
            key, value = line.split(":", 1)
            name = key.split(";", 1)[0].upper()
            if name == "DTSTART":
                cur["start"] = _ics_date(value)
            elif name == "DTEND":
                cur["end"] = _ics_date(value)
            elif name == "UID":
                cur["uid"] = value.strip()
            elif name == "SUMMARY":
                cur["summary"] = value.strip()
    return events


def sync_feed(feed, text=None):
    """Import one OTA calendar: upsert blocks, drop stale ones, and raise an alert on any clash with a direct booking."""
    from apps.core.activity import record

    try:
        if text is None:
            with httpx.Client(timeout=15, follow_redirects=True) as client:
                r = client.get(feed.url, headers={"User-Agent": "AminaStays-iCal/2.0"})
                r.raise_for_status()
                text = r.text
        events = [e for e in parse_ics(text) if e["end"] >= today()]
    except Exception as e:
        feed.last_ok, feed.last_error, feed.last_synced_at = False, str(e)[:300], timezone.now()
        feed.save(update_fields=["last_ok", "last_error", "last_synced_at"])
        return {"ok": False, "error": str(e)}

    conflicts = []
    with transaction.atomic():
        seen = set()
        for e in events:
            uid = e.get("uid") or f"{e['start']}-{e['end']}"
            seen.add(uid)
            blk, _ = CalendarBlock.objects.update_or_create(
                feed=feed,
                external_uid=uid,
                defaults={
                    "unit": feed.unit,
                    "start_date": e["start"],
                    "end_date": e["end"],
                    "reason": "external",
                    "note": f"{feed.name}: {e.get('summary', 'Reserved')}"[:160],
                },
            )
            clash = (
                _booking_overlap(feed.unit, e["start"], e["end"]).filter(status__in=("confirmed", "checked_in")).first()
            )
            if clash:
                conflicts.append((blk, clash))
        CalendarBlock.objects.filter(feed=feed).exclude(external_uid__in=seen).delete()
        feed.last_ok, feed.last_error, feed.last_synced_at, feed.events_count = True, "", timezone.now(), len(events)
        feed.save(update_fields=["last_ok", "last_error", "last_synced_at", "events_count"])

    for blk, booking in conflicts:
        from apps.safety.services import raise_alert

        raise_alert(
            "conflict",
            f"Double booking risk: {feed.name} blocks {feed.unit.name} {blk.start_date}→{blk.end_date}, overlapping direct booking {booking.ref}",
            severity="critical",
            booking=booking,
            dedupe=f"conflict:{feed.pk}:{blk.external_uid}:{booking.ref}",
        )
    record(
        "listing",
        f"Calendar synced from {feed.name} for {feed.unit.name}: {len(events)} event(s)",
        conflicts=len(conflicts),
    )
    return {"ok": True, "events": len(events), "conflicts": len(conflicts)}


def sync_all_feeds():
    return [sync_feed(f) for f in ICalFeed.objects.filter(active=True).select_related("unit")]
