"""Service alerts. Guests hear about an outage or planned maintenance before they have to ask, hear again when it's
over, and stay online with an Africa's Talking data bundle while the Wi-Fi or power is down. A guest who reports a
problem we already know about gets the notice instead of a new work order."""

import logging
import re
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.bookings.models import Booking
from apps.core.activity import record
from apps.core.utils import nice_date, nice_time, today
from apps.messaging import services as messaging
from apps.properties.models import Area, Unit

from .models import Delivery, Notice

log = logging.getLogger("amina.notices")

HEADS_UP_BEFORE = timedelta(hours=24)  # planned maintenance: guests hear about it a day ahead
OVERDUE_GRACE = timedelta(minutes=30)  # then Amina is asked whether it's really still on
DATA_SERVICES = {"wifi", "power"}  # outages that take guests offline: the data bundle applies
# a guest's problem report (a Task category) that an active notice already explains
COVERS = {
    "power": {"power"},
    "water": {"water"},
    "plumbing": {"water"},
    "wifi": {"wifi", "power"},
    "ac": {"ac", "power"},
    "appliance": {"power", "gas"},
}
TITLES = {
    "en": {
        "power": "Power outage",
        "water": "No water supply",
        "wifi": "Wi-Fi down",
        "ac": "Air conditioning not working",
        "gas": "No cooking gas",
        "pool": "Swimming pool closed",
        "lift": "Lift out of service",
        "road": "Road access blocked",
        "network": "Mobile network problems",
        "security": "Security incident",
        "other": "Service disruption",
    },
    "sw": {
        "power": "Umeme umekatika",
        "water": "Hakuna maji",
        "wifi": "Wi-Fi haifanyi kazi",
        "ac": "AC haifanyi kazi",
        "gas": "Hakuna gesi ya kupikia",
        "pool": "Bwawa la kuogelea limefungwa",
        "lift": "Lifti haifanyi kazi",
        "road": "Barabara imefungwa",
        "network": "Matatizo ya mtandao wa simu",
        "security": "Tukio la usalama",
        "other": "Usumbufu wa huduma",
    },
}
SERVICE_WORDS = {
    "power": ("power", "stima", "umeme", "electricity", "blackout", "lights", "kplc"),
    "water": ("water", "maji"),
    "wifi": ("wifi", "wi-fi", "internet", "mtandao", "router"),
    "ac": ("ac", "aircon", "air-con"),
    "gas": ("gas", "gesi"),
    "pool": ("pool", "bwawa"),
    "lift": ("lift", "elevator", "lifti"),
    "road": ("road", "barabara"),
    "network": ("network", "signal", "safaricom", "airtel"),
    "security": ("security", "usalama"),
    "other": ("other", "service"),
}
ALL_WORDS = ("all", "zote", "everywhere", "kote")
LABELS = dict(Notice.SERVICES)


def default_title(kind, service, lang="en"):
    label = LABELS.get(service, "Service")
    if kind == "maintenance":
        return f"Planned maintenance: {label}" if lang != "sw" else f"Matengenezo yaliyopangwa: {label}"
    if kind == "advisory":
        return f"Advisory: {label}" if lang != "sw" else f"Tahadhari: {label}"
    return TITLES.get(lang, TITLES["en"]).get(service) or TITLES["en"]["other"]


def title_in(n, lang):
    """The notice title in the guest's language, unless Amina wrote her own."""
    if lang != "en" and n.title == default_title(n.kind, n.service):
        return default_title(n.kind, n.service, lang)
    return n.title


def local(dt):
    return timezone.localtime(dt)


def when_text(dt, lang="en"):
    """'2pm' today, else 'Sat 29 Nov 2pm'."""
    d = local(dt)
    clock = nice_time(d.strftime("%H:%M"))
    return clock if d.date() == today() else f"{nice_date(d.date(), lang)} {clock}"


def eta_text(n, lang="en"):
    """' Expected back by 6pm.' - a leading space, as it follows a sentence (render() strips its own)."""
    return " " + messaging.render("notice_eta", lang, time=when_text(n.expected_end, lang)) if n.expected_end else ""


