import secrets

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateRangeField, RangeBoundary, RangeOperators
from django.db import models
from django.db.models import Func, Q
from django.utils import timezone

ACTIVE_STATUSES = ("held", "confirmed", "checked_in")
LIVE_STATUSES = ("confirmed", "checked_in", "completed")  # count as real, paid stays


class DateRange(Func):
    function = "DATERANGE"
    output_field = DateRangeField()


class Booking(models.Model):
    STATUS = [
        ("held", "Held — awaiting payment"),
        ("confirmed", "Confirmed"),
        ("checked_in", "Checked in"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
        ("expired", "Hold expired"),
        ("refund_due", "Refund due"),
        ("no_show", "No-show"),
    ]
    CHANNELS = [
        ("web", "Website"),
        ("ussd", "USSD"),
        ("sms", "SMS (Ask Amina)"),
        ("voice", "Voice (Call Amina)"),
        ("whatsapp", "WhatsApp"),
        ("walk_in", "Walk-in / phone (host)"),
        ("airbnb", "Airbnb"),
        ("booking_com", "Booking.com"),
    ]
    PAYMENT_STATUS = [
        ("unpaid", "Unpaid"),
        ("deposit_paid", "Deposit paid"),
        ("paid", "Paid in full"),
        ("refunded", "Refunded"),
        ("partially_refunded", "Partially refunded"),
    ]
    PLANS = [("full", "Pay in full"), ("deposit", "Deposit now, balance before arrival")]

    ref = models.CharField(max_length=16, unique=True)
    unit = models.ForeignKey("properties.Unit", on_delete=models.PROTECT, related_name="bookings")
    guest = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="bookings")
    check_in = models.DateField(db_index=True)
    check_out = models.DateField(db_index=True)
    adults = models.PositiveSmallIntegerField(default=1)
    children = models.PositiveSmallIntegerField(default=0)
    infants = models.PositiveSmallIntegerField(default=0)

    status = models.CharField(max_length=12, choices=STATUS, default="held", db_index=True)
    channel = models.CharField(max_length=12, choices=CHANNELS, default="web", db_index=True)
    lang = models.CharField(max_length=2, default="en")
    hold_expires_at = models.DateTimeField(null=True, blank=True)

    nightly = models.JSONField(default=list, blank=True)
    accommodation_amount = models.PositiveIntegerField(default=0)
    discount_amount = models.PositiveIntegerField(default=0)
    cleaning_fee = models.PositiveIntegerField(default=0)
    addons_amount = models.PositiveIntegerField(default=0)
    levy_amount = models.PositiveIntegerField(default=0)
    vat_amount = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)
    payment_plan = models.CharField(max_length=8, choices=PLANS, default="full")
    amount_due_now = models.PositiveIntegerField(default=0)
    amount_paid = models.PositiveIntegerField(default=0)
    amount_refunded = models.PositiveIntegerField(default=0)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default="unpaid")

    arrival_eta = models.CharField(max_length=40, blank=True)
    arrival_mode = models.CharField(max_length=10, blank=True, help_text="flight, sgr, car, bus, ferry…")
    vehicle_plate = models.CharField(max_length=12, blank=True, help_text="For the gate/vehicle log (PSRA directive)")
    special_requests = models.TextField(blank=True)
    purpose = models.CharField(max_length=20, blank=True)
    host_notes = models.TextField(blank=True)
    cancellation_policy = models.CharField(max_length=10, default="moderate")
    external_uid = models.CharField(max_length=255, blank=True)

    # Reservation screening (party / fraud risk) and SIM-swap check before the door code goes out
    risk_score = models.PositiveSmallIntegerField(default=0)
    risk_flags = models.JSONField(default=list, blank=True)
    sim_swap_status = models.CharField(max_length=20, blank=True)
    sim_swap_checked_at = models.DateTimeField(null=True, blank=True)
    sim_swap_request_id = models.CharField(max_length=80, blank=True)

    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.CharField(max_length=10, blank=True)
    cancel_reason = models.CharField(max_length=200, blank=True)
    code_released_at = models.DateTimeField(null=True, blank=True)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_out_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # The database itself refuses two active bookings for the same unit on overlapping nights.
            # Half-open [check_in, check_out) so a same-day turnover (out 11:00, in 14:00) is allowed.
            ExclusionConstraint(
                name="booking_no_overlap",
                expressions=[
                    ("unit", RangeOperators.EQUAL),
                    (DateRange("check_in", "check_out", RangeBoundary()), RangeOperators.OVERLAPS),
                ],
                condition=Q(status__in=ACTIVE_STATUSES),
            ),
            models.CheckConstraint(
                condition=Q(check_out__gt=models.F("check_in")), name="booking_checkout_after_checkin"
            ),
        ]

    def __str__(self):
        return self.ref

    @property
    def nights(self):
        return (self.check_out - self.check_in).days

    @property
    def guests_count(self):
        return self.adults + self.children

    @property
    def guest_phone(self):
        return self.guest.phone

    @property
    def balance_due(self):
        if self.status in ("cancelled", "expired"):
            return 0  # nothing is owed on a stay that isn't happening
        # money handed back on a live stay (its bill went down) no longer pays for it
        refunded = self.amount_refunded if self.status in (*ACTIVE_STATUSES, "completed") else 0
        return max(0, self.total - (self.amount_paid - refunded))

    @property
    def hold_active(self):
        return self.status == "held" and self.hold_expires_at and self.hold_expires_at > timezone.now()

    @staticmethod
    def new_ref():
        for _ in range(50):
            ref = "AMS-" + str(secrets.randbelow(9000) + 1000)
            if not Booking.objects.filter(ref=ref).exists():
                return ref
        return "AMS-" + secrets.token_hex(3).upper()


