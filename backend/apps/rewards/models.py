from django.conf import settings
from django.db import models
from django.utils import timezone


class Program(models.Model):
    """Amina's loyalty and referral rules (one row). Rewards are paid in Africa's Talking airtime and mobile data:
    instant, useful to every guest with a Kenyan line, and no vouchers or cash to manage."""

    enabled = models.BooleanField(default=True)
    points_per_100 = models.PositiveSmallIntegerField(
        default=1, help_text="Points for every KES 100 of a completed stay"
    )
    review_points = models.PositiveIntegerField(
        default=50, help_text="Points for sharing feedback after a stay (any rating)"
    )
    referral_airtime = models.PositiveIntegerField(
        default=100, help_text="KES airtime for a guest whose friend completes a first stay"
    )
    referee_airtime = models.PositiveIntegerField(default=100, help_text="KES airtime for that friend, after the stay")
    redeem_points = models.PositiveIntegerField(default=100, help_text="Points per redemption")
    redeem_airtime = models.PositiveIntegerField(default=100, help_text="KES airtime per redemption")
    redeem_data_mb = models.PositiveIntegerField(default=250, help_text="MB of mobile data per redemption")
    outage_data_mb = models.PositiveIntegerField(
        default=100, help_text="Data for each guest staying when the Wi-Fi or power fails (0 = off)"
    )
    monthly_airtime_budget = models.PositiveIntegerField(
        default=5000, help_text="KES of airtime a month before rewards wait for your approval (0 = no cap)"
    )
    started_at = models.DateTimeField(default=timezone.now, help_text="Stays that ended before this earn no points")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "rewards programme"
        verbose_name_plural = "rewards programme"

    def __str__(self):
        return "Rewards programme"

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Member(models.Model):
    """A guest's place in the programme: their invite code and who invited them."""

    REFERRAL = [("pending", "Waiting for the first stay"), ("rewarded", "Rewarded"), ("void", "Not eligible")]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reward_member")
    code = models.CharField(max_length=16, unique=True)
    referred_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="referred_members"
    )
    referred_at = models.DateTimeField(null=True, blank=True)
    referral_status = models.CharField(max_length=8, choices=REFERRAL, blank=True)
    referral_booking = models.ForeignKey(
        "bookings.Booking", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.code


class PointsEntry(models.Model):
    REASONS = [
        ("stay", "Stay"),
        ("review", "Feedback"),
        ("redeem", "Redeemed"),
        ("refund", "Returned"),
        ("bonus", "Bonus"),
        ("adjust", "Adjustment"),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="points_entries")
    points = models.IntegerField()
    reason = models.CharField(max_length=8, choices=REASONS)
    booking = models.ForeignKey("bookings.Booking", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    payout = models.ForeignKey("Payout", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    note = models.CharField(max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
        verbose_name_plural = "points entries"


class Payout(models.Model):
    """Every airtime top-up and data bundle sent through Africa's Talking, whatever it was for."""

    KINDS = [("airtime", "Airtime"), ("data", "Mobile data")]
    REASONS = [
        ("referral", "Referral reward"),
        ("referee", "Referred-guest reward"),
        ("redeem", "Points redeemed"),
        ("outage", "Outage: stay connected"),
        ("manual", "Sent by host"),
    ]
    STATUS = [
        ("held", "Waiting for approval"),
        ("queued", "Queued"),
        ("sent", "Sent"),
        ("success", "Delivered"),
        ("failed", "Failed"),
        ("rejected", "Rejected"),
        ("simulated", "Simulated (no API key)"),
    ]
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="payouts"
    )
    phone = models.CharField(max_length=20, db_index=True)
    kind = models.CharField(max_length=8, choices=KINDS)
    amount = models.PositiveIntegerField(help_text="KES for airtime, MB for data")
    reason = models.CharField(max_length=8, choices=REASONS)
    status = models.CharField(max_length=10, choices=STATUS, default="queued", db_index=True)
    booking = models.ForeignKey("bookings.Booking", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    note = models.CharField(max_length=160, blank=True)
    provider_ref = models.CharField(max_length=80, blank=True, db_index=True)
    error = models.CharField(max_length=240, blank=True)
    idempotency_key = models.CharField(max_length=80, unique=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.amount_text} to {self.phone}"

    @property
    def amount_text(self):
        return f"KES {self.amount:,}" if self.kind == "airtime" else f"{self.amount:,} MB"
