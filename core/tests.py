from django.contrib.auth import get_user_model
from django.test import TestCase

from .collector import collect, parse
from .models import Container, Server

SAMPLE = """##load
0.50 0.40 0.30 1/200 999
##cpus
2
##mem
MemTotal:       1000 kB
MemAvailable:    250 kB
##disk
/dev/sda1 100 40 60 40% /
##uptime
3600.55 7000.1
##docker
{"ID":"abc","Names":"web","Image":"nginx","State":"running","Status":"Up 2 hours"}
"""


class CollectorTests(TestCase):
    def test_parse(self):
        values, containers = parse(SAMPLE)
        self.assertEqual(values["cpu_percent"], 25.0)
        self.assertEqual(values["mem_percent"], 75.0)
        self.assertEqual(values["disk_percent"], 40.0)
        self.assertEqual(containers[0]["Names"], "web")

    def test_collect_local(self):
        m = collect(Server.objects.create(name="lokal", host="localhost"))
        self.assertTrue(m.reachable, m.error)

    def test_unreachable_is_recorded(self):
        m = collect(Server.objects.create(name="x", host="nonexistent.invalid", ssh_user="u"))
        self.assertFalse(m.reachable)


class AccessTests(TestCase):
    def test_default_admin_exists(self):
        self.assertTrue(get_user_model().objects.filter(username="admin", is_superuser=True).exists())

    def test_dashboard_requires_login(self):
        self.assertEqual(self.client.get("/").status_code, 302)
        self.assertTrue(self.client.login(username="admin", password="admin"))
        self.assertEqual(self.client.get("/").status_code, 200)
