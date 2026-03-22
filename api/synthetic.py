"""
PULSE Synthetic Monitoring — HTTP health checks, SSL cert expiry, response time tracking.

Runs as a background loop in the API. Probes configured URLs and generates:
- Metrics (response_time_ms, status_code) per target
- Alerts when targets are down, slow, or SSL certs expiring
"""
import asyncio
import os
import ssl
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
import yaml


_config_path = Path(__file__).parent / "config" / "synthetic.yaml"
_targets: list[dict] = []
_target_state: dict[str, dict] = {}  # track consecutive failures


def load_targets() -> list[dict]:
    """Load synthetic monitoring targets from config."""
    global _targets
    for candidate in [_config_path, Path(__file__).parent.parent / "config" / "synthetic.yaml"]:
        if candidate.exists():
            try:
                data = yaml.safe_load(candidate.read_text())
                _targets = (data or {}).get("targets") or []
                return _targets
            except Exception as e:
                print(f"[Synthetic] Config error: {e}")
    _targets = []
    return _targets


def check_ssl_expiry(hostname: str, port: int = 443) -> Optional[dict]:
    """Check SSL certificate expiry date for a hostname."""
    try:
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(socket.socket(), server_hostname=hostname) as sock:
            sock.settimeout(5)
            sock.connect((hostname, port))
            cert = sock.getpeercertificate()
            if cert:
                not_after = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z")
                days_left = (not_after - datetime.utcnow()).days
                return {
                    "issuer": dict(x[0] for x in cert.get("issuer", [])),
                    "subject": dict(x[0] for x in cert.get("subject", [])),
                    "not_after": not_after.isoformat(),
                    "days_left": days_left,
                }
    except Exception as e:
        return {"error": str(e), "days_left": -1}
    return None


