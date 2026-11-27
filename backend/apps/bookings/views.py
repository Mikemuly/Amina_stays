from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.accounts.services import AuthError, get_or_create_user, set_identity
from apps.core.activity import record
from apps.core.api import IsGuest, IsHost
from apps.core.utils import kes, parse_date
from apps.messaging import services as messaging
from apps.payments import services as payments
from apps.payments.providers import PaymentError
from apps.properties.models import Unit

from . import services
from .models import ACTIVE_STATUSES, Addon, Booking, BookingAddon, BookingGuest, ChangeRequest, Waitlist
from .serializers import (
    AddonSerializer,
    BookingCreateSerializer,
    change_dict,
    reservation_row,
    trip_card,
    trip_dict,
    waitlist_entry,
)


def _mine(request, ref, *, lock=False):
    qs = Booking.objects.select_related("unit", "unit__area", "guest")
    if lock:
        qs = qs.select_for_update(no_key=True, of=("self",))
    return get_object_or_404(qs, ref=ref.upper(), guest=request.user)


def _err(e, status=400):
    return Response({"error": str(e)}, status=status)


def _booking_err(e, status=400):
    """A BookingError as {error} - plus its code when it has one (e.g. "available", "unavailable")."""
    code = getattr(e, "code", None)
    return Response({"error": str(e), **({"code": code} if code else {})}, status=status)


def _payment_error(e):
    """{error, failure_code, suggest} for a payment that couldn't start."""
    as_dict = getattr(e, "as_dict", None)
    if callable(as_dict):
        return as_dict()
    return {"error": str(e), "failure_code": getattr(e, "failure_code", None), "suggest": getattr(e, "suggest", None)}


def _truthy(value):
    return value is True or str(value).strip().lower() in ("1", "true", "yes", "on")


# ---------- guest ----------


@api_view(["GET", "POST"])
@permission_classes([IsGuest])
def bookings(request):
    if request.method == "GET":
        qs = (
            Booking.objects.filter(guest=request.user)
            .exclude(status="expired")
            .select_related("unit", "unit__area")
            .prefetch_related("unit__photos")
        )
        return Response([trip_card(b) for b in qs.order_by("-check_in")])
    ser = BookingCreateSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    d = ser.validated_data
    user = request.user
    unit = get_object_or_404(Unit, slug=d["listing"], status="active")
    changed = []
    if d["name"]:
        user.name = d["name"][:80]
        changed.append("name")
    if d["email"]:
        user.email = d["email"]
        changed.append("email")
    if d["lang"] in ("en", "sw", "it", "de", "fr"):
        user.lang = d["lang"]
        changed.append("lang")
    if d["marketing_opt_in"]:
        user.marketing_opt_in = True
        changed.append("marketing_opt_in")
    if changed:
        user.save(update_fields=changed)
    ident = d.get("identity") or {}
    if ident.get("id_number"):
        try:
            set_identity(
                user,
                id_type=ident.get("id_type", ""),
                id_number=ident["id_number"],
                nationality=ident.get("nationality", ""),
                consent=bool(ident.get("consent")),
            )
        except AuthError as e:
            return _err(e)
    try:
        b = services.create_hold(
            unit=unit,
            guest=user,
            check_in=d["check_in"],
            check_out=d["check_out"],
            channel="web",
            adults=d["adults"],
            children=d["children"],
            infants=d["infants"],
            addons=d["addons"],
            payment_plan=d["payment_plan"],
            arrival_eta=d["arrival_eta"],
            arrival_mode=d["arrival_mode"],
            special_requests=d["special_requests"],
            purpose=d["purpose"],
            vehicle_plate=d["vehicle_plate"],
            occupants=d["occupants"],
        )
    except services.BookingError as e:
        return _err(e, 409)
    try:
        pay = payments.start_payment(b, method=d.get("payment_method"))
    except PaymentError as e:
        pay = _payment_error(e)
    return Response({"booking": trip_dict(b), "payment": pay}, status=201)


