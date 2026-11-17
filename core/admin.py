from django.contrib import admin

from .models import Container, ContainerStat, DiskUsage, FailedService, Metric, Server


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


class DiskInline(admin.TabularInline):
    model = DiskUsage
    extra = 0
    can_delete = False


@admin.register(Metric)
class MetricAdmin(admin.ModelAdmin):
    list_display = ("server", "created", "reachable", "cpu_percent", "mem_percent",
                    "swap_percent", "disk_percent", "failed_services", "updates_pending")
    list_filter = ("server", "reachable", "reboot_required")
    date_hierarchy = "created"
    inlines = [DiskInline]


@admin.register(Container)
class ContainerAdmin(admin.ModelAdmin):
    list_display = ("name", "server", "image", "state", "cpu_percent", "mem_percent",
                    "restart_count", "exit_code", "oom_killed", "updated")
    list_filter = ("server", "state", "oom_killed")
    search_fields = ("name", "image")


@admin.register(FailedService)
class FailedServiceAdmin(admin.ModelAdmin):
    list_display = ("unit", "server", "description", "updated")
    list_filter = ("server",)


admin.site.register(ContainerStat)
