from django.contrib.auth import login, logout
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from apps.core.api import IsGuest
from apps.properties.models import Unit, Wishlist
from apps.properties.serializers import listing_card, review_stats

from . import services
from .models import ID_TYPES, LANGUAGES


class RequestThrottle(SimpleRateThrottle):
    """Per-IP cap on code requests (the 30 s resend gap per phone is enforced in the service)."""

    scope = "otp"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class VerifyThrottle(RequestThrottle):
    """Per-IP cap on guesses (each code also locks after 5 wrong attempts)."""

    scope = "otp_verify"


def user_dict(u):
    if not u or not u.is_authenticated:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "id": u.pk,
        "phone": u.phone,
        "name": u.name,
        "email": u.email,
        "role": u.role,
        "is_host": u.is_host,
        "lang": u.lang,
        "nationality": u.nationality,
        "preferred_channel": u.preferred_channel,
        "marketing_opt_in": u.marketing_opt_in,
        "identity": {
            "type": u.id_type,
            "type_label": u.get_id_type_display() if u.id_type else "",
            "last4": u.id_last4,
            "submitted_at": u.id_submitted_at,
            "verified": bool(u.id_verified_at),
        },
        "languages": LANGUAGES,
        "id_types": ID_TYPES,
    }


@ensure_csrf_cookie
def csrf(request):
    return JsonResponse({"csrfToken": get_token(request)})


@api_view(["POST"])
@throttle_classes([RequestThrottle])
def otp_request(request):
    try:
        return Response(services.request_otp(request.data.get("phone")))
    except services.AuthError as e:
        return Response({"error": str(e)}, status=400)


@api_view(["POST"])
@throttle_classes([VerifyThrottle])
def otp_verify(request):
    try:
        user = services.verify_otp(request.data.get("phone"), request.data.get("code"))
    except services.AuthError as e:
        return Response({"error": str(e)}, status=400)
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return Response(user_dict(user))


@api_view(["POST"])
def logout_view(request):
    logout(request)
    return Response({"ok": True})


@api_view(["GET", "PATCH"])
def me(request):
    if request.method == "GET":
        return Response(user_dict(request.user))
    if not request.user.is_authenticated:
        return Response({"error": "Please log in with your phone number."}, status=401)
    u, d = request.user, request.data
    if d.get("email"):
        try:
            validate_email(str(d["email"]).strip())
        except ValidationError:
            return Response({"error": "Please enter a valid email address."}, status=400)
    for field, limit in (("name", 80), ("email", 254)):
        if field in d:
            setattr(u, field, str(d[field] or "")[:limit].strip())
    if d.get("lang") in dict(LANGUAGES):
        u.lang = d["lang"]
    if "nationality" in d:
        u.nationality = str(d["nationality"] or "")[:2].upper()
    if d.get("preferred_channel") in ("sms", "whatsapp"):
        u.preferred_channel = d["preferred_channel"]
    if "marketing_opt_in" in d:
        u.marketing_opt_in = bool(d["marketing_opt_in"])
        if u.marketing_opt_in:
            u.sms_opt_out_at = None
    u.save()
    return Response(user_dict(u))


@api_view(["POST"])
@permission_classes([IsGuest])
def identity(request):
    d = request.data
    try:
        services.set_identity(
            request.user,
            id_type=d.get("id_type", ""),
            id_number=d.get("id_number", ""),
            nationality=d.get("nationality", ""),
            consent=bool(d.get("consent")),
            name=d.get("name", ""),
        )
    except services.AuthError as e:
        return Response({"error": str(e)}, status=400)
    return Response(user_dict(request.user))


@api_view(["GET"])
@permission_classes([IsGuest])
def export(request):
    resp = Response(services.export_data(request.user))
    resp["Content-Disposition"] = 'attachment; filename="amina-stays-my-data.json"'
    return resp


@api_view(["POST"])
@permission_classes([IsGuest])
def erase(request):
    result = services.erase(request.user)
    logout(request)
    return Response(result)


@api_view(["GET", "POST"])
@permission_classes([IsGuest])
def wishlist(request):
    if request.method == "POST":
        unit = get_object_or_404(Unit, slug=request.data.get("slug"))
        Wishlist.objects.get_or_create(user=request.user, unit=unit)
        return Response({"ok": True}, status=201)
    units = [
        w.unit
        for w in Wishlist.objects.filter(user=request.user)
        .select_related("unit__area")
        .prefetch_related("unit__photos")
    ]
    stats = review_stats()
    return Response([listing_card(u, stats=stats, wished=True) for u in units if u.status == "active"])


@api_view(["DELETE"])
@permission_classes([IsGuest])
def wishlist_remove(request, slug):
    Wishlist.objects.filter(user=request.user, unit__slug=slug).delete()
    return Response(status=204)
