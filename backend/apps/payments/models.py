from django.conf import settings
from django.db import models
from django.utils import timezone


class Payment(models.Model):
    METHODS = [("mpesa", "M-Pesa"), ("card", "Card"), ("cash", "Cash"), ("bank", "Bank transfer")]
    STATUS = [
        ("pending", "Pending"),
        ("success", "Paid"),
        ("failed", "Failed"),
        ("expired", "Expired"),
        ("cancelled", "Cancelled"),
        ("refunded", "Refunded"),
    ]
    PURPOSES = [
        ("full", "Full payment"),
        ("deposit", "Deposit"),
        ("balance", "Balance"),
        ("addon", "Add-on"),
        ("change", "Date change"),
    ]

    booking = models.ForeignKey("bookings.Booking", on_delete=models.CASCADE, related_name="payments")
    amount = models.PositiveIntegerField()
    currency = models.CharField(max_length=3, default="KES")
    method = models.CharField(max_length=6, choices=METHODS)
    purpose = models.CharField(max_length=8, choices=PURPOSES, default="full")
    status = models.CharField(max_length=10, choices=STATUS, default="pending", db_index=True)
    phone = models.CharField(max_length=20, blank=True)
    provider = models.CharField(max_length=20, default="simulate")
    transaction_id = models.CharField(max_length=80, null=True, blank=True, unique=True)
    provider_ref = models.CharField(max_length=80, blank=True, help_text="M-Pesa receipt, card auth code…")
    checkout_token = models.CharField(max_length=64, null=True, blank=True, unique=True)
    failure_code = models.CharField(max_length=12, blank=True, help_text="M-Pesa ResultCode, e.g. 1032")
    failure_reason = models.CharField(max_length=200, blank=True)
    raw = models.JSONField(default=list, blank=True, help_text="Provider responses and callbacks, for reconciliation")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.booking_id} {self.method} {self.amount} {self.status}"


class Refund(models.Model):
    METHODS = [("mpesa_b2c", "M-Pesa (B2C)"), ("card", "Card reversal"), ("manual", "Manual / cash")]
    STATUS = [("pending", "Pending"), ("success", "Sent"), ("failed", "Failed")]
    booking = models.ForeignKey("bookings.Booking", on_delete=models.CASCADE, related_name="refunds")
    payment = models.ForeignKey(Payment, null=True, blank=True, on_delete=models.SET_NULL, related_name="refunds")
    amount = models.PositiveIntegerField()
    method = models.CharField(max_length=10, choices=METHODS, default="mpesa_b2c")
    status = models.CharField(max_length=8, choices=STATUS, default="pending")
    provider_ref = models.CharField(max_length=80, blank=True)
    reason = models.CharField(max_length=200, blank=True)
    raw = models.JSONField(default=list, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]


class C2BTransaction(models.Model):
    """A Lipa na M-Pesa Paybill/Till payment (Daraja C2B confirmation). The account number the guest typed is
    matched to a booking ref; anything that doesn't match waits in the host's "Unmatched payments" queue."""

    STATUS = [("matched", "Matched"), ("unmatched", "Unmatched")]

    trans_id = models.CharField(max_length=32, unique=True, help_text="M-Pesa transaction code, e.g. SKL3X7QW2P")
    amount = models.PositiveIntegerField()
    phone = models.CharField(max_length=80, blank=True, help_text="MSISDN as sent (newer Daraja payloads mask it)")
    payer_name = models.CharField(max_length=120, blank=True)
    bill_ref = models.CharField(max_length=40, blank=True, help_text="Account number exactly as typed")
    shortcode = models.CharField(max_length=12, blank=True)
    trans_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="unmatched", db_index=True)
    note = models.CharField(max_length=200, blank=True)
    booking = models.ForeignKey(
        "bookings.Booking", null=True, blank=True, on_delete=models.SET_NULL, related_name="c2b_payments"
    )
    payment = models.OneToOneField(Payment, null=True, blank=True, on_delete=models.SET_NULL, related_name="c2b")
    matched_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    matched_at = models.DateTimeField(null=True, blank=True)
    raw = models.JSONField(default=dict, blank=True)
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-id"]
        verbose_name = "Paybill (C2B) payment"

    def __str__(self):
        return f"{self.trans_id} {self.amount} {self.status}"


class DocumentCounter(models.Model):
    """Gap-free numbering for tax documents: one row per series and year, incremented under a row lock."""

    key = models.CharField(max_length=20, unique=True)
    last = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.key}: {self.last}"


ETIMS_STATUS = [
    ("not_submitted", "Not submitted"),
    ("pending", "Pending"),
    ("synced", "Synced"),
    ("failed", "Failed"),
]


class Invoice(models.Model):
    """eTIMS-ready tax invoice for a stay. Lines and totals follow the booking until the invoice is
    transmitted to KRA (etims_status != not_submitted); after that they are frozen and reductions become
    credit notes."""

    booking = models.OneToOneField("bookings.Booking", on_delete=models.CASCADE, related_name="invoice")
    number = models.CharField(max_length=24, unique=True)
    year = models.PositiveSmallIntegerField()
    seq = models.PositiveIntegerField()
    issued_at = models.DateTimeField(default=timezone.now, db_index=True)
    buyer_name = models.CharField(max_length=120, blank=True)
    buyer_kra_pin = models.CharField(max_length=11, blank=True)
    lines = models.JSONField(default=list, blank=True)
    subtotal = models.IntegerField(default=0)
    vat = models.PositiveIntegerField(default=0)
    levy = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)
    etims_status = models.CharField(max_length=14, choices=ETIMS_STATUS, default="not_submitted")
    etims_invoice_no = models.CharField(max_length=40, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-issued_at", "-id"]
        constraints = [models.UniqueConstraint(fields=["year", "seq"], name="invoice_year_seq_unique")]

    def __str__(self):
        return self.number


class CreditNote(models.Model):
    """Reduces an invoice: a cancelled stay, or a refund of value the invoice still charges for."""

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="credit_notes")
    refund = models.ForeignKey(Refund, null=True, blank=True, on_delete=models.SET_NULL, related_name="credit_notes")
    number = models.CharField(max_length=24, unique=True)
    year = models.PositiveSmallIntegerField()
    seq = models.PositiveIntegerField()
    issued_at = models.DateTimeField(default=timezone.now, db_index=True)
    amount = models.PositiveIntegerField()
    reason = models.CharField(max_length=200, blank=True)
    etims_status = models.CharField(max_length=14, choices=ETIMS_STATUS, default="not_submitted")

    class Meta:
        ordering = ["issued_at", "id"]
        constraints = [models.UniqueConstraint(fields=["year", "seq"], name="creditnote_year_seq_unique")]

    def __str__(self):
        return self.number
