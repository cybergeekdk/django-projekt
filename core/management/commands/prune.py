from django.conf import settings
from django.core.management.base import BaseCommand

from core.retention import prune


class Command(BaseCommand):
    help = "Sletter gamle målinger."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=settings.METRICS_RETENTION_DAYS)

    def handle(self, *args, **opts):
        n, s = prune(opts["days"])
        self.stdout.write(f"Slettede {n} rækker (målinger+diske) og {s} container-målinger ældre end {opts['days']} dage.")
