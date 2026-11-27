"""python manage.py simulator_guests [PHONE ...]

Adds the guests you use in Africa's Talking's simulator to the data already there, without reseeding: the numbers
given, or SIMULATOR_GUESTS from .env. seed_demo adds them too, so after `seed_demo --reset` there's nothing to run."""

import random

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core.utils import today
from apps.properties.models import Unit

from .seed_demo import Command as SeedDemo


class Command(BaseCommand):
    help = "Make the simulator phones (SIMULATOR_GUESTS or the numbers given) real guests in the current data."

    def add_arguments(self, parser):
        parser.add_argument("phones", nargs="*", help="Up to 5 guest numbers, e.g. +254711000001")

    def handle(self, *args, **opts):
        if not Unit.objects.exists():
            raise CommandError("No homes yet: run `python manage.py seed_demo` first (it adds these guests too).")
        seed = SeedDemo(stdout=self.stdout, stderr=self.stderr)
        seed.rng, seed.t = random.Random(), today()
        with transaction.atomic():
            lines = seed.simulator_guests(opts["phones"] or None)
        if not lines:
            raise CommandError("No numbers: set SIMULATOR_GUESTS in .env or pass them, e.g. +254711000001.")
        for line in lines:
            self.stdout.write(line)
