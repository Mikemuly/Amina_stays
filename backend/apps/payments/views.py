import csv
import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.db.models import Q
from django.http import Http404, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.bookings.models import Booking
from apps.comms import deferred
from apps.core.api import IsGuest, IsHost
from apps.core.utils import today

from . import c2b, invoices, services
from .models import C2BTransaction, Payment, Refund
from .providers import STRIPE_EVENTS, PaymentError, PaystackCard, callback_secret, stripe_signature_ok, stripe_test_mode
from .results import code_from_text

log = logging.getLogger("amina.payments")


def _same(given, expected):
    """Constant-time comparison that is simply False (never a 500) for a non-ASCII secret or signature."""
    return hmac.compare_digest(str(given or "").encode(), str(expected or "").encode())


def _secret_ok(secret):
    expected = settings.AT_WEBHOOK_SECRET
    return not expected or _same(secret, expected)


def _json(request):
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return request.POST.dict()
    return data if isinstance(data, dict) else {}


def _err(e, status=400):
    return Response({"error": str(e)}, status=status)


@csrf_exempt
@require_POST
def at_callback(request, secret=""):
    """Africa's Talking Mobile Checkout notification."""
    if not _secret_ok(secret or request.GET.get("key")):
        return HttpResponseForbidden("bad secret")
    d = _json(request)
    meta = d.get("requestMetadata") or d.get("metadata") or {}
    p = Payment.objects.filter(transaction_id=d.get("transactionId")).first() if d.get("transactionId") else None
    if p is None and str(meta.get("paymentId", "")).isdigit():
        p = Payment.objects.filter(pk=meta["paymentId"], method="mpesa").first()
    if p is None:
        log.warning("AT payment callback for unknown transaction: %s", d)
        return HttpResponse("OK")
    value = str(d.get("value", "")).replace("KES", "").strip()
    try:
        if d.get("status") == "Success":
            services.on_success(
                p,
                transaction_id=d.get("transactionId"),
                provider_ref=d.get("providerRefId", ""),
                raw=d,
                amount=value or None,
            )
        elif d.get("status") == "Failed":
            description = d.get("description", "failed")
            services.on_failure(p, description, raw=d, code=code_from_text(description))
    except Exception:
        log.exception("AT payment callback failed")
    return HttpResponse("OK")


@csrf_exempt
@require_POST
def daraja_callback(request, secret=""):
    """Safaricom Daraja STK push result (ResultCode 0 = paid), on the same path secret as the Paybill callbacks."""
    if not _same(secret, callback_secret()):
        return HttpResponseForbidden("bad secret")
    cb = (_json(request).get("Body") or {}).get("stkCallback") or {}
    checkout_id = cb.get("CheckoutRequestID")
    # never filter on a missing id: transaction_id=None would match any payment Daraja never saw
    p = Payment.objects.filter(transaction_id=checkout_id).first() if checkout_id else None
    if p is None:
        log.warning("Daraja callback for unknown request: %s", cb)
        return JsonResponse({"ResultCode": 0, "ResultDesc": "Accepted"})
    items = {i.get("Name"): i.get("Value") for i in (cb.get("CallbackMetadata") or {}).get("Item", [])}
    try:
        services.on_mpesa_result(
            p,
            cb.get("ResultCode"),
            desc=cb.get("ResultDesc", ""),
            raw=cb,
            amount=items.get("Amount"),
            receipt=str(items.get("MpesaReceiptNumber") or ""),
        )
    except Exception:
        log.exception("Daraja callback failed")
    return JsonResponse({"ResultCode": 0, "ResultDesc": "Accepted"})


@csrf_exempt
@require_POST
def c2b_callback(request, kind, secret):
    """Daraja C2B (Paybill/Till): register .../c2b/validation/<secret> and .../c2b/confirmation/<secret>."""
    if not _same(secret, callback_secret()):
        return HttpResponseForbidden("bad secret")
    payload = _json(request)
    if kind == "validation":
        code = c2b.validate(payload)
        return JsonResponse({"ResultCode": code, "ResultDesc": "Accepted" if code == "0" else "Rejected"})
    if kind != "confirmation":
        raise Http404
    try:
        c2b.receive(payload)
    except Exception:
        log.exception("C2B confirmation failed: %s", payload)
    return JsonResponse({"ResultCode": 0, "ResultDesc": "Accepted"})


