"""Go-live readiness: `python manage.py check --deploy` lists every key or setting a live site still needs.

Everything works without them (dry-run messages, simulated payments and locks), which is right for a demo but
not for real guests, so each gap is a warning that names the variable to set."""

from urllib.parse import urlsplit

from django.conf import settings
from django.core.checks import Tags, Warning, register
from django.http.request import validate_host

from apps.core.utils import normalize_phone
from apps.payments.providers import stripe_test_mode, tunnel_host

DEMO_AMINA_PHONE = "+254700000001"  # the AMINA_PHONE default in settings and .env.example


def _warn(n, msg, hint):
    return Warning(msg, hint=hint, id=f"amina.W{n:03d}")


@register(Tags.security, deploy=True)
def go_live_check(app_configs=None, **kwargs):
    s = settings
    found = []
    if s.DEMO:
        found.append(
            _warn(1, "DEMO is on: the Demo Lab, demo endpoints and on-screen login codes are exposed.", "Set DEMO=0.")
        )
    if not s.AT_API_KEY:
        found.append(
            _warn(
                2,
                "Africa's Talking isn't configured: SMS, voice calls, airtime and SIM-swap checks only run as a dry run.",
                "Set AT_USERNAME and AT_API_KEY.",
            )
        )
    elif s.AT_SANDBOX:
        found.append(
            _warn(
                3,
                "AT_USERNAME is 'sandbox': messages reach the Africa's Talking simulator, never real phones.",
                "Use your live app's username and API key.",
            )
        )
    elif not (s.AT_SENDER_ID or s.AT_SMS_NUMBER):
        found.append(
            _warn(
                13,
                "No SMS sender is set: Africa's Talking's default sender only reaches Airtel numbers in Kenya, so "
                "login codes and booking messages won't reach most guests.",
                "Set AT_SENDER_ID to your approved sender ID, or AT_SMS_NUMBER to your two-way shortcode.",
            )
        )
    if not s.AT_WEBHOOK_SECRET:
        found.append(
            _warn(
                4,
                "AT_WEBHOOK_SECRET is empty, so anyone who knows the callback URLs can post fake USSD, SMS, voice and "
                "payment callbacks.",
                "Set a long random value, then register the /at/<secret>/… URLs from the README.",
            )
        )
    public = urlsplit(s.PUBLIC_URL)
    if public.scheme != "https" or public.hostname in ("localhost", "127.0.0.1", None):
        found.append(
            _warn(
                5,
                f"PUBLIC_URL is {s.PUBLIC_URL!r}: Africa's Talking, Safaricom and Paystack can't reach callbacks there.",
                "Set PUBLIC_URL (and FRONTEND_URL) to the site's public https address.",
            )
        )
    if public.hostname and not validate_host(public.hostname, s.ALLOWED_HOSTS):
        found.append(
            _warn(
                15,
                f"ALLOWED_HOSTS doesn't include {public.hostname}, the PUBLIC_URL host: Django answers every "
                "callback there with 400 Bad Request.",
                f"Add {public.hostname} to ALLOWED_HOSTS.",
            )
        )
    if s.DARAJA_ENV == "production" and tunnel_host(s.PUBLIC_URL):
        found.append(
            _warn(
                16,
                f"PUBLIC_URL {s.PUBLIC_URL!r} is a tunnel: Safaricom blocks URL testers such as ngrok and "
                "trycloudflare in production, so M-Pesa callbacks won't arrive.",
                "Serve the site on your own https domain and set PUBLIC_URL to it.",
            )
        )
    if s.MPESA_PROVIDER == "simulate":
        found.append(
            _warn(
                6,
                "M-Pesa is simulated: bookings are confirmed without any money moving.",
                "Set MPESA_PROVIDER=off to take card payments only, or MPESA_PROVIDER=daraja with "
                "DARAJA_CONSUMER_KEY, DARAJA_CONSUMER_SECRET, DARAJA_SHORTCODE and DARAJA_PASSKEY.",
            )
        )
    elif s.MPESA_PROVIDER == "daraja":
        missing = [k for k in ("DARAJA_CONSUMER_KEY", "DARAJA_CONSUMER_SECRET", "DARAJA_PASSKEY") if not getattr(s, k)]
        if missing:
            found.append(
                _warn(7, f"Daraja is selected but {', '.join(missing)} not set.", "Copy them from your Daraja app.")
            )
        if s.DARAJA_ENV != "production":
            found.append(
                _warn(
                    8,
                    "DARAJA_ENV is 'sandbox': M-Pesa prompts go to Safaricom's test system.",
                    "Set DARAJA_ENV=production with your live shortcode and passkey.",
                )
            )
    if s.DARAJA_ENV == "production" and str(s.DARAJA_SHORTCODE).strip() == "174379":
        found.append(
            _warn(
                14,
                "DARAJA_SHORTCODE is 174379, Safaricom's sandbox shortcode, but DARAJA_ENV is 'production'.",
                "Set DARAJA_SHORTCODE (and DARAJA_PASSKEY from the Go-Live email) to your own Paybill or Till.",
            )
        )
    if s.CARD_PROVIDER == "simulate":
        found.append(
            _warn(
                9,
                "Card payments are simulated: the card page confirms bookings without any money moving.",
                "Set STRIPE_SECRET_KEY (and STRIPE_WEBHOOK_SECRET); Stripe is used as soon as the key is set.",
            )
        )
    elif s.CARD_PROVIDER == "paystack" and not s.PAYSTACK_SECRET_KEY:
        found.append(_warn(10, "Paystack is selected but PAYSTACK_SECRET_KEY is empty.", "Copy it from Paystack."))
    elif s.CARD_PROVIDER == "stripe":
        if not s.STRIPE_SECRET_KEY:
            found.append(
                _warn(
                    18,
                    "Stripe is selected but STRIPE_SECRET_KEY is empty, so card payments can't start.",
                    "Copy the secret key from the Stripe Dashboard (Developers > API keys).",
                )
            )
        elif stripe_test_mode():
            found.append(
                _warn(
                    19,
                    "STRIPE_SECRET_KEY is a test key: guests pay with Stripe's test cards and no real money moves.",
                    "Use the live secret key (sk_live_...) and the signing secret of a live-mode webhook.",
                )
            )
        if s.STRIPE_SECRET_KEY and not s.STRIPE_WEBHOOK_SECRET:
            found.append(
                _warn(
                    20,
                    "STRIPE_WEBHOOK_SECRET is empty: a card payment confirms when the guest comes back to the site, "
                    "or within 2 minutes, instead of at once.",
                    f"In the Stripe Dashboard (Developers > Webhooks), add {s.PUBLIC_URL.rstrip('/')}/api/payments/"
                    "stripe/webhook for checkout.session.completed, checkout.session.async_payment_succeeded, "
                    "checkout.session.async_payment_failed and checkout.session.expired; set STRIPE_WEBHOOK_SECRET "
                    "to its signing secret (whsec_...).",
                )
            )
    if not s.ID_ENCRYPTION_KEY:
        found.append(
            _warn(
                11,
                "ID_ENCRYPTION_KEY is empty: guest ID numbers are encrypted with a key derived from SECRET_KEY, so "
                "changing SECRET_KEY would make them unreadable.",
                'Set one: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"',
            )
        )
    if not (s.IGLOOHOME_API_KEY and s.LOCK_PROVIDER_API_BASE):
        found.append(
            _warn(
                12,
                "Smart locks aren't connected: door codes are generated but not programmed into a lock.",
                "Optional: set IGLOOHOME_API_KEY and IGLOOHOME_API_BASE, and each home's lock device ID in the listing "
                "editor (Check-in method).",
            )
        )
    if normalize_phone(s.AMINA_PHONE) == DEMO_AMINA_PHONE:
        found.append(
            _warn(
                17,
                f"AMINA_PHONE is still the demo number {DEMO_AMINA_PHONE}: SOS calls, alerts and approvals would go "
                "there.",
                "Set AMINA_PHONE to the host's real phone number (+254...).",
            )
        )
    return found
