from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.core.api import IsHost
from apps.messaging import services as messaging
from apps.properties.models import Unit

from . import services
from .models import Notice


def notice_dict(n):
    units = [{"id": u.pk, "name": u.name} for u in n.units.all()]
    return {
        "id": n.pk,
        "kind": n.kind,
        "kind_label": n.get_kind_display(),
        "service": n.service,
        "service_label": n.get_service_display(),
        "status": n.status,
        "status_label": n.get_status_display(),
        "title": n.title,
        "message": n.message,
        "units": units,
        "all_homes": not units,
        "starts_at": n.starts_at,
        "expected_end": n.expected_end,
        "resolved_at": n.resolved_at,
        "resolution": n.resolution,
        "data_mb": n.data_mb,
        "notified": n.notified,
        "source": n.source,
        "created_by": n.created_by.display_name if n.created_by_id else None,
        "created_at": n.created_at,
    }


def public_dict(n):
    return {
        k: v
        for k, v in notice_dict(n).items()
        if k
        in (
            "id",
            "kind",
            "kind_label",
            "service",
            "service_label",
            "status",
            "title",
            "message",
            "starts_at",
            "expected_end",
        )
    }


def _when(value, label):
    if value in (None, ""):
        return None
    dt = parse_datetime(str(value))
    if dt is None:
        raise ValueError(f"{label}: use a date and time like 2026-12-01T09:00.")
    return timezone.make_aware(dt) if timezone.is_naive(dt) else dt


def _form(data):
    """Validate a new-alert form. Returns (fields, error)."""
    kind = data.get("kind") or "outage"
    service = data.get("service")
    if kind not in dict(Notice.KINDS):
        return None, "Pick outage, planned maintenance or advisory."
    if service not in dict(Notice.SERVICES):
        return None, "Pick the service that's affected."
    try:
        starts_at = _when(data.get("starts_at"), "Start")
        expected_end = _when(data.get("expected_end"), "Expected end")
    except ValueError as e:
        return None, str(e)
    if kind == "maintenance" and not starts_at:
        return None, "Planned maintenance needs a start time."
    if expected_end and expected_end <= (starts_at or timezone.now()):
        return None, "The expected end must be after the start."
    ids = [int(i) for i in data.get("unit_ids") or [] if str(i).isdigit()]
    units = list(Unit.objects.filter(pk__in=ids))
    if len(units) != len(set(ids)):
        return None, "One of those homes doesn't exist."
    try:
        data_mb = None if data.get("data_mb") in (None, "") else max(0, int(data.get("data_mb")))
    except (TypeError, ValueError):
        return None, "Data bundle: a number of MB."
    title = (data.get("title") or "").strip()[:100]
    message = (data.get("message") or "").strip()
    if len(message) > 300:
        return None, "Keep the message under 300 characters: it goes out by SMS."
    if (err := messaging.placeholder_error(message)) is not None:
        return None, err
    return {
        "kind": kind,
        "service": service,
        "title": title,
        "message": message,
        "units": units,
        "starts_at": starts_at,
        "expected_end": expected_end,
        "data_mb": data_mb,
    }, None


@api_view(["GET", "POST"])
@permission_classes([IsHost])
def notices(request):
    from apps.rewards.models import Program

    if request.method == "POST":
        fields, error = _form(request.data)
        if error:
            return Response({"error": error}, status=400)
        n = services.create(**fields, source="host", actor=request.user)
        return Response(notice_dict(n), status=201)
    status = request.query_params.get("status", "current")
    qs = Notice.objects.prefetch_related("units").select_related("created_by")
    if status == "current":
        qs = qs.filter(status__in=("active", "scheduled"))
    elif status == "resolved":
        qs = qs.filter(status__in=("resolved", "cancelled"))
    return Response(
        {
            "notices": [notice_dict(n) for n in qs[:100]],
            "services": Notice.SERVICES,
            "kinds": Notice.KINDS,
            "default_data_mb": Program.load().outage_data_mb,
            "data_services": sorted(services.DATA_SERVICES),
        }
    )