def said(text):
    """The host's own words inside an alert: a capital first and exactly one full stop, so sentences don't run on."""
    text = (text or "").strip()
    if not text:
        return ""
    text = text[0].upper() + text[1:]
    return text if text.endswith((".", "!", "?")) else f"{text}."


def homes_text(n):
    names = list(n.units.values_list("name", flat=True))
    return ", ".join(names) if names else "all homes"


# ---------- who is affected ----------


def _stays(n):
    qs = Booking.objects.filter(status__in=("confirmed", "checked_in")).select_related("guest", "unit")
    ids = list(n.units.values_list("id", flat=True))
    return qs.filter(unit_id__in=ids) if ids else qs


def affected_now(n):
    """An outage touches the guests in the home now (on checkout morning too, until they leave) and those arriving
    before it's expected to end."""
    t = today()
    until = local(n.expected_end).date() if n.expected_end else t
    return [
        b
        for b in _stays(n).filter(check_out__gte=t)
        if b.status == "checked_in" or (b.check_in <= until and b.check_out > t)
    ]


def affected_by_plan(n):
    """Planned work touches anyone staying while it runs."""
    start = local(n.starts_at).date()
    end = local(n.expected_end).date() if n.expected_end else start
    return list(_stays(n).filter(check_in__lte=end, check_out__gt=start))


def affects_unit(n, unit):
    ids = list(n.units.values_list("id", flat=True))
    return not ids or unit.pk in ids


def for_unit(unit, statuses=("active",)):
    return (
        Notice.objects.filter(status__in=statuses)
        .filter(Q(units=unit) | Q(units__isnull=True))
        .distinct()
        .order_by("starts_at")
    )


def current_for_unit(unit, days=7):
    """What a guest at this home should know: what's going on now and what's planned for the coming days."""
    soon = timezone.now() + timedelta(days=days)
    return [n for n in for_unit(unit, ("active", "scheduled")) if n.status == "active" or n.starts_at <= soon]


# ---------- telling guests ----------


def _claim(n, b, kind):
    try:
        with transaction.atomic():
            Delivery.objects.create(notice=n, phone=b.guest.phone, booking=b, kind=kind)
        return True
    except IntegrityError:
        return False


def _tell(n, b, kind, key, **ctx):
    """Text one guest, once per notice and kind ('update' may repeat)."""
    if not _claim(n, b, kind):
        return 0
    lang = b.guest.lang or b.lang
    body = messaging.render(
        key,
        lang,
        unit=b.unit.name,
        title=title_in(n, lang),
        message=said(n.message),
        eta=eta_text(n, lang),
        when=when_text(n.starts_at, lang),
        **ctx,
    )
    messaging.send(b.guest.phone, body, booking=b, kind=key)
    return 1


def _compensate(n, b):
    """Wi-Fi or power down while the guest is in the home: an Africa's Talking data bundle, once per notice."""
    if not n.data_mb or n.service not in DATA_SERVICES or b.status != "checked_in":
        return 0
    if not _claim(n, b, "data"):
        return 0
    from apps.rewards.services import send_payout

    p = send_payout(
        b.guest,
        "data",
        n.data_mb,
        "outage",
        booking=b,
        note=f"Service alert #{n.pk}: {n.title}"[:160],
        key=f"outage-{n.pk}-{b.guest.phone}",
    )
    return n.data_mb if p is not None and p.status not in ("failed", "rejected") else 0


def _count(n, told):
    if told:
        Notice.objects.filter(pk=n.pk).update(notified=F("notified") + told)
        n.notified += told


