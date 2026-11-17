from django.contrib.auth import get_user_model
from django.test import TestCase

from .collector import collect, parse, ssh_command
from .models import ContainerStat, DiskUsage, Metric, Server

SAMPLE = """##load
0.50 0.40 0.30 1/200 999
##cpus
2
##mem
MemTotal:       1000 kB
MemAvailable:    250 kB
SwapTotal:       400 kB
SwapFree:        300 kB
##disks
/dev/sda1 ext4 1000 400 600 40% /
/dev/sdb1 xfs 2000 1900 100 95% /data
/dev/sda1 ext4 1000 400 600 40% /etc/hosts
overlay overlay 500 100 400 20% /var/lib/docker/overlay2/x/merged
tmpfs tmpfs 100 1 99 1% /run
##inodes
/dev/sda1 100 10 90 10% /
/dev/sdb1 100 97 3 97% /data
##uptime
3600.55 7000.1
##reboot
yes
##updates
12
3
##systemd
yes
##failed
● nginx.service loaded failed failed A high performance web server
##docker
{"ID":"abc","Names":"web","Image":"nginx","State":"running","Status":"Up 2 hours"}
{"ID":"def","Names":"job","Image":"busybox","State":"exited","Status":"Exited (1) 1h ago"}
##dstats
{"ID":"abc","Name":"web","CPUPerc":"12.50%","MemPerc":"1.50%","MemUsage":"20MiB / 1.9GiB"}
##dinspect
abc 7 0 false
def 0 1 true
"""


class CollectorTests(TestCase):
    def test_parse_host_values(self):
        v = parse(SAMPLE)["values"]
        self.assertEqual(v["cpu_percent"], 25.0)
        self.assertEqual(v["mem_percent"], 75.0)
        self.assertEqual(v["swap_percent"], 25.0)
        self.assertEqual(v["disk_percent"], 95.0)          # fyldteste filsystem
        self.assertTrue(v["reboot_required"])
        self.assertEqual((v["updates_pending"], v["security_updates"]), (12, 3))
        self.assertEqual(v["failed_services"], 1)

    def test_parse_disks_filters_pseudo_and_duplicates(self):
        disks = parse(SAMPLE)["disks"]
        self.assertEqual([d["mount"] for d in disks], ["/", "/data"])
        self.assertEqual(disks[1]["inode_percent"], 97.0)

    def test_parse_failed_services(self):
        f = parse(SAMPLE)["failed"]
        self.assertEqual(f[0]["unit"], "nginx.service")
        self.assertIn("web server", f[0]["description"])

    def test_parse_containers(self):
        c = {x["name"]: x for x in parse(SAMPLE)["containers"]}
        self.assertEqual(c["web"]["cpu_percent"], 12.5)
        self.assertEqual(c["web"]["mem_bytes"], 20 * 1024**2)
        self.assertEqual(c["web"]["restart_count"], 7)
        self.assertTrue(c["job"]["oom_killed"])
        self.assertEqual(c["job"]["exit_code"], 1)

    def test_no_swap_and_no_systemd(self):
        out = SAMPLE.replace("SwapTotal:       400 kB", "SwapTotal:         0 kB").replace("##systemd\nyes", "##systemd\nno")
        p = parse(out)
        self.assertIsNone(p["values"]["swap_percent"])
        self.assertIsNone(p["values"]["failed_services"])

    def test_collect_local(self):
        m = collect(Server.objects.create(name="lokal", host="localhost"))
        self.assertTrue(m.reachable, m.error)
        self.assertIsNotNone(m.disk_percent)

    def test_collect_stores_everything(self):
        from unittest import mock
        srv = Server.objects.create(name="s", host="localhost")
        with mock.patch("core.collector._run", return_value=SAMPLE):
            m = collect(srv)
            collect(srv)   # to gange: ingen dubletter af tjenester/containere
        self.assertEqual(m.disks.count(), 2)
        self.assertEqual(srv.containers.count(), 2)
        self.assertEqual(srv.failed_service_list.count(), 1)
        self.assertEqual(ContainerStat.objects.filter(server=srv).count(), 2)
        self.assertEqual([c.name for c in srv.problem_containers], ["job", "web"])

    def test_unreachable_is_recorded(self):
        m = collect(Server.objects.create(name="x", host="nonexistent.invalid", ssh_user="u"))
        self.assertFalse(m.reachable)


class RetentionTests(TestCase):
    def test_prune_removes_old_rows_only(self):
        from datetime import timedelta
        from django.utils import timezone
        from .retention import prune
        srv = Server.objects.create(name="s", host="localhost")
        old = Metric.objects.create(server=srv, load1=1)
        new = Metric.objects.create(server=srv, load1=1)
        DiskUsage.objects.create(metric=old, mount="/", used_percent=1)
        Metric.objects.filter(pk=old.pk).update(created=timezone.now() - timedelta(days=40))
        prune(30)
        self.assertEqual(list(Metric.objects.values_list("pk", flat=True)), [new.pk])
        self.assertEqual(DiskUsage.objects.count(), 0)


class AccessTests(TestCase):
    def test_default_admin_exists(self):
        self.assertTrue(get_user_model().objects.filter(username="admin", is_superuser=True).exists())

    def test_detail_has_grafana_panels(self):
        srv = Server.objects.create(name="web 1", host="localhost")
        self.client.login(username="admin", password="admin")
        r = self.client.get(f"/servers/{srv.pk}/")
        self.assertContains(r, "d-solo/server-overblik")
        self.assertContains(r, "var-server=web%201")
        self.assertContains(r, "panelId=7")

    def test_pages_render_with_collected_data(self):
        from unittest import mock
        srv = Server.objects.create(name="s", host="localhost")
        with mock.patch("core.collector._run", return_value=SAMPLE):
            collect(srv)
        self.client.login(username="admin", password="admin")
        home = self.client.get("/")
        self.assertContains(home, "fejlede tjenester")
        self.assertContains(home, "Genstart påkrævet")
        detail = self.client.get(f"/servers/{srv.pk}/")
        self.assertContains(detail, "/data")
        self.assertContains(detail, "nginx.service")
        self.assertContains(detail, "OOM")

    def test_login_page(self):
        self.assertEqual(self.client.get("/login/").status_code, 200)

    def test_dashboard_requires_login(self):
        self.assertEqual(self.client.get("/").status_code, 302)
        self.assertTrue(self.client.login(username="admin", password="admin"))
        self.assertEqual(self.client.get("/").status_code, 200)


class SshCommandTests(TestCase):
    def test_accepts_new_host_keys_and_uses_private_key(self):
        import os, tempfile
        with tempfile.NamedTemporaryFile() as key:
            srv = Server(name="r", host="10.0.0.5", ssh_user="u", ssh_key_path=key.name)
            cmd = ssh_command(srv)
        self.assertIn("StrictHostKeyChecking=accept-new", cmd)
        self.assertIn(key.name, cmd)
        self.assertIn("u@10.0.0.5", cmd)

    def test_public_key_is_rejected_with_clear_message(self):
        srv = Server(name="r", host="10.0.0.5", ssh_key_path="/root/.ssh/id_rsa.pub")
        with self.assertRaisesMessage(RuntimeError, "offentlige"):
            ssh_command(srv)

    def test_missing_key_file_is_explained(self):
        srv = Server(name="r", host="10.0.0.5", ssh_key_path="/home/x/.ssh/id_rsa")
        with self.assertRaisesMessage(RuntimeError, "inde i"):
            ssh_command(srv)
