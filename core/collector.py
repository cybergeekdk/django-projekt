"""Indsamler målinger fra Linux-servere (lokalt eller via SSH) inkl. Docker-containere."""
import json
import subprocess

from .models import Container, Metric

SCRIPT = r"""
echo '##load'; cat /proc/loadavg
echo '##cpus'; nproc
echo '##mem'; grep -E '^(MemTotal|MemAvailable):' /proc/meminfo
echo '##disk'; df -P / | tail -1
echo '##uptime'; cat /proc/uptime
echo '##docker'; docker ps -a --no-trunc --format '{{json .}}' 2>/dev/null
exit 0
"""


def _run(server, timeout=20):
    if server.is_local:
        cmd = ["sh", "-c", SCRIPT]
    else:
        cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
               "-p", str(server.ssh_port)]
        if server.ssh_key_path:
            cmd += ["-i", server.ssh_key_path]
        target = f"{server.ssh_user}@{server.host}" if server.ssh_user else server.host
        cmd += ["--", target, SCRIPT]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or f"Exit {res.returncode}")
    return res.stdout


def _sections(out):
    data, key = {}, None
    for line in out.splitlines():
        if line.startswith("##"):
            key = line[2:]
            data[key] = []
        elif key:
            data[key].append(line)
    return data


def parse(out):
    s = _sections(out)
    load1 = float(s["load"][0].split()[0])
    cpus = int(s["cpus"][0]) or 1
    mem = {l.split(":")[0]: int(l.split()[1]) for l in s["mem"] if l}
    disk = s["disk"][0].split()[4].rstrip("%")
    containers = []
    for line in s.get("docker", []):
        if line.strip():
            c = json.loads(line)
            containers.append(c)
    return {
        "load1": load1,
        "cpu_percent": round(min(load1 / cpus * 100, 999), 1),
        "mem_percent": round(100 * (1 - mem["MemAvailable"] / mem["MemTotal"]), 1),
        "disk_percent": float(disk),
        "uptime_seconds": int(float(s["uptime"][0].split()[0])),
    }, containers


def collect(server):
    try:
        values, containers = parse(_run(server))
    except Exception as exc:  # noqa: BLE001 - alt skal logges som måling
        return Metric.objects.create(server=server, reachable=False, error=str(exc)[:1000])
    metric = Metric.objects.create(server=server, **values)
    seen = []
    for c in containers:
        Container.objects.update_or_create(
            server=server, container_id=c["ID"],
            defaults={"name": c.get("Names", ""), "image": c.get("Image", ""),
                      "state": c.get("State", ""), "status": c.get("Status", "")},
        )
        seen.append(c["ID"])
    server.containers.exclude(container_id__in=seen).delete()
    return metric