@api_view(["GET", "PATCH"])
@permission_classes([IsGuest])
def booking_detail(request, ref):
    if request.method == "GET":
        # One consistent trip: a payment being settled (with the change it pays for) holds this booking's row until
        # it commits, so the trip waits for it - or keeps it waiting - rather than mix rows from before and after.
        with transaction.atomic():
            return Response(trip_dict(_mine(request, ref, lock=True)))
    b = _mine(request, ref)
    if request.method == "PATCH":
        d = request.data
        for field, limit in (
            ("arrival_eta", 40),
            ("arrival_mode", 10),
            ("vehicle_plate", 12),
            ("special_requests", 1000),
        ):
            if field in d:
                setattr(
                    b,
                    field,
                    str(d[field] or "")[:limit].strip().upper()
                    if field == "vehicle_plate"
                    else str(d[field] or "")[:limit],
                )
        b.save()
        services.event(b, "arrival", "Arrival details updated", "web")
    return Response(trip_dict(b))


@api_view(["POST"])
@permission_classes([IsGuest])
def pay(request, ref):
    """Pay what's due. plan="deposit" switches a held pay-in-full booking to its deposit first (when the stay allows
    one). Whatever start_payment returns is passed through; a payment that can't start is {error, failure_code,
    suggest} with 400."""
    b = _mine(request, ref)
    plan = "deposit" if request.data.get("plan") == "deposit" and b.payment_plan != "deposit" else None
    amount = request.data.get("amount")
    if amount in (None, "") or plan:
        amount = None
    else:
        # guests may pay more than the minimum but never pick less: a 1-shilling payment must not confirm a hold
        low, high = (
            (b.amount_due_now - b.amount_paid, b.total - b.amount_paid) if b.status == "held" else (1, b.balance_due)
        )
        try:
            amount = int(amount)
        except (TypeError, ValueError):
            return _err("Enter the amount in Kenyan shillings.")
        if high <= 0:
            amount = None  # nothing is due: start_payment says so
        elif not low <= amount <= high:
            return _err(f"Choose an amount between {kes(low)} and {kes(high)}.")
    try:
        extra = {"plan": plan} if plan else {}
        return Response(payments.start_payment(b, method=request.data.get("method"), amount=amount, **extra))
    except PaymentError as e:
        return Response(_payment_error(e), status=400)


@api_view(["GET", "POST"])
@permission_classes([IsGuest])
def cancel(request, ref):
    b = _mine(request, ref)
    if request.method == "GET":
        return Response(services.refund_quote(b))
    try:
        return Response(services.cancel(b, by="guest", reason=str(request.data.get("reason") or "")[:200]))
    except services.BookingError as e:
        return _err(e)


@api_view(["POST"])
@permission_classes([IsGuest])
def add_extra(request, ref):
    b = _mine(request, ref)
    try:
        services.add_addon(
            b,
            request.data.get("code"),
            quantity=request.data.get("quantity"),
            details=request.data.get("details") or {},
            channel="web",
        )
    except services.BookingError as e:
        return _err(e)
    b.refresh_from_db()
    return Response(trip_dict(b))


@api_view(["PUT"])
@permission_classes([IsGuest])
def breakfast(request, ref):
    b = _mine(request, ref)
    d = request.data
    try:
        services.set_breakfast(
            b,
            d.get("style"),
            people=d.get("people"),
            dietary=d.get("dietary", ""),
            time=d.get("time", ""),
            notes=d.get("notes", ""),
            channel="web",
        )
    except services.BookingError as e:
        return _err(e)
    b.refresh_from_db()
    return Response(trip_dict(b))


@api_view(["POST"])
@permission_classes([IsGuest])
def occupants(request, ref):
    b = _mine(request, ref)
    for o in request.data.get("occupants") or []:
        if not o.get("full_name"):
            continue
        bg = BookingGuest(
            booking=b,
            full_name=o["full_name"][:80],
            id_type=o.get("id_type", "")[:20],
            nationality=(o.get("nationality") or "")[:2].upper(),
            is_minor=bool(o.get("is_minor")),
        )
        if o.get("id_number"):
            bg.set_id_number(o["id_number"])
        bg.save()
    services.event(b, "register", "Guest register updated", "web")
    return Response(trip_dict(b))


@api_view(["POST"])
@permission_classes([IsGuest])
def checkout(request, ref):
    b = _mine(request, ref)
    try:
        services.check_out(b, channel="web")
    except services.BookingError as e:
        return _err(e)
    b.refresh_from_db()
    return Response(trip_dict(b))


