"""eTIMS-ready tax invoices and credit notes.

An invoice is issued once per stay (when it's confirmed, or lazily the first time anyone opens it) with a gap-free
number per year: AMS-INV-2026-00001. Until it has been transmitted to KRA (etims_status still "not_submitted")
its lines follow the booking, so add-ons and date changes show up; after that the lines are frozen. A credit note
(AMS-CN-2026-00001) records value the invoice still charges for but the business no longer keeps: a cancelled
stay - created when its refund goes out - or a reduction after the invoice was frozen. Returning an overpayment is
not a credit note: the bill itself didn't change.
"""

import re

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from apps.bookings import services as bookings
from apps.bookings.models import Booking
from apps.core.models import SiteSettings
from apps.core.utils import kes

from .models import CreditNote, DocumentCounter, Invoice

KRA_PIN = re.compile(r"^[AP]\d{9}[A-Z]$")
INVOICED_STATUSES = ("confirmed", "checked_in", "completed")
CANCELLED_STATUSES = ("cancelled", "refund_due", "no_show", "expired")
COUNTED_ADDONS = ("confirmed", "fulfilled")


class InvoiceError(Exception):
    pass


def _next_seq(series, year):
    """Next number in a per-year series. Runs inside the caller's transaction: the UPDATE's row lock makes
    concurrent issuers queue, and a rollback gives the number back, so there are never gaps or repeats."""
    key = f"{series}-{year}"
    DocumentCounter.objects.get_or_create(key=key)
    DocumentCounter.objects.filter(key=key).update(last=F("last") + 1)
    return DocumentCounter.objects.get(key=key).last


def _was_confirmed(b):
    return b.status in INVOICED_STATUSES or b.events.filter(kind="confirmed").exists()


def get_or_issue(booking):
    """The stay's invoice, issued now if it has none yet. None while the booking was never confirmed."""
    inv = Invoice.objects.filter(booking_id=booking.pk).first()
    if inv or not _was_confirmed(booking):
        return inv
    with transaction.atomic():
        b = Booking.objects.select_for_update().select_related("unit", "guest").get(pk=booking.pk)
        inv = Invoice.objects.filter(booking=b).first()
        if inv:
            return inv
        now = timezone.now()
        year = timezone.localtime(now).year
        seq = _next_seq("INV", year)
        inv = Invoice(booking=b, year=year, seq=seq, number=f"AMS-INV-{year}-{seq:05d}", issued_at=now)
        _snapshot(inv, b)
        inv.save()
        bookings.event(b, "invoice", f"Invoice {inv.number} issued ({kes(inv.total)})")
    return inv


def _line(label, qty, unit_price, amount=None):
    return {
        "label": label,
        "qty": qty,
        "unit_price": unit_price,
        "amount": qty * unit_price if amount is None else amount,
    }


