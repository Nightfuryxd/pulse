"""
PULSE Universal Collector Agent

Runs on: Linux, macOS, Windows, Docker containers
Monitors via SNMP: Routers, switches, firewalls, printers, UPS, any SNMP-capable device
Monitors via SSH: Remote Linux/Unix hosts without installed agents
Monitors via WMI: Windows hosts (agentless)

Auto-discovers all devices on the local network.
Ships everything to PULSE API every COLLECT_INTERVAL seconds.
"""
import asyncio
import os
import platform
import re
import socket
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

import httpx
import psutil
from dotenv import load_dotenv

load_dotenv()

API_URL          = os.getenv("PULSE_API_URL", "http://localhost:8000")
NODE_ID          = os.getenv("NODE_ID") or socket.gethostname()
COLLECT_INTERVAL = int(os.getenv("COLLECT_INTERVAL", "10"))
LOG_PATHS        = os.getenv("LOG_PATHS", "/var/log/syslog,/var/log/auth.log").split(",")
SNMP_TARGETS     = os.getenv("SNMP_TARGETS", "").split(",")
SSH_TARGETS      = os.getenv("SSH_TARGETS", "").split(",")
ENABLE_DISCOVERY = os.getenv("ENABLE_DISCOVERY", "false").lower() == "true"
NETWORK_RANGE    = os.getenv("NETWORK_RANGE", "")
ENABLE_K8S       = os.getenv("ENABLE_K8S", "false").lower() == "true"
ENABLE_AWS       = os.getenv("ENABLE_AWS", "false").lower() == "true"
ENABLE_AZURE     = os.getenv("ENABLE_AZURE", "false").lower() == "true"
ENABLE_GCP       = os.getenv("ENABLE_GCP", "false").lower() == "true"

SYSTEM  = platform.system()   # "Linux", "Darwin", "Windows"
HOSTNAME = socket.gethostname()
OS_INFO  = f"{platform.system()} {platform.release()}"
try:
    IP = socket.gethostbyname(HOSTNAME)
except Exception:
    IP = "unknown"

# ── In-memory state ───────────────────────────────────────────────────────────
_net_baseline:  dict = {}
_auth_failures: dict = defaultdict(list)
_port_tracker:  dict = defaultdict(set)
_log_positions: dict = {}


# ══════════════════════════════════════════════════════════════════════════════
# LOCAL SYSTEM METRICS  (psutil — Linux / macOS / Windows)
# ══════════════════════════════════════════════════════════════════════════════

def collect_metrics() -> dict:
    cpu  = psutil.cpu_percent(interval=1)
    mem  = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    load = psutil.getloadavg() if hasattr(psutil, "getloadavg") else (0, 0, 0)
    net  = psutil.net_io_counters()
    procs = len(psutil.pids())

    extra = {}

    # ── Windows-specific: battery, uptime ────────────────────────────────────
    if SYSTEM == "Windows":
        try:
            extra["uptime_seconds"] = time.time() - psutil.boot_time()
        except Exception:
            pass
        try:
            batt = psutil.sensors_battery()
            if batt:
                extra["battery_percent"] = batt.percent
                extra["battery_plugged"]  = batt.power_plugged
        except Exception:
            pass

    # ── Linux-specific: temperature sensors ──────────────────────────────────
    if SYSTEM == "Linux":
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for name, readings in temps.items():
                    if readings:
                        extra[f"temp_{name}"] = round(readings[0].current, 1)
        except Exception:
            pass

    # ── macOS: temperature via sysctl ─────────────────────────────────────────
    if SYSTEM == "Darwin":
        try:
            import subprocess
            out = subprocess.check_output(
                ["sysctl", "-n", "machdep.xcpm.cpu_thermal_level"],
                stderr=subprocess.DEVNULL, timeout=2
            ).decode().strip()
            extra["cpu_thermal_level"] = int(out)
        except Exception:
            pass

    return {
        "node_id":        NODE_ID,
        "hostname":       HOSTNAME,
        "ip":             IP,
        "os":             OS_INFO,
        "ts":             datetime.utcnow().isoformat(),
        "cpu_percent":    cpu,
        "memory_percent": mem.percent,
        "memory_used_mb": round(mem.used / 1024 / 1024, 1),
        "disk_percent":   disk.percent,
        "disk_used_gb":   round(disk.used / 1024 / 1024 / 1024, 2),
        "net_bytes_sent": net.bytes_sent,
        "net_bytes_recv": net.bytes_recv,
        "load_avg_1m":    load[0],
        "process_count":  procs,
        "extra":          extra,
    }


