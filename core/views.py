from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import Server


@login_required
def dashboard(request):
    servers = Server.objects.filter(is_active=True).prefetch_related("containers")
    return render(request, "core/dashboard.html", {"servers": servers})
