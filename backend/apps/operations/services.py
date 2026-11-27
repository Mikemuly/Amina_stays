"""Housekeeping, maintenance, kitchen and gate operations — the work behind a good review.

Cleaning is hosts' #1 time sink (PriceLabs 2025), and coastal staff often carry feature phones,
so every task can be run entirely by SMS: assignment texts, 'DONE 12' to close, 'TASKS' to list.
"""

import re
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.core.activity import record
from apps.core.models import SiteSettings
from apps.core.utils import at_local, nice_date, nice_time, today
from apps.messaging import services as messaging

from .models import Task

DEFAULT_CHECKLIST = [
    "Strip beds, fresh linen and towels",
    "Bathroom and kitchen deep clean",
    "Sweep and mop, empty bins",
    "Restock water, toilet paper, soap, tea and coffee",
    "Check AC remote, lights, Wi-Fi router, keypad battery",
    "Mosquito nets intact, windows closed",
    "Photo of each room when finished",
]
ROLE_FOR_TYPE = {
    "turnover": "cleaner",
    "laundry": "cleaner",
    "restock": "cleaner",
    "maintenance": "caretaker",
    "inspection": "caretaker",
    "guest_request": "caretaker",
    "other": "manager",
}
ISSUE_KEYWORDS = [
    ("security", r"thief|stolen|steal|intruder|break.?in|robb|attack|unsafe|mwizi|wezi|kuibiwa"),
    ("lock", r"lock(ed)? out|can'?t (get|open)|door|keypad|code (not|doesn)|key|mlango|ufunguo"),
    ("water", r"no water|water|maji|shower (cold|not)|hot water"),
    ("power", r"power|blackout|electric|no light|stima|umeme|generator|token"),
    ("plumbing", r"leak|toilet|blocked|flood|sink|drain|pipe|choo"),
    ("wifi", r"wi-?fi|internet|router|network|mtandao"),
    ("ac", r"\bac\b|air ?con|aircon|fan|too hot|joto|feni"),
    ("pests", r"cockroach|bed ?bug|mosquito|rat|mouse|ants|mende|mbu|panya"),
    ("cleanliness", r"dirty|smell|stain|not clean|chafu|harufu|towel|sheet"),
    ("noise", r"noise|loud|music|party|kelele"),
    ("appliance", r"fridge|tv|cooker|stove|gas|microwave|kettle|iron|washing|friji"),
]
URGENT = {"security", "lock"}
HIGH = {"water", "power", "plumbing"}


def classify_issue(text):
    low = (text or "").lower()
    for category, pattern in ISSUE_KEYWORDS:
        if re.search(pattern, low):
            return category
    return "other"


def looks_like_issue(text):
    low = (text or "").lower()
    return bool(
        re.search(
            r"broken|not working|doesn'?t work|isn'?t working|problem|issue|blackout|leak|locked out|"
            r"\bno (hot )?water\b|\bno (power|electricity|lights?|wi-?fi|internet|network)\b|"
            r"\b(wi-?fi|internet|network) (is )?down\b|\bpower (is )?(out|off|cut)\b|"
            r"cockroach|bed ?bug|dirty|stopped|imeharibika|haifanyi|tatizo|"
            r"hakuna (maji|stima|umeme|wi-?fi|mtandao|internet)",
            low,
        )
    )


def staff_for(role, unit=None):
    from apps.accounts.models import User

    qs = User.objects.filter(role=role, is_active=True)
    if unit is not None:
        first = qs.filter(assigned_units=unit).first()
        if first:
            return first
    return qs.first()


def notify_assignee(task):
    if not task.assignee:
        return
    unit_line = f" at {task.unit.name}" if task.unit else ""
    due = (
        f"{nice_date(timezone.localtime(task.due_at).date())} {nice_time(timezone.localtime(task.due_at).strftime('%H:%M'))}"
        if task.due_at
        else "today"
    )
    messaging.send(
        task.assignee.phone,
        messaging.render("staff_task", task.assignee.lang, id=task.pk, title=task.title, unit_line=unit_line, due=due),
        kind="staff_task",
        sender="system",
    )