@csrf_exempt
@require_POST
def paystack_webhook(request):
    """Answered at once (Paystack waits only a few seconds); Verify Transaction runs after the response."""
    sig = request.headers.get("x-paystack-signature", "")
    expected = hmac.new((settings.PAYSTACK_SECRET_KEY or "").encode(), request.body, hashlib.sha512).hexdigest()
    if not settings.PAYSTACK_SECRET_KEY or not _same(sig, expected):
        return HttpResponseForbidden("bad signature")
    event = _json(request)
    data = event.get("data") or {}
    reference = data.get("reference")
    p = Payment.objects.filter(checkout_token=reference, method="card").first() if reference else None
    if p and event.get("event") == "charge.success" and data.get("status") == "success":
        if p.provider == "paystack":  # a webhook only says "look": the money counts once Verify Transaction agrees
            deferred.after_response(_verify_card, p.pk)
        elif str(data.get("currency") or "KES").upper() == "KES":
            services.on_success(
                p,
                transaction_id=str(data.get("id")),
                provider_ref=data.get("reference", ""),
                raw=data,
                amount=(data.get("amount") or 0) / 100,
            )
    return HttpResponse("OK")


def _verify_card(payment_id):
    p = Payment.objects.get(pk=payment_id)
    services.settle_card(p, PaystackCard().query(p))


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """Stripe's Checkout Session events, signed with STRIPE_WEBHOOK_SECRET over the raw body. The answer goes back at
    once; the session is applied after the response (on_success settles once, so retries and duplicates are safe)."""
    signature = request.headers.get("Stripe-Signature", "")
    if not stripe_signature_ok(request.body, signature, settings.STRIPE_WEBHOOK_SECRET):
        return HttpResponse("bad signature", status=400)
    event = _json(request)
    session = (event.get("data") or {}).get("object") or {}
    if event.get("type") in STRIPE_EVENTS and isinstance(session, dict) and session.get("object") == "checkout.session":
        token = session.get("client_reference_id")
        p = Payment.objects.filter(checkout_token=token, method="card", provider="stripe").first() if token else None
        if p:
            deferred.after_response(_stripe_event, p.pk, event["type"], session)
    return HttpResponse("OK")


def _stripe_event(payment_id, kind, session):
    p = Payment.objects.get(pk=payment_id)
    if kind == "checkout.session.async_payment_failed":
        services.on_failure(p, "card payment failed", raw={k: session.get(k) for k in services.STRIPE_FIELDS})
    else:
        services.settle_stripe(p, session)


# ---------- simulated hosted card page (the Next.js /pay/card/[token] page calls these) ----------


def _card(token):
    return get_object_or_404(
        Payment.objects.select_related("booking", "booking__unit"), checkout_token=token, method="card"
    )


@api_view(["GET", "POST"])
def card_checkout(request, token):
    """The /pay/card/<token> page: the simulated card form, or for a real provider the page that opens its checkout
    and where Stripe brings the guest back. Opening it asks Stripe about a pending payment (throttled), so the stay
    confirms the moment the guest is back, webhook or not."""
    p = _card(token)
    b = p.booking
    if request.method == "GET" and p.provider == "stripe" and p.status == "pending":
        p = services.check_stripe(p)
        b.refresh_from_db()
    if request.method == "POST" and p.provider == "simulate":
        if (
            p.status in ("pending", "failed")
            and b.status in ("held", "confirmed", "checked_in")
            and (b.status != "held" or b.hold_active)
        ):
            if request.data.get("action") == "pay":
                services.on_success(p, transaction_id=f"CARD-SIM-{p.pk}", provider_ref=f"AUTH{p.pk:06d}")
            else:
                if p.status == "pending":
                    services.on_failure(p, "card declined")
        p.refresh_from_db()
        b.refresh_from_db()
    change = p.change_requests.order_by("-id").first() if p.purpose == "change" else None
    return Response(
        {
            "ref": b.ref,
            "unit": b.unit.name,
            "check_in": b.check_in,
            "check_out": b.check_out,
            "amount": p.amount,
            "currency": p.currency,
            "purpose": p.purpose,
            "change": {"check_in": change.new_check_in, "check_out": change.new_check_out} if change else None,
            "status": p.status,
            "booking_status": b.status,
            "expires_at": b.hold_expires_at if b.status == "held" else None,
            "expired": (b.status == "held" and not b.hold_active) or b.status == "expired",
            "simulated": p.provider == "simulate",
            "provider": p.provider,
            "checkout_url": services.checkout_url(p) if p.status == "pending" and p.provider != "simulate" else None,
            "test_mode": p.provider == "stripe" and stripe_test_mode(),
        }
    )


# ---------- guest: tax invoice, "I've paid" ----------


def _booking_for(request, ref):
    """The guest's own booking, or any booking for the host; 404 for everyone else."""
    b = get_object_or_404(Booking.objects.select_related("guest", "unit"), ref=ref.upper())
    if b.guest_id != request.user.pk and not getattr(request.user, "is_host", False):
        raise Http404
    return b


@api_view(["GET", "PATCH"])
@permission_classes([IsGuest])
def invoice(request, ref):
    b = _booking_for(request, ref)
    inv = invoices.get_or_issue(b)
    if inv is None:
        return _err("An invoice is issued once the booking is confirmed.", 404)
    if request.method == "PATCH":
        d = request.data
        try:
            invoices.update_buyer(inv, name=d.get("buyer_name"), kra_pin=d.get("buyer_kra_pin"))
        except invoices.InvoiceError as e:
            return _err(e)
    return Response(invoices.invoice_for(b))