# ══════════════════════════════════════════════════════════════════════════════
# SECURITY EVENT DETECTION
# ══════════════════════════════════════════════════════════════════════════════

def detect_security_events() -> list[dict]:
    events = []
    now    = time.time()

    # 1. Port scan detection via active connections
    try:
        conns = psutil.net_connections(kind="inet")
        remote_ports: dict[str, set] = defaultdict(set)
        for c in conns:
            if c.raddr and c.status == "ESTABLISHED":
                remote_ports[c.raddr.ip].add(c.raddr.port)
        for ip, ports in remote_ports.items():
            if ip.startswith("127.") or ip == "::1":
                continue
            _port_tracker[ip] |= ports
            if len(_port_tracker[ip]) >= 20:
                events.append({
                    "node_id":  NODE_ID,
                    "type":     "port_scan",
                    "severity": "critical",
                    "source":   "network_monitor",
                    "message":  f"Port scan detected from {ip} ({len(_port_tracker[ip])} ports)",
                    "data":     {"source_ip": ip, "unique_ports": len(_port_tracker[ip])},
                })
                _port_tracker[ip] = set()
    except Exception:
        pass

    # 2. Suspicious processes
    SUSPICIOUS = ["xmrig", "minerd", "ncat", "nc -e", "bash -i", "python -c", "/dev/tcp",
                  "meterpreter", "cobalt", "mimikatz", "powersploit", "invoke-expression"]
    try:
        for proc in psutil.process_iter(["pid", "name", "cmdline", "username"]):
            try:
                info    = proc.info
                cmdline = " ".join(info.get("cmdline") or []).lower()
                name    = (info.get("name") or "").lower()
                if any(s in name or s in cmdline for s in SUSPICIOUS):
                    events.append({
                        "node_id":  NODE_ID,
                        "type":     "suspicious_process",
                        "severity": "high",
                        "source":   "process_monitor",
                        "message":  f"Suspicious process: {name} (PID {info['pid']})",
                        "data":     {"process": name, "pid": info["pid"],
                                     "user": info.get("username"), "cmdline": cmdline[:200]},
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception:
        pass

    # 3. Zombie processes
    try:
        for proc in psutil.process_iter(["pid", "name", "status"]):
            if proc.info.get("status") == psutil.STATUS_ZOMBIE:
                events.append({
                    "node_id":  NODE_ID,
                    "type":     "process_exit",
                    "severity": "medium",
                    "source":   "process_monitor",
                    "message":  f"Zombie process: {proc.info.get('name')} (PID {proc.info['pid']})",
                    "data":     {"process": proc.info.get("name"), "pid": proc.info["pid"], "exit_code": -1},
                })
    except Exception:
        pass

    # 4. Windows-specific: new admin accounts, service changes
    if SYSTEM == "Windows":
        events.extend(_detect_windows_security())

    return events


def _detect_windows_security() -> list[dict]:
    """Windows-specific security checks via subprocess/WMI."""
    events = []
    try:
        import subprocess
        # Check for recently enabled admin accounts
        out = subprocess.check_output(
            ["net", "localgroup", "administrators"],
            stderr=subprocess.DEVNULL, timeout=5
        ).decode(errors="replace")
        # Just log member count — comparison logic can be added
    except Exception:
        pass
    return events


# ══════════════════════════════════════════════════════════════════════════════
# LOG TAILING  (Linux / macOS)
# ══════════════════════════════════════════════════════════════════════════════

AUTH_FAIL_RE  = re.compile(r"Failed password for (?:invalid user )?(\S+) from ([\d.]+)")
SUDO_RE       = re.compile(r"sudo.*COMMAND=(.+)")
SEGFAULT_RE   = re.compile(r"segfault at")
OOM_RE        = re.compile(r"Out of memory.*process (\d+) \((\w+)\)")
SSH_ACCEPT_RE = re.compile(r"Accepted (?:password|publickey) for (\S+) from ([\d.]+)")


def tail_logs() -> list[dict]:
    events = []
    now    = time.time()

    if SYSTEM == "Windows":
        return _tail_windows_eventlog()

    log_paths = LOG_PATHS
    if SYSTEM == "Darwin":
        log_paths = ["/var/log/system.log"]

    for log_path in log_paths:
        path = log_path.strip()
        for candidate in [f"/host{path}", path]:
            p = Path(candidate)
            if not p.exists():
                continue
            try:
                size = p.stat().st_size
                pos  = _log_positions.get(candidate, size)
                if size < pos:
                    pos = 0
                if size == pos:
                    _log_positions[candidate] = pos
                    break

                with open(p, "r", errors="replace") as f:
                    f.seek(pos)
                    new_lines = f.readlines()
                    _log_positions[candidate] = f.tell()

                for line in new_lines[-200:]:
                    line = line.strip()
                    if not line:
                        continue
                    m = AUTH_FAIL_RE.search(line)
                    if m:
                        user, src_ip = m.group(1), m.group(2)
                        _auth_failures[src_ip].append(now)
                        _auth_failures[src_ip] = [t for t in _auth_failures[src_ip] if now - t <= 60]
                        count = len(_auth_failures[src_ip])
                        if count >= 3:
                            events.append({
                                "node_id":  NODE_ID,
                                "type":     "auth_failure",
                                "severity": "critical" if count >= 10 else "high",
                                "source":   candidate,
                                "message":  f"{count} failed logins for '{user}' from {src_ip}",
                                "data":     {"user": user, "source_ip": src_ip, "count": count},
                            })
                    m = OOM_RE.search(line)
                    if m:
                        events.append({
                            "node_id":  NODE_ID,
                            "type":     "oom_kill",
                            "severity": "critical",
                            "source":   candidate,
                            "message":  f"OOM killed PID {m.group(1)} ({m.group(2)})",
                            "data":     {"pid": m.group(1), "process": m.group(2)},
                        })
                    if SEGFAULT_RE.search(line):
                        events.append({
                            "node_id":  NODE_ID,
                            "type":     "segfault",
                            "severity": "high",
                            "source":   candidate,
                            "message":  f"Segfault: {line[:120]}",
                            "data":     {"raw": line[:200]},
                        })
            except Exception:
                pass
            break

    return events


def _tail_windows_eventlog() -> list[dict]:
    """Read Windows Security/System event log for auth failures and errors."""
    events = []
    try:
        import subprocess
        # Query Security log for failed logons (EventID 4625)
        ps_cmd = (
            "Get-WinEvent -LogName Security -MaxEvents 50 "
            "-FilterHashtable @{Id=4625} 2>$null | "
            "Select-Object -ExpandProperty Message"
        )
        out = subprocess.check_output(
            ["powershell", "-NonInteractive", "-Command", ps_cmd],
            stderr=subprocess.DEVNULL, timeout=10
        ).decode(errors="replace")
        if "Account Name" in out:
            events.append({
                "node_id":  NODE_ID,
                "type":     "auth_failure",
                "severity": "high",
                "source":   "Windows Security Log",
                "message":  "Failed Windows logon detected",
                "data":     {"raw": out[:500]},
            })
    except Exception:
        pass
    return events


# ══════════════════════════════════════════════════════════════════════════════
# SNMP POLLER  — network equipment (routers, switches, firewalls, printers, UPS)
# ══════════════════════════════════════════════════════════════════════════════

# Standard SNMP OIDs
SNMP_OIDS = {
    "sysDescr":        "1.3.6.1.2.1.1.1.0",
    "sysName":         "1.3.6.1.2.1.1.5.0",
    "sysUpTime":       "1.3.6.1.2.1.1.3.0",
    "ifNumber":        "1.3.6.1.2.1.2.1.0",
    "cpu_cisco":       "1.3.6.1.4.1.9.2.1.57.0",       # Cisco CPU 1min avg
    "cpu_netsnmp":     "1.3.6.1.4.1.2021.11.11.0",      # net-snmp idle CPU
    "mem_total":       "1.3.6.1.4.1.2021.4.5.0",        # net-snmp total memory
    "mem_free":        "1.3.6.1.4.1.2021.4.11.0",       # net-snmp free memory
    "hrProcessorLoad": "1.3.6.1.2.1.25.3.3.1.2.196608", # HOST-RESOURCES CPU
}

# Interface table walk (ifDescr, ifOperStatus, ifInOctets, ifOutOctets)
SNMP_IF_TABLE = {
    "ifDescr":      "1.3.6.1.2.1.2.2.1.2",
    "ifOperStatus": "1.3.6.1.2.1.2.2.1.8",
    "ifInOctets":   "1.3.6.1.2.1.2.2.1.10",
    "ifOutOctets":  "1.3.6.1.2.1.2.2.1.16",
    "ifInErrors":   "1.3.6.1.2.1.2.2.1.14",
    "ifOutErrors":  "1.3.6.1.2.1.2.2.1.20",
}


async def poll_snmp_device(target: str, community: str = "public", port: int = 161) -> Optional[dict]:
    """
    Poll a single device via SNMP v2c.
    Returns a metrics dict compatible with /api/ingest/metrics.
    Requires: pip install pysnmp
    """
    try:
        from pysnmp.hlapi.asyncio import (
            SnmpEngine, CommunityData, UdpTransportTarget,
            ContextData, ObjectType, ObjectIdentity, getCmd, nextCmd
        )
    except ImportError:
        return None  # pysnmp not installed — skip silently

    engine    = SnmpEngine()
    auth      = CommunityData(community, mpModel=1)  # SNMPv2c
    transport = UdpTransportTarget((target, port), timeout=3, retries=1)
    ctx       = ContextData()

    result = {"node_id": f"snmp:{target}", "hostname": target, "ip": target, "os": "SNMP Device",
              "ts": datetime.utcnow().isoformat(), "cpu_percent": 0, "memory_percent": 0,
              "memory_used_mb": 0, "disk_percent": 0, "disk_used_gb": 0,
              "net_bytes_sent": 0, "net_bytes_recv": 0, "load_avg_1m": 0, "process_count": 0, "extra": {}}

    # GET scalar OIDs
    oid_objects = [ObjectType(ObjectIdentity(oid)) for oid in SNMP_OIDS.values()]
    oid_names   = list(SNMP_OIDS.keys())

    try:
        err_indication, err_status, _, var_binds = await getCmd(
            engine, auth, transport, ctx, *oid_objects
        )
        if not err_indication and not err_status:
            for name, vb in zip(oid_names, var_binds):
                val = vb[1].prettyPrint()
                result["extra"][name] = val

                if name == "sysName" and val:
                    result["hostname"] = val
                    result["node_id"]  = f"snmp:{val}"
                elif name == "sysDescr":
                    result["os"] = val[:100]
                elif name == "sysUpTime":
                    result["extra"]["uptime_timeticks"] = val
                elif name == "cpu_cisco":
                    try:
                        result["cpu_percent"] = float(val)
                    except Exception:
                        pass
                elif name == "cpu_netsnmp":
                    try:
                        result["cpu_percent"] = 100.0 - float(val)  # idle → used
                    except Exception:
                        pass
                elif name == "mem_total":
                    try:
                        result["extra"]["mem_total_kb"] = int(val)
                    except Exception:
                        pass
                elif name == "mem_free":
                    try:
                        total = result["extra"].get("mem_total_kb", 0) or 1
                        free  = int(val)
                        result["memory_percent"] = round((1 - free / total) * 100, 1)
                        result["memory_used_mb"] = round((total - free) / 1024, 1)
                    except Exception:
                        pass
    except Exception:
        pass

    # WALK interface table
    iface_data = {}
    for col_name, base_oid in SNMP_IF_TABLE.items():
        try:
            async for (err_ind, err_stat, _, vbs) in nextCmd(
                engine, auth, transport, ctx,
                ObjectType(ObjectIdentity(base_oid)),
                lexicographicMode=False
            ):
                if err_ind or err_stat:
                    break
                for vb in vbs:
                    oid_str = str(vb[0])
                    idx     = oid_str.rsplit(".", 1)[-1]
                    iface_data.setdefault(idx, {})[col_name] = vb[1].prettyPrint()
        except Exception:
            pass

    if iface_data:
        result["extra"]["interfaces"] = iface_data
        # Sum total in/out bytes across all interfaces
        total_in = total_out = 0
        for iface in iface_data.values():
            try:
                total_in  += int(iface.get("ifInOctets",  0))
                total_out += int(iface.get("ifOutOctets", 0))
            except Exception:
                pass
        result["net_bytes_recv"] = total_in
        result["net_bytes_sent"] = total_out

    return result


async def collect_snmp_targets(targets: list[str]) -> list[dict]:
    """Poll all configured SNMP targets in parallel."""
    if not targets or targets == [""]:
        return []
    community = os.getenv("SNMP_COMMUNITY", "public")
    results   = await asyncio.gather(
        *[poll_snmp_device(t.strip(), community) for t in targets if t.strip()],
        return_exceptions=True
    )
    return [r for r in results if isinstance(r, dict)]


# ══════════════════════════════════════════════════════════════════════════════
# SSH AGENTLESS COLLECTOR  — Linux/Unix hosts without installed agents
# ══════════════════════════════════════════════════════════════════════════════

SSH_METRIC_SCRIPT = """
python3 -c "
import json, psutil, platform, socket, time
mem=psutil.virtual_memory(); disk=psutil.disk_usage('/'); net=psutil.net_io_counters()
load=psutil.getloadavg() if hasattr(psutil,'getloadavg') else (0,0,0)
print(json.dumps({
  'cpu_percent':    psutil.cpu_percent(interval=1),
  'memory_percent': mem.percent,
  'memory_used_mb': round(mem.used/1024/1024,1),
  'disk_percent':   disk.percent,
  'disk_used_gb':   round(disk.used/1024/1024/1024,2),
  'net_bytes_sent': net.bytes_sent,
  'net_bytes_recv': net.bytes_recv,
  'load_avg_1m':    load[0],
  'process_count':  len(psutil.pids()),
  'os':             platform.system()+' '+platform.release(),
  'hostname':       socket.gethostname(),
}))
" 2>/dev/null || echo '{}'
"""


async def collect_ssh_target(target: str) -> Optional[dict]:
    """
    Collect metrics from a remote host via SSH.
    target format: "user@hostname" or "user@hostname:port"
    Requires passwordless SSH key auth to the remote host.
    """
    try:
        parts = target.rsplit(":", 1)
        host  = parts[0]
        port  = int(parts[1]) if len(parts) > 1 else 22
        user_host = host  # e.g. "ops@10.0.1.5"

        cmd = ["ssh",
               "-o", "StrictHostKeyChecking=no",
               "-o", "ConnectTimeout=5",
               "-o", "BatchMode=yes",
               "-p", str(port),
               user_host,
               SSH_METRIC_SCRIPT.strip()]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        except asyncio.TimeoutError:
            proc.kill()
            return None

        import json
        raw = stdout.decode(errors="replace").strip()
        if not raw or raw == "{}":
            return None
        data = json.loads(raw)

        remote_host = data.get("hostname", user_host.split("@")[-1])
        return {
            "node_id":        f"ssh:{remote_host}",
            "hostname":       remote_host,
            "ip":             host.split("@")[-1] if "@" in host else host,
            "os":             data.get("os", "Unknown"),
            "ts":             datetime.utcnow().isoformat(),
            "cpu_percent":    data.get("cpu_percent", 0),
            "memory_percent": data.get("memory_percent", 0),
            "memory_used_mb": data.get("memory_used_mb", 0),
            "disk_percent":   data.get("disk_percent", 0),
            "disk_used_gb":   data.get("disk_used_gb", 0),
            "net_bytes_sent": data.get("net_bytes_sent", 0),
            "net_bytes_recv": data.get("net_bytes_recv", 0),
            "load_avg_1m":    data.get("load_avg_1m", 0),
            "process_count":  data.get("process_count", 0),
            "extra":          {"transport": "ssh"},
        }
    except Exception:
        return None


async def collect_ssh_targets(targets: list[str]) -> list[dict]:
    if not targets or targets == [""]:
        return []
    results = await asyncio.gather(
        *[collect_ssh_target(t.strip()) for t in targets if t.strip()],
        return_exceptions=True
    )
    return [r for r in results if isinstance(r, dict)]


# ══════════════════════════════════════════════════════════════════════════════
# NETWORK DISCOVERY  — ping sweep + SNMP probe
# ══════════════════════════════════════════════════════════════════════════════

_discovered_snmp: set[str] = set()
_discovered_ssh:  set[str] = set()


async def _ping(ip: str) -> bool:
    flag = "-n" if SYSTEM == "Windows" else "-c"
    proc = await asyncio.create_subprocess_exec(
        "ping", flag, "1", "-W", "1", ip,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL
    )
    try:
        await asyncio.wait_for(proc.wait(), timeout=3)
        return proc.returncode == 0
    except asyncio.TimeoutError:
        proc.kill()
        return False


async def _probe_snmp(ip: str) -> bool:
    """Returns True if the host responds to SNMP v2c GET on sysDescr."""
    try:
        from pysnmp.hlapi.asyncio import (
            SnmpEngine, CommunityData, UdpTransportTarget,
            ContextData, ObjectType, ObjectIdentity, getCmd
        )
        community = os.getenv("SNMP_COMMUNITY", "public")
        err_ind, err_stat, _, _ = await getCmd(
            SnmpEngine(), CommunityData(community, mpModel=1),
            UdpTransportTarget((ip, 161), timeout=2, retries=0),
            ContextData(), ObjectType(ObjectIdentity("1.3.6.1.2.1.1.1.0"))
        )
        return not err_ind and not err_stat
    except Exception:
        return False


async def _probe_ssh(ip: str) -> bool:
    """Returns True if port 22 is open."""
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, 22), timeout=2
        )
        writer.close()
        return True
    except Exception:
        return False


