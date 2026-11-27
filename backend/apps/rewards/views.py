from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.core.api import IsGuest, IsHost
from apps.core.utils import is_kenyan, normalize_phone

from . import services
from .models import Member, Payout, Program


class ProgramSerializer(serializers.ModelSerializer):
    class Meta:
        model = Program
        fields = [
            "enabled",
            "points_per_100",
            "review_points",
            "referral_airtime",
            "referee_airtime",
            "redeem_points",
            "redeem_airtime",
            "redeem_data_mb",
            "outage_data_mb",
            "monthly_airtime_budget",
        ]
        extra_kwargs = {
            "redeem_points": {"min_value": 1},
            "redeem_airtime": {"max_value": 1000},
            "referral_airtime": {"max_value": 1000},
            "referee_airtime": {"max_value": 1000},
            "redeem_data_mb": {"max_value": 5000},
            "outage_data_mb": {"max_value": 5000},
        }


def payout_dict(p):
    return {
        "id": p.pk,
        "kind": p.kind,
        "kind_label": p.get_kind_display(),
        "amount": p.amount,
        "amount_text": p.amount_text,
        "reason": p.reason,
        "reason_label": p.get_reason_display(),
        "phone": p.phone,
        "guest": p.user.display_name if p.user_id else None,
        "booking": p.booking.ref if p.booking_id else None,
        "note": p.note,
        "status": p.status,
        "status_label": p.get_status_display(),
        "error": p.error,
        "created_at": p.created_at,
        "completed_at": p.completed_at,
    }


# ---------- guests ----------


@api_view(["GET"])
@permission_classes([IsGuest])
def my_rewards(request):
    return Response(services.guest_dict(request.user))


@api_view(["POST"])
@permission_classes([IsGuest])
def my_redeem(request):
    kind = request.data.get("kind")
    if kind not in ("airtime", "data"):
        return Response({"error": "Choose airtime or data."}, status=400)
    payout, message = services.redeem(request.user, kind, lang="en")  # the website is in English
    if payout is None:
        return Response({"error": message}, status=400)
    return Response({**services.guest_dict(request.user), "message": message, "payout": payout_dict(payout)})


@api_view(["POST"])
@permission_classes([IsGuest])
def my_referral(request):
    ok, message = services.apply_referral(request.user, request.data.get("code", ""), lang="en")
    if not ok:
        return Response({"error": message}, status=400)
    return Response({**services.guest_dict(request.user), "message": message})


# ---------- host console ----------


@api_view(["GET"])
@permission_classes([IsHost])
def host_rewards(request):
    payouts = Payout.objects.select_related("user", "booking")[:100]
    referrals = list(
        Member.objects.filter(referred_by__isnull=False)
        .select_related("user", "referred_by", "referral_booking")
        .order_by("-referred_at")[:100]
    )
    codes = dict(
        Member.objects.filter(user_id__in={m.referred_by_id for m in referrals}).values_list("user_id", "code")
    )
    return Response(
        {
            "program": ProgramSerializer(Program.load()).data,
            "stats": services.stats(),
            "payouts": [payout_dict(p) for p in payouts],
            "referrals": [
                {
                    "referrer": m.referred_by.display_name,
                    "referee": m.user.display_name,
                    "code": codes.get(m.referred_by_id),
                    "status": m.referral_status,
                    "status_label": m.get_referral_status_display(),
                    "booking": m.referral_booking.ref if m.referral_booking_id else None,
                    "created_at": m.referred_at,
                }
                for m in referrals
            ],
        }
    )


@api_view(["PUT", "PATCH"])
@permission_classes([IsHost])
def host_program(request):
    s = ProgramSerializer(Program.load(), data=request.data, partial=request.method == "PATCH")
    s.is_valid(raise_exception=True)
    s.save()
    return Response(s.data)


@api_view(["POST"])
@permission_classes([IsHost])
def host_payout_action(request, pk, action):
    p = get_object_or_404(Payout.objects.select_related("user", "booking"), pk=pk)
    if p.status != "held":
        return Response({"error": "Only rewards waiting for approval can be approved or rejected."}, status=400)
    if action == "approve":
        services.approve(p, actor=request.user)
    elif action == "reject":
        services.reject(p, actor=request.user)
    else:
        return Response({"error": "Unknown action - use approve or reject."}, status=400)
    p.refresh_from_db()
    return Response(payout_dict(p))


@api_view(["POST"])
@permission_classes([IsHost])
def host_send(request):
    """Amina sends airtime or a data bundle to a guest herself."""
    phone = normalize_phone(request.data.get("phone"))
    kind = request.data.get("kind")
    if not phone:
        return Response({"error": "Enter the guest's phone number."}, status=400)
    if not is_kenyan(phone):
        return Response({"error": "Airtime and data can only go to Kenyan (+254) numbers."}, status=400)
    if kind not in ("airtime", "data"):
        return Response({"error": "Choose airtime or data."}, status=400)
    try:
        amount = int(request.data.get("amount"))
    except (TypeError, ValueError):
        amount = 0
    low, high = (10, 1000) if kind == "airtime" else (50, 5000)
    if not low <= amount <= high:
        unit = "KES" if kind == "airtime" else "MB"
        return Response({"error": f"Choose between {low} and {high:,} {unit}."}, status=400)
    p = services.gift(phone, kind, amount, note=(request.data.get("note") or "").strip()[:120], actor=request.user)
    if p is None:
        return Response({"error": "Couldn't send to that number."}, status=400)
    p.refresh_from_db()
    return Response(payout_dict(p), status=201)