@api_view(["POST"])
@permission_classes([IsGuest])
def report_issue(request, ref):
    from apps.notices.services import known_issue_text
    from apps.operations.services import classify_issue
    from apps.operations.services import report_issue as report

    b = _mine(request, ref)
    text = (request.data.get("description") or "").strip()
    if not text:
        return _err("Tell us what's wrong.")
    category = request.data.get("category") or None
    known = known_issue_text(b, category or classify_issue(text), "en")  # shown on the (English) website
    if known:  # an outage already announced for this home: no second work order
        return Response({"task": None, "assignee": None, "priority": None, "ticket": None, "known": known})
    task = report(b, text, category=category, channel="web")
    services.notify_host(f"Issue #{task.pk} at {b.unit.name} ({b.guest.display_name}, web): {text[:120]}", booking=b)
    ticket = task.tickets.first()
    return Response(
        {
            "task": task.pk,
            "assignee": task.assignee.name if task.assignee else None,
            "priority": task.priority,
            "ticket": ticket.ref if ticket else None,
            "known": None,
        }
    )


@api_view(["POST"])
@permission_classes([IsGuest])
def sos(request, ref):
    from apps.safety.services import escalate

    _mine(request, ref)
    alert = escalate(request.user.phone, "web", text=(request.data.get("text") or "")[:300])
    return Response({"alert": alert.pk, "call_status": alert.call_status})


@api_view(["POST"])
@permission_classes([IsGuest])
def review(request, ref):
    from apps.reviews.services import record_rating

    b = _mine(request, ref)
    if b.status != "completed":
        return _err("You can review once your stay is complete.")
    if hasattr(b, "review"):
        return _err("You've already reviewed this stay - thank you!")
    d = request.data
    try:
        rating = int(d.get("rating") or 0)
    except (TypeError, ValueError):
        rating = 0
    if not 1 <= rating <= 5:
        return _err("Choose a rating from 1 to 5 stars.")
    record_rating(
        b, rating, channel="web", comment=(d.get("comment") or "")[:2000], categories=d.get("categories") or {}
    )
    b.refresh_from_db()
    return Response(trip_dict(b))


# ---------- waitlist ----------


@api_view(["POST"])
@permission_classes([IsGuest])
def waitlist_join(request):
    d = request.data
    unit = Unit.objects.filter(slug=str(d.get("slug") or ""), status="active").select_related("area").first()
    if unit is None:
        return _err("We couldn't find that home.", 404)
    try:
        adults, children = int(d.get("adults") or 1), int(d.get("children") or 0)
    except (TypeError, ValueError):
        return _err("Choose how many guests are coming.")
    try:
        w, created = services.join_waitlist(
            request.user,
            unit,
            parse_date(d.get("check_in")),
            parse_date(d.get("check_out")),
            adults=adults,
            children=children,
        )
    except services.BookingError as e:
        return _booking_err(e)
    return Response(waitlist_entry(w), status=201 if created else 200)


@api_view(["GET"])
@permission_classes([IsGuest])
def my_waitlist(request):
    return Response([waitlist_entry(w) for w in services.guest_waitlist(request.user)])


@api_view(["DELETE"])
@permission_classes([IsGuest])
def my_waitlist_remove(request, pk):
    get_object_or_404(Waitlist, pk=pk, guest=request.user).delete()
    return Response(status=204)


# ---------- changing a stay ----------


def _change_args(src, b):
    """check_in, check_out, adults, children from a request; anything left out stays as booked."""
    check_in = parse_date(src.get("check_in")) if src.get("check_in") else b.check_in
    check_out = parse_date(src.get("check_out")) if src.get("check_out") else b.check_out
    if check_in is None or check_out is None:
        raise ValueError("bad date")
    adults = b.adults if src.get("adults") in (None, "") else int(src.get("adults"))
    children = b.children if src.get("children") in (None, "") else int(src.get("children"))
    if adults < 0 or children < 0:
        raise ValueError("negative guests")
    return check_in, check_out, adults, children