def publish(n, now=None):
    """Start a notice that's due and text everyone it touches who hasn't heard yet. Run on creation and by the
    scheduler, so guests who arrive mid-outage are told too."""
    now = now or timezone.now()
    told = 0
    if n.status == "scheduled" and n.starts_at <= now:
        n.status = "active"
        n.save(update_fields=["status", "updated_at"])
        record("system", f"Service alert #{n.pk} started: {n.title} ({homes_text(n)})")
    if n.status == "active":
        for b in affected_now(n):
            heard = Delivery.objects.filter(notice=n, phone=b.guest.phone, kind__in=("start", "heads_up"))
            if n.kind == "maintenance" and heard.filter(kind="heads_up").exists():
                _claim(n, b, "start")  # warned a day ahead: no second text, but they'll hear when it's over
                continue
            if heard.filter(kind="start").exists():
                continue
            mb = _compensate(n, b)
            data_line = " " + messaging.render("notice_data_line", b.guest.lang or b.lang, mb=mb) if mb else ""
            told += _tell(n, b, "start", "notice_active", data_line=data_line)
    elif n.status == "scheduled" and n.starts_at - HEADS_UP_BEFORE <= now:
        for b in affected_by_plan(n):
            told += _tell(n, b, "heads_up", "notice_heads_up")
    _count(n, told)
    return told


def create(
    *,
    kind,
    service,
    title="",
    message="",
    units=(),
    starts_at=None,
    expected_end=None,
    data_mb=None,
    source="host",
    actor=None,
):
    from apps.rewards.models import Program

    now = timezone.now()
    starts_at = starts_at or now
    if data_mb is None:
        data_mb = Program.load().outage_data_mb if service in DATA_SERVICES and kind == "outage" else 0
    n = Notice.objects.create(
        kind=kind,
        service=service,
        title=(title or default_title(kind, service))[:100],
        message=(message or "").strip(),
        starts_at=starts_at,
        expected_end=expected_end,
        status="scheduled" if starts_at > now else "active",
        data_mb=data_mb,
        source=source,
        created_by=actor if getattr(actor, "pk", None) else None,
    )
    if units:
        n.units.set(units)
    told = publish(n, now)
    record(
        "system",
        f"Service alert #{n.pk}: {n.title} ({homes_text(n)}) - {told} guest(s) told",
        actor=actor if getattr(actor, "pk", None) else None,
    )
    _tell_team(n, told, actor)
    return n


def _tell_team(n, told, actor):
    """The people who fix it hear about it; if a staff member raised it, Amina does."""
    from apps.bookings.services import notify_host
    from apps.operations.services import staff_for

    text = f"Service alert #{n.pk}: {n.title} at {homes_text(n)}. {told} guest(s) told. Reply RESTORED {n.pk} when it's fixed."
    role = getattr(actor, "role", "")
    if role and role not in ("owner", "manager"):
        notify_host(
            f"{actor.display_name} reported service alert #{n.pk}: {n.title} at {homes_text(n)}. {told} guest(s) told. "
            f"Reply RESTORED {n.pk} when it's fixed.",
            kind="notice_staff",
        )
        return
    unit = n.units.first()
    for person in {p for p in (staff_for("caretaker", unit), staff_for("manager")) if p is not None}:
        if getattr(actor, "pk", None) != person.pk:
            messaging.send(person.phone, text, kind="notice_staff")


def update(n, *, message=None, expected_end=None, actor=None):
    """New details or a new expected time: everyone already told hears the update."""
    fields = []
    if message is not None and message.strip() != n.message:
        n.message = message.strip()
        fields.append("message")
    if expected_end is not None and expected_end != n.expected_end:
        n.expected_end, n.overdue_nudged = expected_end, False
        fields += ["expected_end", "overdue_nudged"]
    if not fields or n.status not in ("active", "scheduled"):
        return 0
    n.save(update_fields=[*fields, "updated_at"])
    told = 0
    kind = "start" if n.status == "active" else "heads_up"
    for d in Delivery.objects.filter(notice=n, kind=kind).select_related("booking__guest", "booking__unit"):
        b = d.booking
        if b is not None and b.status in ("confirmed", "checked_in") and b.check_out >= today():
            told += _tell(n, b, "update", "notice_update")
    _count(n, told)
    record("system", f"Service alert #{n.pk} updated: {n.title} - {told} guest(s) told", actor=actor)
    return told


