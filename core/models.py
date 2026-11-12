from django.core.validators import RegexValidator
from django.db import models

safe = RegexValidator(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", "Ugyldig værdi.")


class Server(models.Model):
    name = models.CharField(max_length=100, unique=True)
    host = models.CharField(
        max_length=255, validators=[safe],
        help_text="Hostnavn/IP. Brug 'localhost' for serveren Django kører på.",
    )
    ssh_port = models.PositiveIntegerField(default=22)
    ssh_user = models.CharField(max_length=64, blank=True, validators=[safe])
    ssh_key_path = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def is_local(self):
        return self.host in ("localhost", "127.0.0.1", "::1")

    @property
    def latest(self):
        return self.metrics.first()


class Metric(models.Model):
    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="metrics")
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    reachable = models.BooleanField(default=True)
    error = models.TextField(blank=True)
    load1 = models.FloatField(null=True)
    cpu_percent = models.FloatField(null=True, help_text="Load1 / antal CPU-kerner")
    mem_percent = models.FloatField(null=True)
    disk_percent = models.FloatField(null=True)
    uptime_seconds = models.PositiveBigIntegerField(null=True)

    class Meta:
        ordering = ["-created"]
        indexes = [models.Index(fields=["server", "-created"])]

    def __str__(self):
        return f"{self.server} @ {self.created:%Y-%m-%d %H:%M}"


class Container(models.Model):
    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="containers")
    container_id = models.CharField(max_length=64)
    name = models.CharField(max_length=200)
    image = models.CharField(max_length=300)
    state = models.CharField(max_length=30)
    status = models.CharField(max_length=200)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["server", "name"]
        unique_together = [("server", "container_id")]

    def __str__(self):
        return f"{self.name} ({self.state})"
