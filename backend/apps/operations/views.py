from django.shortcuts import get_object_or_404
from rest_framework import serializers, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from apps.accounts.models import ROLES, User
from apps.core.api import STAFF_ROLES, IsHost
from apps.core.utils import normalize_phone, parse_date, today
from apps.properties.models import Unit

from . import services
from .models import Task


class TaskSerializer(serializers.ModelSerializer):
    unit_name = serializers.CharField(source="unit.name", read_only=True, default=None)
    assignee_name = serializers.CharField(source="assignee.display_name", read_only=True, default=None)
    booking_ref = serializers.CharField(source="booking.ref", read_only=True, default=None)
    type_label = serializers.CharField(source="get_type_display", read_only=True)

    class Meta:
        model = Task
        fields = "__all__"
        read_only_fields = ["created_by", "created_at", "started_at", "completed_at", "source"]


class TaskViewSet(viewsets.ModelViewSet):
    permission_classes = [IsHost]
    serializer_class = TaskSerializer

    def get_queryset(self):
        qs = Task.objects.select_related("unit", "assignee", "booking")
        status = self.request.query_params.get("status")
        if status == "open":
            qs = qs.filter(status__in=("open", "in_progress"))
        elif status:
            qs = qs.filter(status=status)
        return qs.order_by("status", "due_at", "-id")

    def list(self, request, *args, **kwargs):
        # Cap the board here: slicing get_queryset() would break the detail routes (DRF filters it by pk).
        tasks = self.filter_queryset(self.get_queryset())[:300]
        return Response(self.get_serializer(tasks, many=True).data)

    def perform_create(self, serializer):
        task = serializer.save(created_by=self.request.user, source="host")
        if task.type == "turnover" and not task.checklist:
            task.checklist = [{"item": i, "done": False} for i in services.DEFAULT_CHECKLIST]
            task.save(update_fields=["checklist"])
        services.notify_assignee(task)

    def perform_update(self, serializer):
        before = self.get_object().assignee_id
        task = serializer.save()
        if task.assignee_id and task.assignee_id != before:
            services.notify_assignee(task)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        return Response(
            TaskSerializer(services.complete_task(self.get_object(), request.user, request.data.get("note", ""))).data
        )

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        return Response(TaskSerializer(services.start_task(self.get_object(), request.user)).data)


class StaffSerializer(serializers.ModelSerializer):
    # declared (not the model's unique field) so a former staff member or a guest can be (re-)added: create() reuses the account
    phone = serializers.CharField(max_length=20)
    unit_ids = serializers.PrimaryKeyRelatedField(
        source="assigned_units", many=True, required=False, queryset=Unit.objects.all()
    )
    open_tasks = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "phone", "name", "role", "lang", "is_active", "unit_ids", "open_tasks"]

    def get_open_tasks(self, obj):
        return obj.tasks.filter(status__in=("open", "in_progress")).count()

    def validate_phone(self, value):
        phone = normalize_phone(value)
        if not phone:
            raise serializers.ValidationError("Enter a valid phone number.")
        other = User.objects.filter(phone=phone).exclude(pk=getattr(self.instance, "pk", None)).first()
        if other and (self.instance is not None or other.role == "owner"):
            raise serializers.ValidationError("This number already belongs to someone else.")
        return phone

    def validate_role(self, value):
        if value not in STAFF_ROLES:
            raise serializers.ValidationError("Choose a staff role.")
        return value

    def create(self, validated):
        units = validated.pop("assigned_units", [])
        user, _ = User.objects.get_or_create(phone=validated["phone"])
        for k, v in validated.items():
            setattr(user, k, v)
        user.save()
        user.assigned_units.set(units)
        return user


class StaffViewSet(viewsets.ModelViewSet):
    permission_classes = [IsHost]
    serializer_class = StaffSerializer

    def get_queryset(self):
        return User.objects.filter(role__in=STAFF_ROLES).prefetch_related("assigned_units").order_by("role", "name")

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        if user == request.user:
            return Response({"error": "You can't remove yourself."}, status=400)
        user.role, user.is_active = "guest", True
        user.save(update_fields=["role", "is_active"])
        user.assigned_units.clear()
        return Response(status=204)


