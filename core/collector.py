"""Indsamler målinger fra Linux-servere (lokalt eller via SSH) inkl. Docker-containere."""
import json
import os
import re
import subprocess

from django.db import transaction

from .models import Container, ContainerStat, DiskUsage, FailedService, Metric

SCRIPT = r"""
echo '##load'; cat /proc/loadavg
echo '##cpus'; nproc
echo '##mem'; grep -E '^(MemTotal|MemAvailable|SwapTotal|SwapFree):' /proc/meminfo
echo '##disks'; df -PT 2>/dev/null | tail -n +2
echo '##inodes'; df -Pi 2>/dev/null | tail -n +2
echo '##uptime'; cat /proc/uptime
echo '##reboot'; if [ -e /var/run/reboot-required ]; then echo yes; else echo no; fi
echo '##updates'
if command -v apt-get >/dev/null 2>&1; then
  apt-get -s -o Debug::NoLocking=1 upgrade 2>/dev/null | grep '^Inst' | wc -l
  apt-get -s -o Debug::NoLocking=1 upgrade 2>/dev/null | grep '^Inst' | grep -ci security
else echo -; echo -; fi
echo '##systemd'; if command -v systemctl >/dev/null 2>&1; then echo yes; else echo no; fi
echo '##failed'; systemctl --failed --no-legend --plain --no-pager 2>/dev/null
echo '##docker'; docker ps -a --no-trunc --format '{{json .}}' 2>/dev/null
echo '##dstats'; docker stats --no-stream --no-trunc --format '{{json .}}' 2>/dev/null
echo '##dinspect'
ids=$(docker ps -aq --no-trunc 2>/dev/null)
if [ -n "$ids" ]; then
  docker inspect -f '{{.Id}} {{.RestartCount}} {{.State.ExitCode}} {{.State.OOMKilled}}' $ids 2>/dev/null
fi
exit 0
"""

# Filsystemer og mounts der ikke er rigtige diske (især inde i containere)
PSEUDO_TYPES = {"tmpfs", "devtmpfs", "squashfs", "efivarfs", "fuse.lxcfs", "nsfs", "proc",
                "sysfs", "cgroup", "cgroup2", "ramfs", "iso9660", "overlay"}
SKIP_PREFIXES = ("/proc", "/sys", "/dev", "/run", "/snap", "/var/lib/docker",
                 "/var/lib/containerd", "/var/lib/kubelet")
SKIP_FILES = {"/etc/hosts", "/etc/hostname", "/etc/resolv.conf"}

UNITS = {"b": 1, "kb": 1000, "mb": 1000**2, "gb": 1000**3, "tb": 1000**4,
         "kib": 1024, "mib": 1024**2, "gib": 1024**3, "tib": 1024**4}


def ssh_command(server):
    """Bygger ssh-kommandoen. Kaster RuntimeError ved åbenlyse opsætningsfejl."""
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
           # Husk serverens nøgle første gang (TOFU); afvis den hvis den senere ændres.
           "-o", "StrictHostKeyChecking=accept-new",
           "-p", str(server.ssh_port)]
    known_hosts = os.environ.get("SSH_KNOWN_HOSTS")
    if known_hosts:
        cmd += ["-o", f"UserKnownHostsFile={known_hosts}"]
    if server.ssh_key_path:
        key = server.ssh_key_path
        if key.endswith(".pub"):
            raise RuntimeError(f"{key} er den offentlige nøgle. Angiv den private (uden .pub).")
        if not os.path.isfile(key):
            raise RuntimeError(
                f"Nøglefilen {key} findes ikke her. I Docker skal stien være inde i "
                "containeren, fx /root/.ssh/id_rsa.")
        cmd += ["-i", key, "-o", "IdentitiesOnly=yes"]
    target = f"{server.ssh_user}@{server.host}" if server.ssh_user else server.host
    return cmd + ["--", target, SCRIPT]


def _run(server, timeout=45):
    cmd = ["sh", "-c", SCRIPT] if server.is_local else ssh_command(server)
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
        elif key and line.strip():
            data[key].append(line)
    return data


def _pct(text):
    """'12.5%' -> 12.5, '--' -> None"""
    try:
        return float(str(text).strip().rstrip("%"))
    except ValueError:
        return None


def _size(text):
    """'20.5MiB' -> bytes"""
    m = re.match(r"\s*([\d.]+)\s*([A-Za-z]+)", text or "")
    if not m or m.group(2).lower() not in UNITS:
        return None
    return int(float(m.group(1)) * UNITS[m.group(2).lower()])


def _int(text):
    try:
        return int(str(text).strip())
    except ValueError:
        return None