@api_view(["POST"])
@permission_classes([IsGuest])
def claim(request, ref):
    b = _booking_for(request, ref)
    try:
        return Response(c2b.claim(b, request.data.get("code"), channel="web", actor=request.user))
    except PaymentError as e:
        return _err(e)


# ---------- host ledger ----------


def _month(request):
    month = request.query_params.get("month") or today().strftime("%Y-%m")
    start, end = services.month_bounds(month)  # ValueError for anything but YYYY-MM
    return start, end


@api_view(["GET"])
@permission_classes([IsHost])
def ledger(request):
    if request.query_params.get("export") == "csv":  # not ?format=, which DRF reserves for content negotiation
        try:
            start, end = _month(request)
        except ValueError:
            return _err("Choose a month as YYYY-MM, e.g. 2026-10.")
        resp = HttpResponse(content_type="text/csv")
        resp["Content-Disposition"] = f'attachment; filename="ledger-{start:%Y-%m}.csv"'
        w = csv.writer(resp)
        w.writerow(services.LEDGER_COLUMNS)
        w.writerows(services.ledger_rows(start, end))
        return resp
    q = request.query_params.get("q", "").strip()
    qs = Payment.objects.select_related("booking", "booking__guest", "booking__unit").order_by("-id")
    if request.query_params.get("status"):
        qs = qs.filter(status=request.query_params["status"])
    if q:
        qs = qs.filter(Q(booking__ref__icontains=q) | Q(phone__icontains=q) | Q(provider_ref__icontains=q))
    refunds = Refund.objects.select_related("booking", "booking__guest").order_by("-id")[:100]
    return Response(
        {
            "payments": [
                {
                    "id": p.pk,
                    "ref": p.booking.ref,
                    "guest": p.booking.guest.display_name,
                    "unit": p.booking.unit.name,
                    "amount": p.amount,
                    "method": p.method,
                    "method_label": p.get_method_display(),
                    "purpose": p.purpose,
                    "status": p.status,
                    "provider": p.provider,
                    "reference": p.provider_ref,
                    "failure_code": p.failure_code or None,
                    "failure_reason": p.failure_reason,
                    "created_at": p.created_at,
                    "completed_at": p.completed_at,
                }
                for p in qs[:300]
            ],
            "refunds": [
                {
                    "id": r.pk,
                    "ref": r.booking.ref,
                    "guest": r.booking.guest.display_name,
                    "phone": r.booking.guest.phone,
                    "amount": r.amount,
                    "method": r.get_method_display(),
                    "status": r.status,
                    "reason": r.reason,
                    "reference": r.provider_ref,
                    "created_at": r.created_at,
                }
                for r in refunds
            ],
            "outstanding": services.outstanding_balances(),
            "unmatched": c2b.unmatched_rows(),
        }
    )


@api_view(["POST"])
@permission_classes([IsHost])
def refund_sent(request, pk):
    r = get_object_or_404(Refund, pk=pk)
    services.mark_refund_sent(r, provider_ref=str(request.data.get("reference") or ""), actor=request.user)
    return Response({"ok": True})


@api_view(["POST"])
@permission_classes([IsHost])
def match_unmatched(request, pk):
    t = get_object_or_404(C2BTransaction, pk=pk)
    try:
        p = c2b.match(t, str(request.data.get("ref") or ""), actor=request.user)
    except PaymentError as e:
        return _err(e)
    b = Booking.objects.get(pk=p.booking_id)
    return Response({"ok": True, "ref": b.ref, "status": b.status, "payment_id": p.pk})


@api_view(["GET"])
@permission_classes([IsHost])
def host_invoices(request):
    """The month's sales register: every invoice and credit note issued (?export=csv for the accountant)."""
    try:
        start, end = _month(request)
    except ValueError:
        return _err("Choose a month as YYYY-MM, e.g. 2026-10.")
    rows, totals = invoices.register(start, end)
    if request.query_params.get("export") == "csv":
        resp = HttpResponse(content_type="text/csv")
        resp["Content-Disposition"] = f'attachment; filename="sales-register-{start:%Y-%m}.csv"'
        w = csv.writer(resp)
        w.writerow(invoices.REGISTER_COLUMNS)
        w.writerows([r[c] for c in invoices.REGISTER_COLUMNS] for r in rows)
        w.writerow(["total", "", "", "", "", "", "", totals["net"], totals["vat"], totals["levy"], totals["total"], ""])
        return resp
    return Response(
        {
            "month": f"{start:%Y-%m}",
            "invoices": [r for r in rows if r["type"] == "invoice"],
            "credit_notes": [r for r in rows if r["type"] == "credit_note"],
            "totals": totals,
        }
    )