@api_view(["GET", "POST"])
@permission_classes([IsGuest])
def change(request, ref):
    """GET: price a change (?check_in=&check_out=&adults=&children=). POST: ask for it -> {change, payment, trip}."""
    b = _mine(request, ref)
    try:
        check_in, check_out, adults, children = _change_args(
            request.query_params if request.method == "GET" else request.data, b
        )
    except (TypeError, ValueError):
        return _err("Choose valid dates (YYYY-MM-DD) and numbers of guests.")
    if request.method == "GET":
        return Response(services.change_quote(b, check_in, check_out, adults, children))
    method = request.data.get("method")
    try:
        c, payment = services.request_change(
            b,
            check_in=check_in,
            check_out=check_out,
            adults=adults,
            children=children,
            note=str(request.data.get("note") or ""),
            channel="web",
            method=method if method in ("mpesa", "card") else None,
            actor=request.user,
        )
    except services.BookingError as e:
        return _booking_err(e)
    b.refresh_from_db()
    return Response({"change": change_dict(c), "payment": payment, "trip": trip_dict(b)}, status=201)


@api_view(["POST"])
@permission_classes([IsGuest])
def change_pay(request, ref, pk):
    b = _mine(request, ref)
    c = get_object_or_404(ChangeRequest, pk=pk, booking=b)
    method = request.data.get("method")
    try:
        result = services.pay_change(c, method if method in ("mpesa", "card") else None)
    except services.BookingError as e:
        return _err(e)
    return Response(result, status=400 if result.get("error") else 200)


@api_view(["POST"])
@permission_classes([IsGuest])
def change_cancel(request, ref, pk):
    b = _mine(request, ref)
    c = get_object_or_404(ChangeRequest, pk=pk, booking=b)
    try:
        services.cancel_change(c, actor=request.user)
    except services.BookingError as e:
        return _err(e)
    b.refresh_from_db()
    return Response(trip_dict(b))


# ---------- host ----------


@api_view(["GET", "POST"])
@permission_classes([IsHost])
def host_reservations(request):
    if request.method == "POST":
        return _host_create(request)
    p = request.query_params
    qs = Booking.objects.select_related("unit", "guest").order_by("-created_at")
    if p.get("status"):
        qs = qs.filter(status__in=p["status"].split(","))
    else:
        qs = qs.exclude(status="expired")
    if p.get("channel"):
        qs = qs.filter(channel=p["channel"])
    if p.get("unit"):
        qs = qs.filter(unit_id=p["unit"])
    if p.get("from"):
        qs = qs.filter(check_out__gte=parse_date(p["from"]))
    if p.get("to"):
        qs = qs.filter(check_in__lte=parse_date(p["to"]))
    if p.get("q"):
        q = p["q"].strip()
        qs = qs.filter(
            Q(ref__icontains=q)
            | Q(guest__name__icontains=q)
            | Q(guest__phone__icontains=q)
            | Q(unit__name__icontains=q)
        )
    limit = min(int(p.get("limit") or 200), 500)
    return Response([reservation_row(b) for b in qs[:limit]])