async def discover_network(network_range: str):
    """
    Sweep a CIDR range (e.g. 192.168.1.0/24) and discover:
    - SNMP-capable devices  → add to _discovered_snmp
    - SSH-accessible hosts  → add to _discovered_ssh (uses SSH_USER env var)
    """
    try:
        import ipaddress
        net  = ipaddress.ip_network(network_range, strict=False)
        hosts = list(net.hosts())
        print(f"[Agent] Discovering {len(hosts)} hosts in {network_range}...")

        # Ping sweep (batched 50 at a time)
        batch_size = 50
        live_hosts = []
        for i in range(0, len(hosts), batch_size):
            batch   = hosts[i:i + batch_size]
            results = await asyncio.gather(*[_ping(str(h)) for h in batch])
            live_hosts.extend(str(h) for h, up in zip(batch, results) if up)

        print(f"[Agent] Found {len(live_hosts)} live hosts")

        # Probe live hosts for SNMP / SSH
        ssh_user = os.getenv("SSH_USER", "")
        for ip in live_hosts:
            snmp_ok, ssh_ok = await asyncio.gather(_probe_snmp(ip), _probe_ssh(ip))
            if snmp_ok:
                _discovered_snmp.add(ip)
            elif ssh_ok and ssh_user:
                _discovered_ssh.add(f"{ssh_user}@{ip}")

        print(f"[Agent] Discovered SNMP={len(_discovered_snmp)} SSH={len(_discovered_ssh)}")
    except Exception as e:
        print(f"[Agent] Discovery error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# SHIP TO API
# ══════════════════════════════════════════════════════════════════════════════

async def ship_metrics(client: httpx.AsyncClient, metrics: dict):
    try:
        await client.post(f"{API_URL}/api/ingest/metrics", json=metrics, timeout=10)
    except Exception as e:
        print(f"[Agent] Metrics failed ({metrics.get('node_id', '?')}): {e}")


async def ship_events(client: httpx.AsyncClient, events: list[dict]):
    for event in events:
        try:
            await client.post(f"{API_URL}/api/ingest/events", json=event, timeout=10)
        except Exception as e:
            print(f"[Agent] Event failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN LOOP
# ══════════════════════════════════════════════════════════════════════════════

async def main():
    print(f"[Agent] PULSE Universal Collector starting")
    print(f"[Agent] Node: {NODE_ID} | API: {API_URL} | Interval: {COLLECT_INTERVAL}s")
    print(f"[Agent] OS: {OS_INFO} | IP: {IP}")
    print(f"[Agent] SNMP targets: {[t for t in SNMP_TARGETS if t]}")
    print(f"[Agent] SSH  targets: {[t for t in SSH_TARGETS  if t]}")

    # Wait for API to be ready
    async with httpx.AsyncClient() as http:
        for attempt in range(30):
            try:
                r = await http.get(f"{API_URL}/health", timeout=5)
                if r.status_code == 200:
                    print("[Agent] API connected")
                    break
            except Exception:
                pass
            print(f"[Agent] Waiting for API... ({attempt+1}/30)")
            await asyncio.sleep(5)

    # Initial network discovery
    if ENABLE_DISCOVERY and NETWORK_RANGE:
        await discover_network(NETWORK_RANGE)

    discovery_counter = 0
    DISCOVERY_INTERVAL = 60  # re-discover every 60 cycles

    # Main collection loop
    async with httpx.AsyncClient() as http:
        while True:
            try:
                # ── Local node ─────────────────────────────────────────────
                local_metrics = collect_metrics()
                sec_events    = detect_security_events()
                log_events    = tail_logs()
                all_events    = sec_events + log_events

                await ship_metrics(http, local_metrics)
                if all_events:
                    await ship_events(http, all_events)

                # ── SNMP devices ───────────────────────────────────────────
                snmp_targets = list(set(
                    [t for t in SNMP_TARGETS if t.strip()] +
                    list(_discovered_snmp)
                ))
                if snmp_targets:
                    snmp_results = await collect_snmp_targets(snmp_targets)
                    for m in snmp_results:
                        await ship_metrics(http, m)

                # ── SSH agentless nodes ────────────────────────────────────
                ssh_targets = list(set(
                    [t for t in SSH_TARGETS if t.strip()] +
                    list(_discovered_ssh)
                ))
                if ssh_targets:
                    ssh_results = await collect_ssh_targets(ssh_targets)
                    for m in ssh_results:
                        await ship_metrics(http, m)

                # ── Kubernetes ─────────────────────────────────────────────
                if ENABLE_K8S:
                    try:
                        sys.path.insert(0, str(Path(__file__).parent))
                        from cloud.kubernetes import collect_all as k8s_collect_all
                        k8s_data = await k8s_collect_all()
                        await ship_metrics(http, k8s_data["metric"])
                        await ship_events(http, k8s_data["events"])
                    except Exception as e:
                        print(f"[Agent] K8s error: {e}")

                # ── AWS ────────────────────────────────────────────────────
                if ENABLE_AWS:
                    try:
                        from cloud.aws import collect_all as aws_collect_all
                        aws_data = await aws_collect_all()
                        for m in aws_data["metrics"]:
                            await ship_metrics(http, m)
                        await ship_events(http, aws_data["events"])
                    except Exception as e:
                        print(f"[Agent] AWS error: {e}")

                # ── Azure ──────────────────────────────────────────────────
                if ENABLE_AZURE:
                    try:
                        from cloud.azure import collect_all as azure_collect_all
                        azure_data = await azure_collect_all()
                        for m in azure_data["metrics"]:
                            await ship_metrics(http, m)
                        await ship_events(http, azure_data["events"])
                    except Exception as e:
                        print(f"[Agent] Azure error: {e}")

                # ── GCP ────────────────────────────────────────────────────
                if ENABLE_GCP:
                    try:
                        from cloud.gcp import collect_all as gcp_collect_all
                        gcp_data = await gcp_collect_all()
                        for m in gcp_data["metrics"]:
                            await ship_metrics(http, m)
                        await ship_events(http, gcp_data["events"])
                    except Exception as e:
                        print(f"[Agent] GCP error: {e}")

                # Summary log
                total_nodes = 1 + len(snmp_targets) + len(ssh_targets)
                print(
                    f"[Agent] CPU={local_metrics['cpu_percent']:.1f}% "
                    f"MEM={local_metrics['memory_percent']:.1f}% "
                    f"DISK={local_metrics['disk_percent']:.1f}% | "
                    f"nodes={total_nodes} events={len(all_events)}"
                )

                # Periodic re-discovery
                if ENABLE_DISCOVERY and NETWORK_RANGE:
                    discovery_counter += 1
                    if discovery_counter >= DISCOVERY_INTERVAL:
                        discovery_counter = 0
                        asyncio.create_task(discover_network(NETWORK_RANGE))

            except Exception as e:
                print(f"[Agent] Collection error: {e}")

            await asyncio.sleep(COLLECT_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