def resolve(n, *, note="", actor=None):
    """It's over: the guests who heard it was broken hear it's fixed."""
    if n.status in ("resolved", "cancelled"):
        return 0
    if n.status == "scheduled":
        return cancel(n, actor=actor)
    n.status, n.resolved_at, n.resolution = "resolved", timezone.now(), (note or "").strip()[:240]
    n.save(update_fields=["status", "resolved_at", "resolution", "updated_at"])
    told = 0
    for d in Delivery.objects.filter(notice=n, kind="start").select_related("booking__guest", "booking__unit"):
        b = d.booking
        if b is not None and b.status in ("confirmed", "checked_in") and b.check_out >= today():
            told += _tell(n, b, "restored", "notice_restored", resolution=f" {n.resolution}" if n.resolution else "")
    _count(n, told)
    record("system", f"Service alert #{n.pk} resolved: {n.title} - {told} guest(s) told", actor=actor)
    return told


def cancel(n, *, actor=None):
    if n.status != "scheduled":
        return 0
    n.status, n.resolved_at = "cancelled", timezone.now()
    n.save(update_fields=["status", "resolved_at", "updated_at"])
    told = 0
    for d in Delivery.objects.filter(notice=n, kind="heads_up").select_related("booking__guest", "booking__unit"):
        b = d.booking
        if b is not None and b.status in ("confirmed", "checked_in"):
            told += _tell(n, b, "cancelled", "notice_cancelled")
    _count(n, told)
    record("system", f"Service alert #{n.pk} cancelled: {n.title}", actor=actor)
    return told


def run(now=None):
    """Scheduler: start planned work on time, warn guests a day ahead, tell new arrivals about an outage that's
    still on, and ask Amina once if an outage runs past its expected end."""
    from apps.bookings.services import notify_host

    now = now or timezone.now()
    told = 0
    for n in Notice.objects.filter(status__in=("scheduled", "active")):
        told += publish(n, now)
        if n.status == "active" and n.expected_end and n.expected_end + OVERDUE_GRACE <= now and not n.overdue_nudged:
            n.overdue_nudged = True
            n.save(update_fields=["overdue_nudged"])
            notify_host(
                f"Service alert #{n.pk} ({n.title}, {homes_text(n)}) was expected to end at {when_text(n.expected_end)}. "
                f"Still on? Reply RESTORED {n.pk} when it's fixed, or set a new time in the console.",
                kind="notice_overdue",
            )
    return told


# ---------- what guests see when they ask ----------


def data_request(b, lang="en"):
    """A guest texts DATA: during a Wi-Fi or power outage at their home they get the data bundle, once. None when
    nothing is down (the caller says so)."""
    from apps.rewards.services import can_send

    n = next((n for n in for_unit(b.unit) if n.service in DATA_SERVICES), None)
    if n is None:
        return None
    if n.data_mb and can_send("data"):
        if Delivery.objects.filter(notice=n, phone=b.guest.phone, kind="data").exists():
            return messaging.render("notice_data_already", lang)
        mb = _compensate(n, b)
        if mb:
            return messaging.render("notice_data_sent", lang, mb=mb)
    return _known_text(n, b, lang)  # no bundle for this one: at least what's going on and when it's back


def known_issue(booking, category):
    """An active notice that already explains the problem this guest is reporting."""
    services = COVERS.get(category)
    if not services or booking is None:
        return None
    return next((n for n in for_unit(booking.unit) if n.service in services), None)


def known_issue_text(booking, category, lang="en"):
    n = known_issue(booking, category)
    return _known_text(n, booking, lang) if n is not None else None


def _known_text(n, booking, lang):
    return messaging.render(
        "notice_known",
        lang,
        unit=booking.unit.name,
        title=title_in(n, lang),
        since=when_text(n.starts_at, lang),
        eta=eta_text(n, lang),
        message=said(n.message),
    )


def line(n, lang="en"):
    if n.status == "scheduled":
        return f"{title_in(n, lang)} ({when_text(n.starts_at, lang)})"
    tail = f", {'until' if lang != 'sw' else 'hadi'} {when_text(n.expected_end, lang)}" if n.expected_end else ""
    return f"{title_in(n, lang)} ({'since' if lang != 'sw' else 'tangu'} {when_text(n.starts_at, lang)}{tail})"


