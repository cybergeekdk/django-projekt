from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from urllib.parse import quote

from .models import Server

# Panel-id'er skal matche grafana/dashboards/server-overblik.json
PANELS = [
    (1, "CPU (load / kerner, %)"),
    (2, "RAM-forbrug (%)"),
    (3, "Disk-forbrug (%)"),
]


@login_required
def dashboard(request):
    servers = Server.objects.filter(is_active=True).prefetch_related("containers")
    return render(request, "core/dashboard.html", {"servers": servers})


@login_required
def server_detail(request, pk):
    server = get_object_or_404(Server.objects.prefetch_related("containers"), pk=pk)
    base = f"{settings.GRAFANA_URL}/d-solo/{settings.GRAFANA_DASHBOARD_UID}/_"
    panels = [
        {"title": title,
         "url": f"{base}?orgId=1&panelId={pid}&var-server={quote(server.name)}"
                f"&from=now-24h&to=now&refresh=30s&theme=light"}
        for pid, title in PANELS
    ]
    return render(request, "core/server_detail.html", {
        "server": server, "panels": panels,
        "grafana_full": f"{settings.GRAFANA_URL}/d/{settings.GRAFANA_DASHBOARD_UID}"
                        f"?var-server={quote(server.name)}",
    })