def create_task(
    type,
    title,
    *,
    unit=None,
    booking=None,
    priority="normal",
    description="",
    category="",
    due_at=None,
    source="host",
    assignee=None,
    actor=None,
    notify=True,
    checklist=None,
):
    if assignee is None:
        role = ROLE_FOR_TYPE.get(type, "manager")
        assignee = staff_for(role, unit) or staff_for("caretaker", unit) or staff_for("manager")
    task = Task.objects.create(
        type=type,
        title=title[:140],
        unit=unit,
        booking=booking,
        priority=priority,
        description=description,
        category=category,
        due_at=due_at,
        source=source,
        assignee=assignee,
        created_by=actor if getattr(actor, "pk", None) else None,
        checklist=[
            {"item": i, "done": False}
            for i in (checklist if checklist is not None else (DEFAULT_CHECKLIST if type == "turnover" else []))
        ],
    )
    if notify:
        notify_assignee(task)
    record(
        "task",
        f"Task #{task.pk}: {task.title}{' -> ' + task.assignee.display_name if task.assignee else ''}",
        booking=booking,
        actor=actor,
    )
    return task


def create_turnover_task(booking):
    from apps.bookings.models import Booking
    from apps.bookings.services import effective_checkin_time

    unit = booking.unit
    nxt = (
        Booking.objects.filter(unit=unit, status__in=("confirmed", "held"), check_in__gte=today())
        .order_by("check_in")
        .first()
    )
    same_day = nxt is not None and nxt.check_in == today()
    due = (
        at_local(today(), effective_checkin_time(nxt)) - timedelta(hours=1)
        if same_day
        else timezone.now() + timedelta(hours=4)
    )
    title = f"Turnover clean - {unit.name}" + (
        f" (next guest {nice_time(effective_checkin_time(nxt))} today)" if same_day else ""
    )
    return create_task(
        "turnover",
        title,
        unit=unit,
        booking=booking,
        priority="high" if same_day else "normal",
        due_at=due,
        source="auto",
    )


def report_issue(booking, text, *, category=None, channel="sms", unit=None):
    """A guest reported a problem: open a work order, tell the right person, acknowledge the guest."""
    from apps.bookings.services import send_guest

    category = category or classify_issue(text)
    priority = "urgent" if category in URGENT else "high" if category in HIGH else "normal"
    label = dict(Task.CATEGORIES).get(category, "Issue")
    unit = unit or (booking.unit if booking else None)
    task = create_task(
        "maintenance" if category != "cleanliness" else "guest_request",
        f"{label}: {text[:90]}",
        unit=unit,
        booking=booking,
        priority=priority,
        description=text,
        category=category,
        source="guest",
        due_at=timezone.now() + timedelta(hours=1 if priority != "normal" else 6),
    )
    if booking:
        from apps.support.services import open_for_issue

        open_for_issue(task, booking, text, channel)  # on the support desk too, closed with the work order
    if category in URGENT and booking:
        from apps.safety.services import raise_alert

        raise_alert(
            "urgent_issue",
            f"{label} reported at {unit.name} by {booking.guest.display_name}: {text[:120]}",
            severity="high",
            booking=booking,
            source=channel,
        )
    if booking:
        send_guest(
            booking,
            "issue_logged",
            task=task.pk,
            assignee=task.assignee.name.split(" ")[0] if task.assignee and task.assignee.name else "our caretaker",
        )
    return task


def start_task(task, by=None):
    if task.status == "open":
        task.status, task.started_at = "in_progress", timezone.now()
        task.save(update_fields=["status", "started_at"])
        if task.type == "turnover" and task.unit:
            task.unit.housekeeping = "cleaning"
            task.unit.save(update_fields=["housekeeping"])
        from apps.support.services import task_started

        task_started(task)
    return task


def complete_task(task, by=None, note=""):
    from apps.bookings.services import send_guest

    if task.status in ("done", "cancelled"):
        return task
    task.status, task.completed_at, task.completion_note = "done", timezone.now(), note[:300]
    task.checklist = [{**c, "done": True} for c in task.checklist]
    task.save(update_fields=["status", "completed_at", "completion_note", "checklist"])
    if task.type == "turnover" and task.unit:
        task.unit.housekeeping = "clean"
        task.unit.save(update_fields=["housekeeping"])
    from apps.support.services import task_done

    task_done(task)
    if task.source == "guest" and task.booking and task.booking.status == "checked_in":
        send_guest(task.booking, "issue_fixed", task=task.pk, title=task.title.split(":")[0])
    record(
        "task",
        f"Task #{task.pk} done{' by ' + by.display_name if getattr(by, 'pk', None) else ''}: {task.title}",
        booking=task.booking,
    )
    return task


