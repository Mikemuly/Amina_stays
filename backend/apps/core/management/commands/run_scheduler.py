import signal

from django.core.management.base import BaseCommand

from apps.core.scheduler import loop


class Command(BaseCommand):
    help = "Run Amina Stays' periodic jobs (holds, message timeline, door codes, checkouts, reviews, iCal…) forever."

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval", type=int, default=None, help="Seconds between passes (default SCHEDULER_INTERVAL_SECONDS)"
        )

    def handle(self, *args, **opts):
        stopping = {"flag": False}

        def stop(*_):
            stopping["flag"] = True

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        loop(opts["interval"], stop=lambda: stopping["flag"])
