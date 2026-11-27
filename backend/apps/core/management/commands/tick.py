from django.core.management.base import BaseCommand

from apps.core.scheduler import JOBS, run_due


class Command(BaseCommand):
    help = "Run one scheduler pass (use from cron). --job NAME forces specific jobs."

    def add_arguments(self, parser):
        parser.add_argument("--job", action="append", choices=[k for k, _, _ in JOBS])

    def handle(self, *args, **opts):
        for key, result in run_due(only=opts.get("job")).items():
            self.stdout.write(f"{key}: {result}")
