from django.conf import settings


def grafana(request):
    return {"grafana_url": settings.GRAFANA_URL}