class BookingGuest(models.Model):
    """Guest register: every occupant of a stay (TRA Tourism Enterprises Regulations 2025, r.26)."""

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="occupants")
    full_name = models.CharField(max_length=80)
    id_type = models.CharField(max_length=20, blank=True)
    id_number_enc = models.TextField(blank=True)
    id_last4 = models.CharField(max_length=12, blank=True)
    nationality = models.CharField(max_length=2, blank=True)
    is_minor = models.BooleanField(default=False)
    is_lead = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_lead", "id"]

    def set_id_number(self, value):
        from apps.core import crypto

        value = (value or "").strip().upper()
        self.id_number_enc = crypto.encrypt(value)
        self.id_last4 = crypto.last4(value)[-8:]


class BookingEvent(models.Model):
    """The booking timeline the host sees: created via USSD → STK push → paid → code sent → …"""

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=30)
    text = models.CharField(max_length=300)
    channel = models.CharField(max_length=12, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class Addon(models.Model):
    """Extras guests can add: breakfast, airport/SGR pickup, early check-in, late checkout…"""

    PRICING = [
        ("per_stay", "per stay"),
        ("per_night", "per night"),
        ("per_guest_night", "per guest per night"),
        ("per_guest", "per guest"),
        ("per_item", "per item"),
    ]
    CATEGORIES = [
        (c, c.capitalize()) for c in ("breakfast", "transport", "flexibility", "cleaning", "experience", "comfort")
    ]
    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=60)
    short = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=12, choices=CATEGORIES, default="comfort")
    icon = models.CharField(max_length=40, default="sparkles")
    photo_url = models.URLField(max_length=300, blank=True, help_text="Shown on the Experiences & Services pages")
    price = models.PositiveIntegerField(default=0)
    pricing = models.CharField(max_length=16, choices=PRICING, default="per_stay")
    requires_approval = models.BooleanField(
        default=False, help_text="e.g. early check-in depends on the previous guest"
    )
    options = models.JSONField(default=dict, blank=True)
    lead_hours = models.PositiveSmallIntegerField(default=0)
    units = models.ManyToManyField("properties.Unit", blank=True, related_name="addons", help_text="Blank = all units")
    active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name

    def price_for(self, nights, guests, quantity=1):
        q = max(1, quantity)
        if self.pricing == "per_night":
            return self.price * nights * q
        if self.pricing == "per_guest_night":
            return self.price * nights * q  # quantity = number of guests eating
        if self.pricing == "per_guest":
            return self.price * q
        return self.price * q


