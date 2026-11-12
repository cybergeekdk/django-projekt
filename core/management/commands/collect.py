import time

from django.core.management.base import BaseCommand

from core.collector import collect
from core.models import Server


class Command(BaseCommand):
    help = "Indsamler målinger fra alle aktive servere."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, help="Gentag hvert N. sekund")

    def handle(self, *args, **opts):
        while True:
            for server in Server.objects.filter(is_active=True):
                m = collect(server)
                status = "OK" if m.reachable else f"FEJL: {m.error}"
                self.stdout.write(f"{server}: {status}")
            if not opts["interval"]:
                break
            time.sleep(opts["interval"])
