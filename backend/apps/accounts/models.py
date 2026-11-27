from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models

from apps.core import crypto
from apps.core.utils import normalize_phone

LANGUAGES = [("en", "English"), ("sw", "Kiswahili"), ("fr", "Français"), ("de", "Deutsch"), ("it", "Italiano")]
ROLES = [
    ("guest", "Guest"),
    ("owner", "Owner"),
    ("manager", "Manager / co-host"),
    ("cleaner", "Cleaner"),
    ("cook", "Cook / breakfast"),
    ("caretaker", "Caretaker / maintenance"),
    ("security", "Security"),
    ("driver", "Driver"),
]
ID_TYPES = [
    ("national_id", "Kenyan National ID"),
    ("passport", "Passport"),
    ("alien_id", "Alien / Foreigner ID"),
    ("driving_licence", "Driving licence"),
]


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, phone, password=None, **extra):
        phone = normalize_phone(phone)
        if not phone:
            raise ValueError("A valid phone number is required")
        user = self.model(phone=phone, **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, phone, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("role", "owner")
        return self.create_user(phone, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """One identity per phone number — the same account whether the guest arrives by
    web, USSD, SMS or voice. Staff (Amina, cleaners, the cook…) are users with a role."""

    phone = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=80, blank=True)
    email = models.EmailField(blank=True)
    role = models.CharField(max_length=12, choices=ROLES, default="guest", db_index=True)
    lang = models.CharField(max_length=2, choices=LANGUAGES, default="en")
    nationality = models.CharField(max_length=2, blank=True, help_text="ISO 3166 alpha-2, e.g. KE, GB, DE")
    first_channel = models.CharField(max_length=10, blank=True)

    # Guest register (Tourism Act guest records) — encrypted at rest, erased after retention period
    id_type = models.CharField(max_length=20, choices=ID_TYPES, blank=True)
    id_number_enc = models.TextField(blank=True)
    id_last4 = models.CharField(max_length=12, blank=True)
    id_submitted_at = models.DateTimeField(null=True, blank=True)
    id_verified_at = models.DateTimeField(null=True, blank=True)
    consent_at = models.DateTimeField(null=True, blank=True, help_text="Data Protection Act consent to process ID")

    # Messaging preferences
    preferred_channel = models.CharField(
        max_length=8,
        default="sms",
        choices=[("sms", "SMS"), ("whatsapp", "WhatsApp")],
        help_text="International guests often prefer WhatsApp",
    )
    marketing_opt_in = models.BooleanField(default=False)
    sms_opt_out_at = models.DateTimeField(null=True, blank=True, help_text="Replied STOP — no promotional SMS")

    # Host CRM
    is_blocked = models.BooleanField(default=False, help_text="Do-not-host: new bookings are refused")
    block_reason = models.CharField(max_length=200, blank=True)
    host_notes = models.TextField(blank=True)
    tags = models.JSONField(default=list, blank=True)
    last_area = models.CharField(max_length=40, blank=True)
    last_guests = models.PositiveSmallIntegerField(null=True, blank=True)

    # Staff
    assigned_units = models.ManyToManyField("properties.Unit", blank=True, related_name="staff")
    is_staff = models.BooleanField(default=False, help_text="Can log in to the Django admin")
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()
    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = []

    class Meta:
        ordering = ["-date_joined"]

    def __str__(self):
        return f"{self.name} ({self.phone})" if self.name else self.phone

    @property
    def display_name(self):
        return self.name or self.phone

    @property
    def is_host(self):
        return self.is_superuser or self.role in ("owner", "manager")

    @property
    def has_id(self):
        return bool(self.id_number_enc)

    def set_id_number(self, value):
        value = (value or "").strip().upper()
        self.id_number_enc = crypto.encrypt(value)
        self.id_last4 = crypto.last4(value)[-8:]

    def get_id_number(self):
        return crypto.decrypt(self.id_number_enc)


class OTPCode(models.Model):
    phone = models.CharField(max_length=20, unique=True)
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    sent_at = models.DateTimeField()

    def __str__(self):
        return self.phone
