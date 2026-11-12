import os

from django.apps import AppConfig
from django.db.models.signals import post_migrate


def create_default_admin(sender, **kwargs):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    if User.objects.filter(is_superuser=True).exists():
        return
    username = os.environ.get("DJANGO_ADMIN_USER", "admin")
    password = os.environ.get("DJANGO_ADMIN_PASSWORD", "admin")
    User.objects.create_superuser(username, "", password)
    print(f"\n  Standard-admin oprettet: {username} / {password}"
          "\n  SKIFT ADGANGSKODEN før systemet tilgås fra andre maskiner!\n")


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        post_migrate.connect(create_default_admin, sender=self)