def parse_disks(disk_lines, inode_lines):
    inodes = {}
    for line in inode_lines:
        p = line.split()
        if len(p) >= 6:
            inodes[" ".join(p[5:])] = _pct(p[4])
    found = {}
    for line in disk_lines:
        p = line.split()
        if len(p) < 7:  # Filesystem Type 1K-blocks Used Available Capacity Mounted-on
            continue
        dev, fstype, size_kb, mount = p[0], p[1], p[2], " ".join(p[6:])
        used = _pct(p[5])
        is_root_overlay = fstype == "overlay" and mount == "/"
        if used is None or (fstype in PSEUDO_TYPES and not is_root_overlay):
            continue
        if mount in SKIP_FILES or mount.startswith(SKIP_PREFIXES):
            continue
        rec = {"mount": mount, "device": dev, "fstype": fstype,
               "size_bytes": (_int(size_kb) or 0) * 1024, "used_percent": used,
               "inode_percent": inodes.get(mount)}
        key = mount if is_root_overlay else dev   # samme disk monteret flere steder -> kort mount vinder
        if key not in found or len(mount) < len(found[key]["mount"]):
            found[key] = rec
    return sorted(found.values(), key=lambda d: d["mount"])


def parse_containers(s):
    containers = {}
    for line in s.get("docker", []):
        c = json.loads(line)
        containers[c["ID"]] = {
            "container_id": c["ID"], "name": c.get("Names", ""), "image": c.get("Image", ""),
            "state": c.get("State", ""), "status": c.get("Status", ""),
        }
    for line in s.get("dstats", []):
        st = json.loads(line)
        c = containers.get(st.get("ID"))
        if c:
            c["cpu_percent"] = _pct(st.get("CPUPerc"))
            c["mem_percent"] = _pct(st.get("MemPerc"))
            c["mem_bytes"] = _size(str(st.get("MemUsage", "")).split("/")[0])
    for line in s.get("dinspect", []):
        p = line.split()
        if len(p) == 4 and p[0] in containers:
            containers[p[0]].update(restart_count=_int(p[1]) or 0, exit_code=_int(p[2]),
                                    oom_killed=p[3] == "true")
    return list(containers.values())


def parse_failed(s):
    if s.get("systemd", ["no"])[0] != "yes":
        return None
    out = []
    for line in s.get("failed", []):
        p = line.lstrip("● ").split(None, 4)
        if p and "." in p[0]:
            out.append({"unit": p[0], "description": p[4] if len(p) > 4 else ""})
    return out


def parse(out):
    s = _sections(out)
    load1 = float(s["load"][0].split()[0])
    cpus = int(s["cpus"][0]) or 1
    mem = {l.split(":")[0]: int(l.split()[1]) for l in s["mem"]}
    swap_total = mem.get("SwapTotal", 0)
    disks = parse_disks(s.get("disks", []), s.get("inodes", []))
    failed = parse_failed(s)
    upd = s.get("updates", ["-", "-"])
    values = {
        "load1": load1,
        "cpu_percent": round(min(load1 / cpus * 100, 999), 1),
        "mem_percent": round(100 * (1 - mem["MemAvailable"] / mem["MemTotal"]), 1),
        "swap_percent": round(100 * (1 - mem["SwapFree"] / swap_total), 1) if swap_total else None,
        "disk_percent": max((d["used_percent"] for d in disks), default=None),
        "uptime_seconds": int(float(s["uptime"][0].split()[0])),
        "reboot_required": s.get("reboot", ["no"])[0] == "yes",
        "updates_pending": _int(upd[0]),
        "security_updates": _int(upd[1]) if len(upd) > 1 else None,
        "failed_services": None if failed is None else len(failed),
    }
    return {"values": values, "disks": disks, "containers": parse_containers(s), "failed": failed}


def collect(server):
    try:
        data = parse(_run(server))
    except Exception as exc:  # noqa: BLE001 - alt skal logges som måling
        return Metric.objects.create(server=server, reachable=False, error=str(exc)[:1000])
    with transaction.atomic():
        metric = Metric.objects.create(server=server, **data["values"])
        DiskUsage.objects.bulk_create(DiskUsage(metric=metric, **d) for d in data["disks"])
        seen = []
        stats = []
        for c in data["containers"]:
            cid = c.pop("container_id")
            Container.objects.update_or_create(server=server, container_id=cid, defaults=c)
            seen.append(cid)
            if c.get("cpu_percent") is not None or c.get("mem_percent") is not None:
                stats.append(ContainerStat(server=server, name=c["name"],
                                           cpu_percent=c.get("cpu_percent"),
                                           mem_percent=c.get("mem_percent"),
                                           mem_bytes=c.get("mem_bytes")))
        server.containers.exclude(container_id__in=seen).delete()
        ContainerStat.objects.bulk_create(stats)
        if data["failed"] is not None:
            units = [f["unit"] for f in data["failed"]]
            for f in data["failed"]:
                FailedService.objects.update_or_create(
                    server=server, unit=f["unit"], defaults={"description": f["description"][:300]})
            server.failed_service_list.exclude(unit__in=units).delete()
    return metric
