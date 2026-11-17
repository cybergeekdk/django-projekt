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

    @property
    def problem_containers(self):
        return [c for c in self.containers.all() if c.has_problem]


class Metric(models.Model):
    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="metrics")
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    reachable = models.BooleanField(default=True)
    error = models.TextField(blank=True)
    load1 = models.FloatField(null=True)
    cpu_percent = models.FloatField(null=True, help_text="Load1 / antal CPU-kerner")
    mem_percent = models.FloatField(null=True)
    swap_percent = models.FloatField(null=True, help_text="Tom hvis serveren ingen swap har")
    disk_percent = models.FloatField(null=True, help_text="Det fyldteste filsystem")
    uptime_seconds = models.PositiveBigIntegerField(null=True)
    reboot_required = models.BooleanField(default=False)
    updates_pending = models.IntegerField(null=True)
    security_updates = models.IntegerField(null=True)
    failed_services = models.IntegerField(null=True)

    class Meta:
        ordering = ["-created"]
        indexes = [models.Index(fields=["server", "-created"])]

    def __str__(self):
        return f"{self.server} @ {self.created:%Y-%m-%d %H:%M}"


class DiskUsage(models.Model):
    metric = models.ForeignKey(Metric, on_delete=models.CASCADE, related_name="disks")
    mount = models.CharField(max_length=300)
    device = models.CharField(max_length=200, blank=True)
    fstype = models.CharField(max_length=30, blank=True)
    size_bytes = models.BigIntegerField(null=True)
    used_percent = models.FloatField()
    inode_percent = models.FloatField(null=True)

    class Meta:
        ordering = ["mount"]

    def __str__(self):
        return f"{self.mount} {self.used_percent}%"


class Container(models.Model):
    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="containers")
    container_id = models.CharField(max_length=64)
    name = models.CharField(max_length=200)
    image = models.CharField(max_length=300)
    state = models.CharField(max_length=30)
    status = models.CharField(max_length=200)
    cpu_percent = models.FloatField(null=True)
    mem_bytes = models.BigIntegerField(null=True)
    mem_percent = models.FloatField(null=True)
    restart_count = models.IntegerField(default=0)
    exit_code = models.IntegerField(null=True)
    oom_killed = models.BooleanField(default=False)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["server", "name"]
        unique_together = [("server", "container_id")]

    def __str__(self):
        return f"{self.name} ({self.state})"

    @property
    def has_problem(self):
        """Crash-loop (mange genstarter), OOM-dræbt eller stoppet med fejlkode."""
        failed_exit = self.state == "exited" and self.exit_code not in (0, None)
        return self.restart_count >= 3 or self.oom_killed or failed_exit


class ContainerStat(models.Model):
    """Historik for ressourceforbrug pr. kørende container (til grafer)."""
    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="container_stats")
    name = models.CharField(max_length=200)
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    cpu_percent = models.FloatField(null=True)
    mem_percent = models.FloatField(null=True)
    mem_bytes = models.BigIntegerField(null=True)

    class Meta:
        ordering = ["-created"]
        indexes = [models.Index(fields=["server", "name", "-created"])]


class FailedService(models.Model):
    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="failed_service_list")
    unit = models.CharField(max_length=200)
    description = models.CharField(max_length=300, blank=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["unit"]
        unique_together = [("server", "unit")]

    def __str__(self):
        return self.unit