def _host_create(request):
    """Walk-in / phone booking. payment_plan "deposit" charges only the deposit by M-Pesa or card; price_override is
    the accommodation price for the whole stay (levy, VAT and cleaning added as usual) and needs override_reason."""
    from apps.core.models import SiteSettings

    d = request.data
    unit = get_object_or_404(Unit, pk=d.get("unit"))
    plan = "deposit" if d.get("payment_plan") == "deposit" else "full"
    override, reason = d.get("price_override"), str(d.get("override_reason") or "").strip()
    if override in (None, ""):
        override = None
    else:
        try:
            override = int(override)
        except (TypeError, ValueError):
            override = 0
        if override <= 0:
            return _err("Enter the price for the whole stay in KES.")
        if not reason:
            return _err("Say why the price was changed - it goes on the booking's timeline.")
    try:
        guest, _ = get_or_create_user(d.get("phone"), name=d.get("name", ""), channel="walk_in")
        b = services.create_hold(
            unit=unit,
            guest=guest,
            check_in=parse_date(d.get("check_in")),
            check_out=parse_date(d.get("check_out")),
            channel=d.get("channel")
            if d.get("channel") in ("walk_in", "airbnb", "booking_com", "whatsapp")
            else "walk_in",
            adults=int(d.get("adults") or 1),
            children=int(d.get("children") or 0),
            addons=d.get("addons") or [],
            actor=request.user,
            special_requests=d.get("notes", ""),
            payment_plan=plan,
            price_override=override,
            override_reason=reason,
        )
    except (services.BookingError, AuthError) as e:
        return _err(e, 409)
    mode = d.get("payment", "none")
    result = {}
    try:
        if mode == "cash":
            payments.record_manual_payment(b, int(d.get("amount") or b.total), method="cash", actor=request.user)
        elif mode == "mpesa":
            result = payments.start_payment(b, method="mpesa", actor=request.user)  # the deposit on a deposit plan
        elif mode == "card":
            result = payments.start_payment(b, method="card", actor=request.user)
            body = messaging.render(
                "hold_card",
                b.lang,
                **services.guest_context(b),
                amount=kes(result["amount"]),
                minutes=SiteSettings.load().hold_minutes,
                link=result.get("pay_link") or result.get("checkout_url") or "",
            )
            messaging.send(guest.phone, body, booking=b, kind="hold_card")
        else:
            services.confirm(b, actor=request.user)  # pay on arrival
    except PaymentError as e:
        result = _payment_error(e)
    b.refresh_from_db()
    return Response({"booking": trip_dict(b, host=True), "payment": result}, status=201)


@api_view(["GET", "PATCH"])
@permission_classes([IsHost])
def host_reservation(request, ref):
    b = get_object_or_404(Booking.objects.select_related("unit", "unit__area", "guest"), ref=ref.upper())
    if request.method == "PATCH":
        for field in ("host_notes", "arrival_eta", "special_requests", "vehicle_plate", "arrival_mode"):
            if field in request.data:
                value = str(request.data[field] or "")
                limit = Booking._meta.get_field(field).max_length  # None for text fields
                setattr(b, field, value[:limit] if limit else value)
        b.save()
    return Response(trip_dict(b, host=True))


RESENDABLE = (
    "booking_confirmed",
    "pre_arrival",
    "id_request",
    "directions",
    "checkin_code",
    "local_tips",
    "welcome_check",
    "checkout_reminder",
)


@api_view(["POST"])
@permission_classes([IsHost])
def host_action(request, ref, action):
    from apps.payments.models import Payment

    b = get_object_or_404(Booking.objects.select_related("unit", "unit__area", "guest"), ref=ref.upper())
    d, user = request.data, request.user
    try:
        if action == "cancel":
            services.cancel(
                b, by="host", reason=str(d.get("reason") or ""), actor=user, refund_amount=d.get("refund_amount")
            )
        elif action == "record-payment":
            try:
                amount = int(d.get("amount") or b.balance_due)
            except (TypeError, ValueError):
                amount = 0
            method = d.get("method") or "cash"
            if b.status not in (*ACTIVE_STATUSES, "completed"):
                return _err("This booking can't take payments.")
            if amount <= 0:
                return _err("Enter the amount received.")
            if method not in dict(Payment.METHODS):
                return _err("Choose cash, bank transfer, M-Pesa or card.")
            payments.record_manual_payment(
                b, amount, method=method, reference=str(d.get("reference") or ""), actor=user
            )
        elif action == "request-payment":
            result = payments.start_payment(b, method=d.get("method"), amount=d.get("amount"), actor=user)
            link = result.get("pay_link") or result.get("checkout_url")
            if result.get("method") == "card" and link:  # M-Pesa prompts itself; a card link must be sent
                services.send_guest(b, "pay_link", amount=kes(result["amount"]), link=link)
        elif action == "release-code":
            state = services.release_code(b, force=bool(d.get("force", True)), actor=user)
            if state != "released":
                return _err(f"Code not released: {state.replace('_', ' ')}")
        elif action == "check-out":
            services.check_out(b, by="host", channel="console", actor=user)
        elif action == "confirm":
            if b.status not in ("held", "confirmed"):
                return _err(f"This booking is {b.get_status_display().lower()} and can't be confirmed.")
            services.confirm(b, actor=user)
        elif action == "resend":
            key = d.get("template") or "booking_confirmed"
            if key not in RESENDABLE:
                return _err("That message can't be resent from here.")
            if b.status not in ("confirmed", "checked_in"):
                return _err("Messages can be resent once the booking is confirmed.")
            if (
                key == "checkin_code"
                and not b.access_codes.filter(revoked_at__isnull=True, sent_at__isnull=False).exists()
            ):
                return _err("The door code hasn't been released yet.")
            note = messaging.render("balance_note", b.lang, **services.guest_context(b)) if b.balance_due else ""
            # Amina resending chooses to share: directions and Wi-Fi go out even before the 48-hour reveal
            services.send_guest(b, key, reveal=True, balance_note=f" {note}" if note else "")
        elif action == "verify-id":
            b.guest.id_verified_at = timezone.now()
            b.guest.save(update_fields=["id_verified_at"])
            services.event(b, "register", "ID verified in person", actor=user)
        elif action == "message":
            from apps.comms.smsbot import reply_as_host

            text = str(d.get("text") or "").strip()
            if not text:
                return _err("Write a message first.")
            reply_as_host(b.guest.phone, text[:600], user=user)
        else:
            return _err("Unknown action.", 404)
    except PaymentError as e:
        return Response(_payment_error(e), status=400)
    except services.BookingError as e:
        return _err(e)
    record("booking", f"{action.replace('-', ' ').capitalize()} on {b.ref}", booking=b, actor=user)
    b.refresh_from_db()
    return Response(trip_dict(b, host=True))


