import time

from django.conf import settings
from django.core.management.base import BaseCommand

from core.collector import collect
from core.models import Server
from core.retention import prune


class Command(BaseCommand):
    help = "Indsamler målinger fra alle aktive servere."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, help="Gentag hvert N. sekund")

    def handle(self, *args, **opts):
        last_prune = 0
        while True:
            for server in Server.objects.filter(is_active=True):
                m = collect(server)
                status = "OK" if m.reachable else f"FEJL: {m.error}"
                self.stdout.write(f"{server}: {status}")
            if opts["interval"] and time.time() - last_prune > 3600:  # oprydning højst hver time
                prune(settings.METRICS_RETENTION_DAYS)
                last_prune = time.time()
            if not opts["interval"]:
                break
            time.sleep(opts["interval"])
