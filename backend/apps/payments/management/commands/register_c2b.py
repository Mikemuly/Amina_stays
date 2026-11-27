import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.payments import c2b
from apps.payments.providers import PaymentError


class Command(BaseCommand):
    help = (
        "Register the Lipa na M-Pesa Paybill (C2B) validation and confirmation URLs with Safaricom Daraja. "
        "In DEMO mode or with simulated M-Pesa it only prints the URLs."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--shortcode", help="Paybill/Till to register (default MPESA_SHORTCODE, else DARAJA_SHORTCODE)"
        )
        parser.add_argument(
            "--force", action="store_true", help="Register even in DEMO mode or with simulated M-Pesa (a sandbox demo)"
        )

    def handle(self, *args, **opts):
        urls = c2b.c2b_urls()
        self.stdout.write(f"Validation URL:   {urls['validation']}")
        self.stdout.write(f"Confirmation URL: {urls['confirmation']}")
        if c2b.callback_secret() == "cb":
            self.stdout.write(
                self.style.WARNING("Set DARAJA_CALLBACK_SECRET (or AT_WEBHOOK_SECRET) so these URLs can't be guessed.")
            )
        if (settings.DEMO or settings.MPESA_PROVIDER == "simulate") and not opts["force"]:
            self.stdout.write(
                self.style.WARNING(
                    "DEMO mode / simulated M-Pesa: nothing was registered with Daraja (use --force for a sandbox demo)."
                )
            )
            return
        try:
            result = c2b.register_c2b_urls(shortcode=opts["shortcode"])
        except PaymentError as e:
            raise CommandError(str(e)) from e
        self.stdout.write(f"Shortcode: {result['shortcode']} ({settings.DARAJA_ENV})")
        self.stdout.write(f"Daraja response: {json.dumps(result['response'])}")
        self.stdout.write(self.style.SUCCESS("Paybill URLs registered."))
