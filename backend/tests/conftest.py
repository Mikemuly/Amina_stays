from datetime import timedelta

import pytest
from django.conf import settings as django_settings
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bookings.models import Addon
from apps.core.models import SiteSettings
from apps.core.utils import today
from apps.properties.models import Area, Unit


@pytest.fixture(autouse=True)
def _isolated(settings, monkeypatch):
    """Deterministic, offline settings: simulated providers, no background timers, synchronous outbox, and none of the
    keys or numbers from a developer's .env (a test that needs one sets it)."""
    settings.SIM_PAY_DELAY_SECONDS = 0
    settings.OUTBOX_MODE = "sync"
    settings.AT_API_KEY = ""
    settings.AT_WEBHOOK_SECRET = ""
    settings.MPESA_PROVIDER = "simulate"
    settings.CARD_PROVIDER = "simulate"
    settings.SIM_SWAP_PROVIDER = "simulate"
    settings.DEMO = True
    settings.AT_USERNAME, settings.AT_SANDBOX = "sandbox", True
    for key in ("AT_SENDER_ID", "AT_SMS_NUMBER", "AT_USSD_CODE", "AT_VOICE_NUMBER", "AT_WHATSAPP_NUMBER"):
        setattr(settings, key, "")
    for key in ("AT_DATA_PRODUCT", "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "PAYSTACK_SECRET_KEY"):
        setattr(settings, key, "")
    settings.IGLOOHOME_API_KEY = settings.LOCK_PROVIDER_API_BASE = ""
    settings.DARAJA_ENV, settings.DARAJA_SHORTCODE = "sandbox", "174379"
    settings.DARAJA_CONSUMER_KEY = settings.DARAJA_CONSUMER_SECRET = settings.DARAJA_PASSKEY = ""
    settings.AMINA_PHONE = "+254700000001"
    settings.SIMULATOR_GUESTS = []
    settings.FRONTEND_URL = settings.PUBLIC_URL = "http://localhost:3000"
    for var in ("DARAJA_CALLBACK_SECRET", "MPESA_SHORTCODE"):  # read from the environment directly
        monkeypatch.delenv(var, raising=False)
    cache.clear()  # OTP caps and DRF throttles live in the cache
    yield
    cache.clear()


def days(n):
    return today() + timedelta(days=n)


@pytest.fixture
def site(db):
    return SiteSettings.load()


@pytest.fixture
def area(db):
    return Area.objects.create(name="Diani", slug="diani", latitude=-4.3, longitude=39.58)


@pytest.fixture
def unit(area):
    return Unit.objects.create(
        name="Palm Suite",
        area=area,
        base_price=10_000,
        cleaning_fee=2_000,
        max_guests=4,
        min_nights=1,
        cancellation_policy="flexible",
        address="Plot 7, Beach Road",
        wifi_name="PalmWifi",
        wifi_password="coconut-7",
        directions="Past the baobab",
        breakfast_available=True,
    )


@pytest.fixture
def other_unit(area):
    return Unit.objects.create(
        name="Reef Studio", area=area, base_price=5_000, max_guests=2, cancellation_policy="moderate"
    )


@pytest.fixture
def breakfast(db):
    return Addon.objects.create(
        code="breakfast",
        name="Breakfast",
        category="breakfast",
        price=650,
        pricing="per_guest_night",
        options={"styles": ["swahili", "continental", "english", "vegetarian"], "default_time": "08:00"},
    )


@pytest.fixture
def guest(db):
    return User.objects.create_user("+254711000001", name="Wanjiru Test")


@pytest.fixture
def foreign_guest(db):
    return User.objects.create_user("+447700900555", name="Emma Test", nationality="GB")


@pytest.fixture
def host(db):
    return User.objects.create_user(django_settings.AMINA_PHONE, name="Amina", role="owner")


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def guest_api(guest):
    client = APIClient()
    client.force_authenticate(guest)
    return client


@pytest.fixture
def host_api(host):
    client = APIClient()
    client.force_authenticate(host)
    return client