def invoice_lines(b):
    """What the stay is charged for, net of VAT and levy (those are separate totals on the invoice)."""
    lines, n = [], b.nights
    stay = f"{b.unit.name} ({b.check_in:%d %b} - {b.check_out:%d %b %Y})"
    nightly = [x for x in (b.nightly or []) if isinstance(x, dict) and isinstance(x.get("price"), int)]
    if b.accommodation_amount and nightly and sum(x["price"] for x in nightly) == b.accommodation_amount:
        groups = {}
        for x in nightly:  # nights at the same rate share a line, in stay order
            key = (x.get("label") or "Standard", x["price"])
            groups[key] = groups.get(key, 0) + 1
        for (label, price), count in groups.items():
            lines.append(_line(f"{stay}, {label} nights" if len(groups) > 1 else f"{stay}, per night", count, price))
    elif b.accommodation_amount:
        lines.append(
            _line(f"{stay}, accommodation", n or 1, round(b.accommodation_amount / (n or 1)), b.accommodation_amount)
        )
    if b.discount_amount:
        lines.append(_line("Stay discount", 1, -b.discount_amount))
    if b.cleaning_fee:
        lines.append(_line("Cleaning fee", 1, b.cleaning_fee))
    for a in b.addons.filter(status__in=COUNTED_ADDONS).select_related("addon").order_by("id"):
        if a.unit_price and a.total % a.unit_price == 0:
            lines.append(_line(a.addon.name, a.total // a.unit_price, a.unit_price))
        else:
            lines.append(_line(a.addon.name, 1, a.total))
    taxable = b.total - b.levy_amount - b.vat_amount
    gap = taxable - sum(x["amount"] for x in lines)
    if gap:  # e.g. a price agreed by hand: the invoice must still add up to what the guest is charged
        lines.append(_line("Adjustment", 1, gap))
    return lines


def _snapshot(inv, b):
    inv.lines = invoice_lines(b)
    inv.subtotal = sum(x["amount"] for x in inv.lines)
    inv.vat, inv.levy, inv.total = b.vat_amount, b.levy_amount, b.total


def refresh(inv):
    """Bring an invoice that hasn't gone to KRA yet in line with its booking. Returns the (saved) invoice."""
    if inv.etims_status != "not_submitted":
        return inv
    b = Booking.objects.select_related("unit", "guest").get(pk=inv.booking_id)
    before = (inv.lines, inv.subtotal, inv.vat, inv.levy, inv.total)
    _snapshot(inv, b)
    if (inv.lines, inv.subtotal, inv.vat, inv.levy, inv.total) != before:
        inv.save(update_fields=["lines", "subtotal", "vat", "levy", "total", "updated_at"])
    return inv


def _kept(b):
    """The value of the stay the business keeps: the whole bill, or for a cancelled stay what wasn't refunded."""
    if b.status in CANCELLED_STATUSES:
        return max(0, b.amount_paid - b.amount_refunded)
    return b.total


def sync_credit_notes(booking, refund=None):
    """Issue the credit note that brings the invoice down to the value kept (idempotent). Returns it, or None."""
    inv = get_or_issue(booking)
    if inv is None:
        return None
    refresh(inv)
    with transaction.atomic():
        inv = Invoice.objects.select_for_update().get(pk=inv.pk)
        b = Booking.objects.get(pk=booking.pk)
        credited = inv.credit_notes.aggregate(s=Sum("amount"))["s"] or 0
        missing = inv.total - _kept(b) - credited
        if missing <= 0:
            return None
        year = timezone.localtime(timezone.now()).year
        seq = _next_seq("CN", year)
        reason = (refund.reason if refund and refund.reason else "") or (
            f"Booking {b.get_status_display().lower()}" if b.status in CANCELLED_STATUSES else "Bill reduced"
        )
        cn = CreditNote.objects.create(
            invoice=inv,
            refund=refund,
            number=f"AMS-CN-{year}-{seq:05d}",
            year=year,
            seq=seq,
            amount=missing,
            reason=reason[:200],
        )
        bookings.event(b, "invoice", f"Credit note {cn.number} issued for {kes(missing)} against {inv.number}")
    return cn


def update_buyer(inv, *, name=None, kra_pin=None):
    if inv.etims_status != "not_submitted":
        raise InvoiceError("This invoice has already been sent to KRA - ask us for a credit note and a new invoice.")
    if kra_pin is not None:
        pin = re.sub(r"\s", "", str(kra_pin)).upper()
        if pin and not KRA_PIN.match(pin):
            raise InvoiceError("Enter a valid KRA PIN: a letter, 9 digits and a letter, e.g. A123456789Z.")
        inv.buyer_kra_pin = pin
    if name is not None:
        inv.buyer_name = str(name).strip()[:120]
    inv.save(update_fields=["buyer_name", "buyer_kra_pin", "updated_at"])
    bookings.event(inv.booking, "invoice", f"Invoice {inv.number} reissued to {inv.buyer_name or 'the guest'}")
    return inv


def _local_date(dt):
    return timezone.localtime(dt).date() if dt else None


def as_dict(inv):
    b = Booking.objects.select_related("unit", "guest").get(pk=inv.booking_id)
    s = SiteSettings.load()
    payments = [
        {
            "date": _local_date(p.completed_at or p.created_at),
            "method": p.get_method_display() + (" Paybill" if p.provider == "c2b" else ""),
            "reference": p.provider_ref,
            "amount": p.amount,
        }
        for p in b.payments.filter(status="success").order_by("completed_at", "id")
    ]
    payments += [
        {
            "date": _local_date(r.completed_at or r.created_at),
            "method": f"Refund - {r.get_method_display()}",
            "reference": r.provider_ref,
            "amount": -r.amount,
        }
        for r in b.refunds.filter(status="success").order_by("completed_at", "id")
    ]
    notes = list(inv.credit_notes.all())
    paid = sum(x["amount"] for x in payments)
    credited = sum(c.amount for c in notes)
    return {
        "number": inv.number,
        "ref": b.ref,
        "issued_at": inv.issued_at,
        "seller": {
            "name": s.business_name,
            "kra_pin": s.kra_pin,
            "address": getattr(s, "business_address", "") or getattr(s, "address", "") or "Mombasa, Kenya",
            "tra_licence": b.unit.tra_licence_number or s.tra_licence_number,
            "vat_registered": s.vat_registered,
        },
        "buyer": {"name": inv.buyer_name or b.guest.name or "", "phone": b.guest.phone, "kra_pin": inv.buyer_kra_pin},
        "lines": inv.lines,
        "subtotal": inv.subtotal,
        "vat": inv.vat,
        "levy": inv.levy,
        "total": inv.total,
        "paid": paid,
        "balance": max(0, inv.total - credited - paid),
        "payments": payments,
        "credit_notes": [
            {"number": c.number, "date": _local_date(c.issued_at), "amount": c.amount, "reason": c.reason}
            for c in notes
        ],
        "etims": {"status": inv.etims_status, "invoice_no": inv.etims_invoice_no or None},
    }


def invoice_for(booking):
    """The guest-facing invoice JSON, issuing it on first view. Raises InvoiceError before confirmation."""
    inv = get_or_issue(booking)
    if inv is None:
        raise InvoiceError("An invoice is issued once the booking is confirmed.")
    sync_credit_notes(booking)  # also brings the lines up to date
    return as_dict(Invoice.objects.get(pk=inv.pk))


# ---------- the monthly sales register (KRA / eTIMS reconciliation) ----------

REGISTER_COLUMNS = [
    "type",
    "number",
    "date",
    "booking",
    "buyer",
    "buyer_kra_pin",
    "against_invoice",
    "net",
    "vat",
    "levy",
    "total",
    "etims_status",
]


def register(start, end):
    """Every invoice and credit note issued between start and end, in number order."""
    rows = []
    for inv in Invoice.objects.filter(issued_at__gte=start, issued_at__lt=end).select_related(
        "booking", "booking__guest"
    ):
        refresh(inv)
        rows.append(
            {
                "type": "invoice",
                "number": inv.number,
                "date": _local_date(inv.issued_at),
                "booking": inv.booking.ref,
                "buyer": inv.buyer_name or inv.booking.guest.name or "",
                "buyer_kra_pin": inv.buyer_kra_pin,
                "against_invoice": "",
                "net": inv.subtotal,
                "vat": inv.vat,
                "levy": inv.levy,
                "total": inv.total,
                "etims_status": inv.etims_status,
            }
        )
    notes = CreditNote.objects.filter(issued_at__gte=start, issued_at__lt=end).select_related(
        "invoice", "invoice__booking", "invoice__booking__guest"
    )
    for cn in notes:
        inv = cn.invoice
        vat = round(cn.amount * inv.vat / inv.total) if inv.total else 0
        levy = round(cn.amount * inv.levy / inv.total) if inv.total else 0
        rows.append(
            {
                "type": "credit_note",
                "number": cn.number,
                "date": _local_date(cn.issued_at),
                "booking": inv.booking.ref,
                "buyer": inv.buyer_name or inv.booking.guest.name or "",
                "buyer_kra_pin": inv.buyer_kra_pin,
                "against_invoice": inv.number,
                "net": -(cn.amount - vat - levy),
                "vat": -vat,
                "levy": -levy,
                "total": -cn.amount,
                "etims_status": cn.etims_status,
            }
        )
    rows.sort(key=lambda r: (r["type"] != "invoice", r["number"]))
    totals = {key: sum(r[key] for r in rows) for key in ("net", "vat", "levy", "total")}
    return rows, totals