@api_view(["POST"])
@permission_classes([IsHost])
def preview(request):
    """How many guests a new alert would reach, and the SMS the first of them would get."""
    fields, error = _form(request.data)
    if error:
        return Response({"error": error}, status=400)
    probe = Notice(
        kind=fields["kind"],
        service=fields["service"],
        title=fields["title"] or services.default_title(fields["kind"], fields["service"]),
        message=fields["message"],
        starts_at=fields["starts_at"] or timezone.now(),
        expected_end=fields["expected_end"],
        status="scheduled" if fields["starts_at"] and fields["starts_at"] > timezone.now() else "active",
    )
    ids = [u.pk for u in fields["units"]]
    audience = services.affected_by_plan if probe.status == "scheduled" else services.affected_now
    stays = audience(_Probe(probe, ids))
    if stays:
        unit_name = stays[0].unit.name
    elif fields["units"]:
        unit_name = fields["units"][0].name
    else:
        unit_name = Unit.objects.order_by("name").values_list("name", flat=True).first() or "your home"
    key = "notice_heads_up" if probe.status == "scheduled" else "notice_active"
    mb = fields["data_mb"]
    if mb is None:
        from apps.rewards.models import Program

        mb = Program.load().outage_data_mb if probe.kind == "outage" and probe.service in services.DATA_SERVICES else 0
    data_line = (
        " " + messaging.render("notice_data_line", "en", mb=mb)
        if mb and probe.service in services.DATA_SERVICES and probe.status == "active"
        else ""
    )
    sms = messaging.render(
        key,
        "en",
        unit=unit_name,
        title=probe.title,
        message=services.said(probe.message),
        eta=services.eta_text(probe),
        when=services.when_text(probe.starts_at),
        data_line=data_line,
    )
    return Response({"guests": len(stays), "sms": sms, "segments": messaging.sms_segments(messaging.to_gsm(sms))})


class _Probe:
    """An unsaved notice that answers .units like a saved one (for the preview)."""

    def __init__(self, notice, unit_ids):
        self._n, self._ids = notice, unit_ids

    def __getattr__(self, name):
        return getattr(self._n, name)

    @property
    def units(self):
        return Unit.objects.filter(pk__in=self._ids)


@api_view(["POST"])
@permission_classes([IsHost])
def notice_action(request, pk, action):
    n = get_object_or_404(Notice, pk=pk)
    if action == "resolve":
        if n.status in ("resolved", "cancelled"):
            return Response({"error": "This alert is already closed."}, status=400)
        services.resolve(n, note=request.data.get("note", ""), actor=request.user)
    elif action == "cancel":
        if n.status != "scheduled":
            return Response(
                {"error": "Only planned work that hasn't started can be cancelled - resolve it instead."}, status=400
            )
        services.cancel(n, actor=request.user)
    elif action == "update":
        if n.status not in ("active", "scheduled"):
            return Response({"error": "This alert is already closed."}, status=400)
        try:
            end = _when(request.data.get("expected_end"), "Expected end")
        except ValueError as e:
            return Response({"error": str(e)}, status=400)
        message = request.data.get("message")
        if message is not None and (err := messaging.placeholder_error(message)) is not None:
            return Response({"error": err}, status=400)
        if end and end <= timezone.now():
            return Response({"error": "The new expected end must be in the future."}, status=400)
        services.update(n, message=message, expected_end=end, actor=request.user)
    else:
        return Response({"error": "Unknown action - use update, resolve or cancel."}, status=400)
    n.refresh_from_db()
    return Response(notice_dict(n))


@api_view(["GET"])
def unit_notices(request):
    """What a guest at one home should know right now (trip and listing pages)."""
    unit = Unit.objects.filter(slug=request.query_params.get("unit", "")).first()
    if unit is None:
        return Response([])
    return Response([public_dict(n) for n in services.current_for_unit(unit)])
