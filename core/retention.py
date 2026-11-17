from datetime import timedelta

from django.utils import timezone

from .models import ContainerStat, Metric


def prune(days):
    """Sletter målinger (og tilhørende diskrækker) ældre end `days` dage."""
    cutoff = timezone.now() - timedelta(days=days)
    metrics, _ = Metric.objects.filter(created__lt=cutoff).delete()
    stats, _ = ContainerStat.objects.filter(created__lt=cutoff).delete()
    return metrics, stats