async def probe_target(client: httpx.AsyncClient, target: dict) -> dict:
    """Probe a single target and return results."""
    target_id = target.get("id", target.get("url", "unknown"))
    url = target.get("url", "")
    method = target.get("method", "GET").upper()
    timeout = target.get("timeout_seconds", 10)
    expected_status = target.get("expected_status", 200)
    expected_body = target.get("expected_body")

    result = {
        "target_id": target_id,
        "url": url,
        "ts": datetime.now(timezone.utc).isoformat(),
        "status": "up",
        "status_code": 0,
        "response_time_ms": 0,
        "ssl": None,
        "events": [],
    }

    # HTTP probe
    start = asyncio.get_event_loop().time()
    try:
        if method == "POST":
            resp = await client.post(url, timeout=timeout, content=target.get("body", ""))
        else:
            resp = await client.get(url, timeout=timeout)

        elapsed_ms = round((asyncio.get_event_loop().time() - start) * 1000, 1)
        result["status_code"] = resp.status_code
        result["response_time_ms"] = elapsed_ms

        # Status code check
        if resp.status_code != expected_status:
            result["status"] = "down"
            result["events"].append({
                "node_id": f"synthetic:{target_id}",
                "type": "synthetic_status_mismatch",
                "severity": target.get("severity", "high"),
                "source": f"synthetic:{target_id}",
                "message": f"{target_id} returned {resp.status_code} (expected {expected_status})",
                "data": {"url": url, "expected": expected_status, "got": resp.status_code,
                         "response_time_ms": elapsed_ms},
            })

        # Body content check
        if expected_body and expected_body not in resp.text:
            result["status"] = "degraded"
            result["events"].append({
                "node_id": f"synthetic:{target_id}",
                "type": "synthetic_body_mismatch",
                "severity": "medium",
                "source": f"synthetic:{target_id}",
                "message": f"{target_id} response missing expected content '{expected_body}'",
                "data": {"url": url, "expected_body": expected_body},
            })

        # Slow response check (>5s default)
        slow_threshold = target.get("slow_threshold_ms", 5000)
        if elapsed_ms > slow_threshold:
            result["events"].append({
                "node_id": f"synthetic:{target_id}",
                "type": "synthetic_slow_response",
                "severity": "medium",
                "source": f"synthetic:{target_id}",
                "message": f"{target_id} slow response: {elapsed_ms}ms (threshold: {slow_threshold}ms)",
                "data": {"url": url, "response_time_ms": elapsed_ms, "threshold": slow_threshold},
            })

    except httpx.TimeoutException:
        elapsed_ms = round((asyncio.get_event_loop().time() - start) * 1000, 1)
        result["status"] = "down"
        result["response_time_ms"] = elapsed_ms
        result["events"].append({
            "node_id": f"synthetic:{target_id}",
            "type": "synthetic_timeout",
            "severity": target.get("severity", "critical"),
            "source": f"synthetic:{target_id}",
            "message": f"{target_id} timed out after {timeout}s",
            "data": {"url": url, "timeout_seconds": timeout},
        })
    except Exception as e:
        result["status"] = "down"
        result["events"].append({
            "node_id": f"synthetic:{target_id}",
            "type": "synthetic_connection_error",
            "severity": target.get("severity", "critical"),
            "source": f"synthetic:{target_id}",
            "message": f"{target_id} connection error: {str(e)[:200]}",
            "data": {"url": url, "error": str(e)[:500]},
        })

    # SSL check
    if target.get("check_ssl") and url.startswith("https://"):
        from urllib.parse import urlparse
        hostname = urlparse(url).hostname
        if hostname:
            ssl_info = check_ssl_expiry(hostname)
            result["ssl"] = ssl_info
            if ssl_info:
                warn_days = target.get("ssl_warn_days", 30)
                days_left = ssl_info.get("days_left", -1)
                if days_left >= 0 and days_left <= warn_days:
                    result["events"].append({
                        "node_id": f"synthetic:{target_id}",
                        "type": "ssl_cert_expiring",
                        "severity": "critical" if days_left <= 7 else "high",
                        "source": f"synthetic:{target_id}",
                        "message": f"{target_id} SSL cert expires in {days_left} days",
                        "data": {"url": url, "hostname": hostname, "days_left": days_left,
                                 "expires": ssl_info.get("not_after")},
                    })
                elif days_left < 0:
                    result["events"].append({
                        "node_id": f"synthetic:{target_id}",
                        "type": "ssl_cert_error",
                        "severity": "critical",
                        "source": f"synthetic:{target_id}",
                        "message": f"{target_id} SSL cert error: {ssl_info.get('error', 'expired')}",
                        "data": {"url": url, "hostname": hostname, "ssl_error": ssl_info.get("error")},
                    })

    # Track consecutive failures
    state = _target_state.setdefault(target_id, {"consecutive_failures": 0})
    if result["status"] == "down":
        state["consecutive_failures"] += 1
    else:
        state["consecutive_failures"] = 0

    return result


# In-memory results for API queries
_latest_results: dict[str, dict] = {}


async def synthetic_loop():
    """Background loop — probes all targets at their configured intervals."""
    load_targets()
    if not _targets:
        print("[Synthetic] No targets configured — skipping")
        return

    print(f"[Synthetic] Monitoring {len(_targets)} targets")

    # Track per-target next-run time
    next_run: dict[str, float] = {}

    async with httpx.AsyncClient(follow_redirects=True, verify=False) as client:
        while True:
            now = asyncio.get_event_loop().time()
            tasks = []

            for target in _targets:
                tid = target.get("id", target.get("url", ""))
                interval = target.get("interval_seconds", 60)
                if now >= next_run.get(tid, 0):
                    tasks.append((target, probe_target(client, target)))
                    next_run[tid] = now + interval

            if tasks:
                results = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)
                for (target, _), result in zip(tasks, results):
                    if isinstance(result, dict):
                        _latest_results[target.get("id", "")] = result
                        # Ship events to API (self)
                        if result.get("events"):
                            try:
                                for ev in result["events"]:
                                    await client.post(
                                        f"http://localhost:{os.getenv('PORT', '8000')}/api/ingest/events",
                                        json=ev, timeout=5
                                    )
                            except Exception:
                                pass

            await asyncio.sleep(5)  # Check every 5s which targets need probing


def get_synthetic_results() -> list[dict]:
    """Return latest probe results for all targets."""
    return list(_latest_results.values())


def get_synthetic_targets() -> list[dict]:
    """Return configured targets."""
    if not _targets:
        load_targets()
    return _targets