class BookingAddon(models.Model):
    STATUS = [
        ("requested", "Requested"),
        ("confirmed", "Confirmed"),
        ("declined", "Declined"),
        ("fulfilled", "Fulfilled"),
        ("cancelled", "Cancelled"),
    ]
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="addons")
    addon = models.ForeignKey(Addon, on_delete=models.PROTECT, related_name="+")
    quantity = models.PositiveSmallIntegerField(default=1)
    unit_price = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=10, choices=STATUS, default="confirmed")
    details = models.JSONField(default=dict, blank=True, help_text="Breakfast style & dietary needs, flight number…")
    paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["id"]


class AccessCode(models.Model):
    """Door code lifecycle: generated at booking, withheld until arrival day, revoked at checkout."""

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="access_codes")
    code = models.CharField(max_length=12)
    provider = models.CharField(max_length=12, default="simulated")
    external_id = models.CharField(max_length=80, blank=True)
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoke_reason = models.CharField(max_length=40, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]

    @property
    def active(self):
        return self.revoked_at is None


class Waitlist(models.Model):
    STATUS = [("waiting", "Waiting"), ("offered", "Offered"), ("booked", "Booked"), ("expired", "Expired")]
    guest = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="waitlist")
    area = models.ForeignKey("properties.Area", null=True, blank=True, on_delete=models.SET_NULL)
    unit = models.ForeignKey("properties.Unit", null=True, blank=True, on_delete=models.SET_NULL)
    check_in = models.DateField()
    check_out = models.DateField()
    guests = models.PositiveSmallIntegerField(default=0)
    adults = models.PositiveSmallIntegerField(default=0, help_text="0 = not asked (SMS/USSD/voice give a head count)")
    children = models.PositiveSmallIntegerField(default=0)
    channel = models.CharField(max_length=10, default="sms")
    status = models.CharField(max_length=8, choices=STATUS, default="waiting")
    offered_unit = models.ForeignKey(
        "properties.Unit", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    offered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class ChangeRequest(models.Model):
    """A guest (or Amina) moving, shortening, extending or resizing a confirmed stay.

    Priced with the normal quote at request time (snapshot in `pricing`); applied in one transaction that
    re-checks availability. delta > 0 waits for payment, delta <= 0 applies at once and refunds the reduction
    under the cancellation policy; when instant changes are off, Amina approves first."""

    STATUS = [
        ("pending_host", "Waiting for Amina"),
        ("pending_payment", "Waiting for payment"),
        ("applied", "Changed"),
        ("declined", "Declined"),
        ("expired", "Expired"),
        ("cancelled", "Withdrawn"),
    ]
    PENDING = ("pending_host", "pending_payment")

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="changes")
    requested_by = models.CharField(max_length=5, choices=[("guest", "Guest"), ("host", "Host")], default="guest")
    channel = models.CharField(max_length=12, blank=True)
    old_check_in = models.DateField()
    old_check_out = models.DateField()
    old_adults = models.PositiveSmallIntegerField(default=1)
    old_children = models.PositiveSmallIntegerField(default=0)
    new_check_in = models.DateField()
    new_check_out = models.DateField()
    new_adults = models.PositiveSmallIntegerField(default=1)
    new_children = models.PositiveSmallIntegerField(default=0)
    old_total = models.PositiveIntegerField(default=0)
    new_total = models.PositiveIntegerField(default=0)
    delta = models.IntegerField(default=0, help_text="new_total - old_total; positive = the guest pays more")
    refund_amount = models.PositiveIntegerField(default=0)
    pricing = models.JSONField(default=dict, blank=True, help_text="Quoted nightly prices, fees and price lines")
    status = models.CharField(max_length=16, choices=STATUS, default="pending_host", db_index=True)
    payment = models.ForeignKey(
        "payments.Payment", null=True, blank=True, on_delete=models.SET_NULL, related_name="change_requests"
    )
    note = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"C{self.pk} {self.booking_id} {self.status}"

    @property
    def pay_now(self):
        return max(0, self.delta) if self.status in self.PENDING else 0