def status_text(phone, lang="en"):
    """ALERTS by SMS, Service status on USSD: what's going on at the guest's home."""
    from apps.bookings.services import current_booking

    b = current_booking(phone)
    if b is not None and b.status in ("confirmed", "checked_in"):
        notices = current_for_unit(b.unit)
        if not notices:
            return messaging.render("notice_all_clear", lang, unit=b.unit.name)
        lines = "; ".join(line(n, lang) + (f" - {n.message}" if n.message else "") for n in notices)
        return messaging.render("notice_status", lang, unit=b.unit.name, list=lines)
    notices = list(Notice.objects.filter(status="active"))
    if not notices:
        return messaging.render("notice_none", lang)
    return messaging.render("notice_status", lang, unit="our homes", list="; ".join(line(n, lang) for n in notices))


# ---------- reports by SMS and USSD (Amina and her staff) ----------


def parse_service(word):
    w = (word or "").lower().strip(".,:;!")
    return next((key for key, words in SERVICE_WORDS.items() if w in words), None)


def parse_scope(text, staff=None):
    """'all ...', a home's name or an area in free text -> (units, rest, found). [] means every home.
    Without a place, a staff member assigned to exactly one home means that home."""
    low = f" {text.lower()} "
    for w in ALL_WORDS:
        if f" {w} " in low:
            return [], re.sub(rf"\b{w}\b", "", text, count=1, flags=re.IGNORECASE).strip(" ,.-"), True
    units = list(Unit.objects.filter(status="active").select_related("area"))
    for u in sorted(units, key=lambda x: -len(x.name)):
        if u.name.lower() in low:
            return [u], re.sub(re.escape(u.name), "", text, count=1, flags=re.IGNORECASE).strip(" ,.-"), True
    generic = {"apartment", "studio", "suite", "house", "cottage", "loft", "home", "the", "family", "creek"}
    for u in units:
        for w in u.name.lower().split():
            if len(w) > 3 and w not in generic and re.search(rf"\b{re.escape(w)}\b", low):
                return [u], re.sub(rf"\b{re.escape(w)}\b", "", text, count=1, flags=re.IGNORECASE).strip(" ,.-"), True
    for a in Area.objects.all():
        if re.search(rf"\b{re.escape(a.name.lower())}\b", low):
            rest = re.sub(re.escape(a.name), "", text, count=1, flags=re.IGNORECASE).strip(" ,.-")
            return [u for u in units if u.area_id == a.pk], rest, True
    if staff is not None:
        mine = list(staff.assigned_units.all()[:2])
        if len(mine) == 1:
            return mine, text.strip(), True
    return [], text.strip(), False


def report_by_text(user, text, source="sms"):
    """'OUTAGE POWER DIANI generator on' from Amina or her staff. Returns the reply text."""
    m = re.match(r"^\s*(outage|maintenance|advisory)\s+(\S+)\s*(.*)$", text, re.IGNORECASE | re.DOTALL)
    if not m:
        return "Text OUTAGE <power|water|wifi|...> <home|ALL> <what guests should know>."
    service = parse_service(m[2])
    if not service:
        return f"Which service? Use one of: {', '.join(k for k in SERVICE_WORDS if k != 'other')}."
    units, message, found = parse_scope(
        m[3], staff=user if getattr(user, "role", "") not in ("owner", "manager") else None
    )
    if not found:
        return f"Which home? Text {m[1].upper()} {m[2].upper()} <home name|ALL> <message>."
    n = create(kind=m[1].lower(), service=service, message=message, units=units, source=source, actor=user)
    return f"Alert #{n.pk} sent: {n.title} at {homes_text(n)}. {n.notified} guest(s) told. Text RESTORED {n.pk} when it's fixed."


def restore_by_text(user, pk, note=""):
    n = Notice.objects.filter(pk=pk).first()
    if n is None or n.status in ("resolved", "cancelled"):
        return f"No open service alert #{pk}."
    told = resolve(n, note=note, actor=user)
    return f"Alert #{n.pk} closed: {n.title}. {told} guest(s) told it's fixed."


def open_list_text():
    notices = list(Notice.objects.filter(status__in=("active", "scheduled"))[:5])
    if not notices:
        return "No open service alerts."
    return "; ".join(f"#{n.pk} {line(n)} at {homes_text(n)}" for n in notices) + ". Text RESTORED <id> when fixed."
