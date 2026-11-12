from django.contrib import admin

from .models import Container, Metric, Server


@admin.register(Server)
class ServerAdmin(admin.ModelAdmin):
    list_display = ("name", "host", "ssh_port", "ssh_user", "is_active")
    list_filter = ("is_active",)
    actions = ["collect_now"]

    @admin.action(description="Indsaml målinger nu")
    def collect_now(self, request, queryset):
        from .collector import collect
        for s in queryset:
            m = collect(s)
            self.message_user(request, f"{s}: {'OK' if m.reachable else m.error}")


@admin.register(Metric)
class MetricAdmin(admin.ModelAdmin):
    list_display = ("server", "created", "reachable", "cpu_percent", "mem_percent", "disk_percent")
    list_filter = ("server", "reachable")
    date_hierarchy = "created"


@admin.register(Container)
class ContainerAdmin(admin.ModelAdmin):
    list_display = ("name", "server", "image", "state", "status", "updated")
    list_filter = ("server", "state")
    search_fields = ("name", "image")