@api_view(["GET"])
@permission_classes([IsHost])
def roles(request):
    return Response([{"value": v, "label": label} for v, label in ROLES if v != "guest"])


# ---------- guest CRM ----------


def _guest_row(u):
    return {
        "id": u.pk,
        "phone": u.phone,
        "name": u.name,
        "email": u.email,
        "lang": u.lang,
        "nationality": u.nationality,
        "tags": u.tags,
        "blocked": u.is_blocked,
        "first_channel": u.first_channel,
        "marketing_opt_in": u.marketing_opt_in,
        "opted_out": bool(u.sms_opt_out_at),
        "id_registered": bool(u.id_last4),
        "stays": getattr(u, "stays", None),
        "spend": getattr(u, "spend", None) or 0,
        "last_stay": getattr(u, "last_stay", None),
        "joined": u.date_joined,
    }


@api_view(["GET"])
@permission_classes([IsHost])
def guests(request):
    from django.db.models import Count, Max, Q, Sum

    live = Q(bookings__status__in=("confirmed", "checked_in", "completed"))
    qs = User.objects.filter(role="guest").annotate(
        stays=Count("bookings", filter=live, distinct=True),
        spend=Sum("bookings__amount_paid", filter=live),
        last_stay=Max("bookings__check_in", filter=live),
    )
    q = request.query_params.get("q")
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(phone__icontains=q) | Q(email__icontains=q))
    if request.query_params.get("filter") == "blocked":
        qs = qs.filter(is_blocked=True)
    elif request.query_params.get("filter") == "returning":
        qs = qs.filter(stays__gte=2)
    return Response([_guest_row(u) for u in qs.order_by("-last_stay", "-date_joined")[:300]])


@api_view(["GET", "PATCH"])
@permission_classes([IsHost])
def guest_detail(request, pk):
    from apps.bookings.serializers import trip_card
    from apps.core.activity import record

    u = get_object_or_404(User, pk=pk)
    if request.method == "PATCH":
        d = request.data
        for field in ("name", "email", "nationality", "host_notes", "block_reason", "lang"):
            if field in d:
                setattr(u, field, str(d[field] or ""))
        if "tags" in d and isinstance(d["tags"], list):
            u.tags = [str(t)[:24] for t in d["tags"]][:12]
        if "is_blocked" in d:
            u.is_blocked = bool(d["is_blocked"])
            record(
                "guest",
                f"{u.display_name} {'added to' if u.is_blocked else 'removed from'} the do-not-host list",
                actor=request.user,
            )
        u.save()
    from apps.messaging.models import Thread

    thread = Thread.objects.filter(phone=u.phone).first()
    return Response(
        {
            **_guest_row(u),
            "notes": u.host_notes,
            "block_reason": u.block_reason,
            "identity": {
                "type": u.get_id_type_display() if u.id_type else "",
                "last4": u.id_last4,
                "verified": bool(u.id_verified_at),
            },
            "bookings": [
                trip_card(b)
                for b in u.bookings.exclude(status="expired").select_related("unit", "unit__area").order_by("-check_in")
            ],
            "thread_id": thread.pk if thread else None,
            "reviews": [
                {"ref": r.booking.ref, "rating": r.rating, "comment": r.comment}
                for r in u.reviews.select_related("booking")
            ],
        }
    )


@api_view(["GET", "POST"])
@permission_classes([IsHost])
def kitchen(request):
    day = parse_date(request.query_params.get("date") or request.data.get("date")) or today()
    if request.method == "POST":
        text = services.kitchen_sheet_text(day)
        if not text:
            return Response({"error": "No breakfasts booked for that morning."}, status=400)
        from apps.messaging import services as messaging

        cooks = list(User.objects.filter(role="cook", is_active=True)) or [get_object_or_404(User, pk=request.user.pk)]
        for c in cooks:
            messaging.send(c.phone, text, kind="kitchen_sheet", user=request.user)
        return Response({"sent_to": [c.display_name for c in cooks]})
    rows = services.kitchen_sheet(day)
    return Response(
        {"date": day, "rows": rows, "people": sum(r["people"] for r in rows), "text": services.kitchen_sheet_text(day)}
    )
