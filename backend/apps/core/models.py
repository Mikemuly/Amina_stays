from django.conf import settings
from django.db import IntegrityError, models, transaction


class SiteSettings(models.Model):
    """Business settings Amina edits from the console (singleton row, pk=1)."""

    business_name = models.CharField(max_length=80, default="Amina Stays")
    host_name = models.CharField(max_length=60, default="Amina")
    host_phone = models.CharField(
        max_length=20, blank=True, help_text="Receives relayed questions, alerts and the daily digest"
    )
    backup_phone = models.CharField(max_length=20, blank=True, help_text="Called if Amina doesn't answer an emergency")
    support_email = models.EmailField(blank=True)
    tagline = models.CharField(max_length=140, default="Thoughtfully hosted homes on the Kenyan coast")

    default_checkin_time = models.CharField(max_length=5, default="14:00")
    default_checkout_time = models.CharField(max_length=5, default="11:00")
    code_release_time = models.CharField(
        max_length=5, default="08:00", help_text="When door codes go out on arrival day"
    )

    hold_minutes = models.PositiveIntegerField(default=10, help_text="How long a unit is held while the guest pays")
    deposit_percent = models.PositiveIntegerField(default=30, help_text="Deposit for 'pay part now' bookings")
    balance_due_days = models.PositiveIntegerField(
        default=1, help_text="Balance is requested this many days before arrival"
    )
    instant_changes = models.BooleanField(
        default=True,
        help_text="Guests can change or extend into free nights and pay the difference instantly; off = you approve each change",
    )
    tourism_levy_percent = models.DecimalField(max_digits=4, decimal_places=2, default=2)
    vat_percent = models.DecimalField(max_digits=4, decimal_places=2, default=0)

    vat_registered = models.BooleanField(
        default=False, help_text="VAT applies once taxable supplies pass KES 5m / 12 months"
    )

    # Compliance (Tourism Act 2011 + Tourism Enterprises Regulations 2025, Data Protection Act 2019)
    tra_licence_number = models.CharField(
        max_length=40, blank=True, help_text="Shown on every listing and booking page (r.19)"
    )
    tra_licence_expiry = models.DateField(null=True, blank=True)
    odpc_registration = models.CharField(max_length=40, blank=True, help_text="Data controller registration number")
    kra_pin = models.CharField(max_length=20, blank=True)

    require_id_before_code = models.BooleanField(
        default=True, help_text="Hold the door code until the guest has registered an ID/passport (guest register)"
    )
    id_retention_days = models.PositiveIntegerField(
        default=1825, help_text="Guest register records are kept 5 years (r.26), then ID numbers are erased"
    )
    sim_swap_check = models.BooleanField(
        default=True, help_text="Check for a recent SIM swap before releasing a door code"
    )
    promo_window_start = models.PositiveIntegerField(default=8, help_text="Promotional SMS only from this hour…")
    promo_window_end = models.PositiveIntegerField(default=18, help_text="…until this hour (Kenya time)")
    welcome_data_mb = models.PositiveIntegerField(
        default=0, help_text="Africa's Talking Mobile Data gift on check-in (0 = off)"
    )
    voice_welcome_call = models.BooleanField(
        default=False, help_text="Call Kenyan guests on arrival day with a spoken walkthrough"
    )
    goodwill_airtime_kes = models.PositiveIntegerField(
        default=50, help_text="Airtime apology when Amina cancels a paid stay (0 = off)"
    )

    review_delay_minutes = models.PositiveIntegerField(default=60)
    quiet_hours_start = models.PositiveIntegerField(default=21)
    quiet_hours_end = models.PositiveIntegerField(default=8)
    auto_answer = models.BooleanField(
        default=True, help_text="Answer common questions automatically from the knowledge base"
    )

    usd_rate = models.DecimalField(max_digits=8, decimal_places=2, default=129, help_text="KES per USD (display only)")
    eur_rate = models.DecimalField(max_digits=8, decimal_places=2, default=150, help_text="KES per EUR (display only)")
    gbp_rate = models.DecimalField(max_digits=8, decimal_places=2, default=172, help_text="KES per GBP (display only)")

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "site settings"
        verbose_name_plural = "site settings"

    def __str__(self):
        return self.business_name

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1, defaults={"host_phone": settings.AMINA_PHONE})
        return obj

    @property
    def host_contact(self):
        return self.host_phone or settings.AMINA_PHONE


class Activity(models.Model):
    """Audit trail + live activity feed for the console ('USSD booking AMS-4821 by +2547…')."""

    KINDS = [
        (k, k)
        for k in (
            "booking",
            "payment",
            "message",
            "sms",
            "ussd",
            "voice",
            "task",
            "alert",
            "review",
            "lock",
            "pricing",
            "listing",
            "guest",
            "broadcast",
            "system",
            "auth",
        )
    ]
    kind = models.CharField(max_length=20, choices=KINDS)
    channel = models.CharField(max_length=12, blank=True)
    title = models.CharField(max_length=200)
    detail = models.TextField(blank=True)
    booking_ref = models.CharField(max_length=20, blank=True, db_index=True)
    phone = models.CharField(max_length=20, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-id"]
        verbose_name_plural = "activity"

    def __str__(self):
        return self.title


class OnceMarker(models.Model):
    """Idempotency: a key can only ever be marked once (e.g. 'booking:AMS-1234:directions')."""

    key = models.CharField(max_length=160, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def mark(cls, key):
        """True if this call claimed the key; False if it was already claimed."""
        try:
            with transaction.atomic():
                cls.objects.create(key=key)
            return True
        except IntegrityError:
            return False

    @classmethod
    def seen(cls, key):
        return cls.objects.filter(key=key).exists()


class JobRun(models.Model):
    """Scheduler bookkeeping so periodic jobs survive restarts and show health in the console."""

    key = models.CharField(max_length=60, unique=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_ok = models.BooleanField(default=True)
    last_error = models.TextField(blank=True)
    run_count = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.key