def open_tasks_for(user):
    return (
        Task.objects.filter(assignee=user, status__in=("open", "in_progress"))
        .select_related("unit")
        .order_by("due_at", "id")
    )


# ---------- kitchen ----------


def kitchen_sheet(day=None):
    """Breakfasts served on the morning of `day` (guests who slept there the night before)."""
    from apps.bookings.models import BookingAddon
    from apps.bookings.services import BREAKFAST_STYLES

    day = day or today()
    rows = (
        BookingAddon.objects.filter(addon__code="breakfast", status__in=("confirmed", "fulfilled"))
        .filter(booking__status__in=("confirmed", "checked_in"), booking__check_in__lt=day, booking__check_out__gte=day)
        .select_related("booking", "booking__unit", "booking__guest")
        .order_by("details__time", "booking__unit__name")
    )
    return [
        {
            "ref": r.booking.ref,
            "unit": r.booking.unit.name,
            "guest": r.booking.guest.display_name,
            "people": r.quantity,
            "style": r.details.get("style", ""),
            "style_label": BREAKFAST_STYLES.get(r.details.get("style"), "Breakfast"),
            "dietary": r.details.get("dietary", ""),
            "time": r.details.get("time", "08:00"),
            "notes": r.details.get("notes", ""),
        }
        for r in rows
    ]


def kitchen_sheet_text(day=None):
    day = day or today()
    rows = kitchen_sheet(day)
    if not rows:
        return None
    lines = "; ".join(
        f"{r['time']} {r['unit']}: {r['people']}x {r['style_label'].split(' (')[0]}{' (' + r['dietary'] + ')' if r['dietary'] else ''}"
        for r in rows
    )
    return messaging.render("kitchen_sheet", "en", date=nice_date(day), lines=lines)


def send_kitchen_sheet(day=None):
    from apps.accounts.models import User

    day = day or today() + timedelta(days=1)
    text = kitchen_sheet_text(day)
    if not text:
        return 0
    cooks = list(User.objects.filter(role="cook", is_active=True)) or []
    targets = [c.phone for c in cooks] or [SiteSettings.load().host_contact]
    for phone in targets:
        messaging.send(phone, text, kind="kitchen_sheet")
    return len(targets)


# ---------- gate (PSRA visitor-log directive) ----------


def gate_list(day=None):
    from apps.bookings.models import Booking

    day = day or today()
    return list(
        Booking.objects.filter(check_in=day, status__in=("confirmed", "checked_in"))
        .select_related("unit", "guest")
        .order_by("unit__name")
    )


def send_gate_list(day=None):
    from apps.accounts.models import User

    day = day or today()
    arrivals = gate_list(day)
    guards = list(User.objects.filter(role="security", is_active=True))
    if not arrivals or not guards:
        return 0
    lines = "; ".join(
        f"{b.unit.name}: {b.guest.display_name}, {b.guests_count} guest(s){', car ' + b.vehicle_plate if b.vehicle_plate else ''}{', ETA ' + b.arrival_eta if b.arrival_eta else ''}"
        for b in arrivals
    )
    for g in guards:
        messaging.send(
            g.phone, messaging.render("gate_list", g.lang, date=nice_date(day), lines=lines), kind="gate_list"
        )
    return len(guards)


# ---------- the host's morning digest ----------


def digest_numbers(day=None):
    from apps.bookings.models import Booking
    from apps.insights.services import occupancy
    from apps.messaging.models import Thread
    from apps.safety.models import Alert

    day = day or today()
    week_start = day - timedelta(days=day.weekday())
    return {
        "arrivals": Booking.objects.filter(check_in=day, status__in=("confirmed", "checked_in")).count(),
        "departures": Booking.objects.filter(check_out=day, status__in=("checked_in", "completed")).count(),
        "in_house": Booking.objects.filter(status="checked_in").count(),
        "breakfasts": sum(r["people"] for r in kitchen_sheet(day)),
        "tasks": Task.objects.filter(status__in=("open", "in_progress")).count(),
        "unread": Thread.objects.filter(needs_reply=True).count(),
        "alerts": Alert.objects.filter(~Q(status="resolved")).count(),
        "occ": occupancy(week_start, week_start + timedelta(days=7))["occupancy"],
    }


def send_host_digest():
    s = SiteSettings.load()
    return messaging.send(
        s.host_contact, messaging.render("host_digest", "en", host=s.host_name, **digest_numbers()), kind="host_digest"
    )