@api_view(["POST"])
@permission_classes([IsHost])
def decide_request(request, pk):
    ba = get_object_or_404(BookingAddon.objects.select_related("booking", "addon"), pk=pk)
    services.decide_addon(ba, bool(request.data.get("approve")), actor=request.user)
    return Response(trip_dict(ba.booking, host=True))


@api_view(["POST"])
@permission_classes([IsHost])
def decide_change(request, pk):
    c = get_object_or_404(ChangeRequest.objects.select_related("booking"), pk=pk)
    try:
        services.decide_change(c, _truthy(request.data.get("approve")), actor=request.user)
    except services.BookingError as e:
        return _booking_err(e)
    b = Booking.objects.select_related("unit", "unit__area", "guest").get(pk=c.booking_id)
    return Response(trip_dict(b, host=True))


def _stay(adults, children, check_in, check_out):
    return {"check_in": check_in, "check_out": check_out, "adults": adults, "children": children}


@api_view(["GET"])
@permission_classes([IsHost])
def pending_requests(request):
    """Extras and date changes waiting for Amina's yes or no (kind "addon" | "change"), oldest first."""
    rows = BookingAddon.objects.filter(status="requested", booking__status__in=ACTIVE_STATUSES).select_related(
        "booking", "booking__guest", "booking__unit", "addon"
    )
    items = [
        {
            "id": r.pk,
            "kind": "addon",
            "addon": r.addon.name,
            "code": r.addon.code,
            "ref": r.booking.ref,
            "unit": r.booking.unit.name,
            "guest": r.booking.guest.display_name,
            "details": r.details,
            "total": r.total,
            "created_at": r.created_at,
        }
        for r in rows
    ]
    changes = ChangeRequest.objects.filter(status="pending_host", booking__status__in=ACTIVE_STATUSES).select_related(
        "booking", "booking__guest", "booking__unit"
    )
    items += [
        {
            "id": c.pk,
            "kind": "change",
            "addon": "Date change",
            "code": "change",
            "ref": c.booking.ref,
            "unit": c.booking.unit.name,
            "guest": c.booking.guest.display_name,
            "details": {"note": c.note},
            "total": c.delta,
            "created_at": c.created_at,
            "change": {
                "old": _stay(c.old_adults, c.old_children, c.old_check_in, c.old_check_out),
                "new": _stay(c.new_adults, c.new_children, c.new_check_in, c.new_check_out),
                "delta": c.delta,
                "refund_amount": c.refund_amount,
            },
        }
        for c in changes
    ]
    return Response(sorted(items, key=lambda x: x["created_at"]))


class HostAddonViewSet(viewsets.ModelViewSet):
    permission_classes = [IsHost]
    serializer_class = AddonSerializer
    queryset = Addon.objects.prefetch_related("units").all()
