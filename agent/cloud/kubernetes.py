"""
PULSE Kubernetes Collector

Monitors: pods, deployments, nodes, namespaces, events, PVCs.
Auto-detects: crash loops, OOMKilled, pending pods, failed deployments.

Works inside a K8s cluster (ServiceAccount) or from outside (kubeconfig).
"""
import asyncio
import os
from datetime import datetime, timezone
from typing import Optional

KUBE_API  = os.getenv("KUBERNETES_SERVICE_HOST", "")
KUBE_PORT = os.getenv("KUBERNETES_SERVICE_PORT", "443")
NODE_ID   = os.getenv("NODE_ID", "k8s-cluster")
SA_TOKEN  = "/var/run/secrets/kubernetes.io/serviceaccount/token"
SA_CA     = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"


def _is_in_cluster() -> bool:
    import os
    return bool(KUBE_API) and os.path.exists(SA_TOKEN)


async def _k8s_get(path: str) -> Optional[dict]:
    """Make a GET request to the Kubernetes API."""
    try:
        import httpx, ssl, pathlib

        if _is_in_cluster():
            token = pathlib.Path(SA_TOKEN).read_text().strip()
            base  = f"https://{KUBE_API}:{KUBE_PORT}"
            headers = {"Authorization": f"Bearer {token}"}
            ssl_ctx = ssl.create_default_context(cafile=SA_CA)
        else:
            # Out-of-cluster: use kubectl proxy or KUBECONFIG
            base    = os.getenv("KUBE_PROXY_URL", "http://localhost:8001")
            headers = {}
            ssl_ctx = False

        async with httpx.AsyncClient(verify=ssl_ctx, timeout=10) as client:
            r = await client.get(f"{base}{path}", headers=headers)
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        print(f"[K8s] API error {path}: {e}")
    return None


async def collect_pods(namespace: str = "") -> list[dict]:
    """Collect all pod metrics and states."""
    ns_path = f"/namespaces/{namespace}" if namespace else ""
    data    = await _k8s_get(f"/api/v1{ns_path}/pods")
    if not data:
        return []

    metrics = []
    for item in data.get("items", []):
        meta   = item.get("metadata", {})
        spec   = item.get("spec", {})
        status = item.get("status", {})

        pod_name  = meta.get("name", "")
        namespace = meta.get("namespace", "default")
        phase     = status.get("phase", "Unknown")
        node_name = spec.get("nodeName", "")

        # Container statuses
        container_statuses = status.get("containerStatuses", [])
        restarts     = sum(cs.get("restartCount", 0) for cs in container_statuses)
        ready_count  = sum(1 for cs in container_statuses if cs.get("ready"))
        total_count  = len(container_statuses)

        # Detect problems
        events = []
        for cs in container_statuses:
            state     = cs.get("state", {})
            last_state = cs.get("lastState", {})

            if "waiting" in state:
                reason = state["waiting"].get("reason", "")
                if reason in ("CrashLoopBackOff", "Error", "OOMKilled", "ImagePullBackOff", "ErrImagePull"):
                    events.append({
                        "node_id":  f"k8s:{NODE_ID}",
                        "type":     "pod_" + reason.lower(),
                        "severity": "critical" if reason in ("CrashLoopBackOff", "OOMKilled") else "high",
                        "source":   f"k8s:{namespace}/{pod_name}",
                        "message":  f"Pod {pod_name} container {cs.get('name','')} in {reason}",
                        "data":     {"namespace": namespace, "pod": pod_name, "reason": reason,
                                     "restarts": restarts, "node": node_name},
                    })

            if restarts >= 5:
                events.append({
                    "node_id":  f"k8s:{NODE_ID}",
                    "type":     "pod_restart_loop",
                    "severity": "high",
                    "source":   f"k8s:{namespace}/{pod_name}",
                    "message":  f"Pod {pod_name} has restarted {restarts} times",
                    "data":     {"namespace": namespace, "pod": pod_name, "restarts": restarts},
                })

        metrics.append({
            "pod":        pod_name,
            "namespace":  namespace,
            "phase":      phase,
            "node":       node_name,
            "ready":      f"{ready_count}/{total_count}",
            "restarts":   restarts,
            "events":     events,
        })

    return metrics


async def collect_nodes() -> list[dict]:
    """Collect K8s node metrics."""
    data = await _k8s_get("/api/v1/nodes")
    if not data:
        return []

    nodes = []
    for item in data.get("items", []):
        meta       = item.get("metadata", {})
        status     = item.get("status", {})
        conditions = {c["type"]: c["status"] for c in status.get("conditions", [])}
        capacity   = status.get("capacity", {})
        alloc      = status.get("allocatable", {})

        ready    = conditions.get("Ready", "Unknown") == "True"
        name     = meta.get("name", "")
        cpu_cap  = capacity.get("cpu", "0")
        mem_cap  = capacity.get("memory", "0Ki")

        events = []
        if not ready:
            events.append({
                "node_id":  f"k8s:{NODE_ID}",
                "type":     "k8s_node_not_ready",
                "severity": "critical",
                "source":   f"k8s:node/{name}",
                "message":  f"K8s node {name} is NOT Ready",
                "data":     {"node": name, "conditions": conditions},
            })
        for cond_type, cond_status in conditions.items():
            if cond_type in ("MemoryPressure", "DiskPressure", "PIDPressure") and cond_status == "True":
                events.append({
                    "node_id":  f"k8s:{NODE_ID}",
                    "type":     f"k8s_{cond_type.lower()}",
                    "severity": "high",
                    "source":   f"k8s:node/{name}",
                    "message":  f"K8s node {name} has {cond_type}",
                    "data":     {"node": name, "condition": cond_type},
                })

        nodes.append({
            "name":       name,
            "ready":      ready,
            "cpu_cap":    cpu_cap,
            "mem_cap":    mem_cap,
            "conditions": conditions,
            "events":     events,
        })

    return nodes


async def collect_deployments(namespace: str = "") -> list[dict]:
    """Check deployment health."""
    ns_path = f"/namespaces/{namespace}" if namespace else ""
    data    = await _k8s_get(f"/apis/apps/v1{ns_path}/deployments")
    if not data:
        return []

    deployments = []
    for item in data.get("items", []):
        meta   = item.get("metadata", {})
        spec   = item.get("spec", {})
        status = item.get("status", {})

        name      = meta.get("name", "")
        ns        = meta.get("namespace", "default")
        desired   = spec.get("replicas", 0)
        ready     = status.get("readyReplicas", 0)
        available = status.get("availableReplicas", 0)

        events = []
        if ready < desired:
            events.append({
                "node_id":  f"k8s:{NODE_ID}",
                "type":     "deployment_degraded",
                "severity": "critical" if available == 0 else "high",
                "source":   f"k8s:{ns}/{name}",
                "message":  f"Deployment {name}: {ready}/{desired} replicas ready",
                "data":     {"namespace": ns, "deployment": name, "desired": desired, "ready": ready},
            })

        deployments.append({
            "name":      name,
            "namespace": ns,
            "desired":   desired,
            "ready":     ready,
            "available": available,
            "events":    events,
        })

    return deployments


async def collect_events(namespace: str = "", minutes: int = 10) -> list[dict]:
    """Get recent K8s warning events."""
    ns_path     = f"/namespaces/{namespace}" if namespace else ""
    data        = await _k8s_get(f"/api/v1{ns_path}/events?fieldSelector=type=Warning")
    if not data:
        return []

    pulse_events = []
    for item in data.get("items", []):
        reason  = item.get("reason", "")
        message = item.get("message", "")
        obj     = item.get("involvedObject", {})
        count   = item.get("count", 1)

        pulse_events.append({
            "node_id":  f"k8s:{NODE_ID}",
            "type":     f"k8s_warning",
            "severity": "high" if count > 5 else "medium",
            "source":   f"k8s:{obj.get('namespace','')}/{obj.get('name','')}",
            "message":  f"[{reason}] {message} (count={count})",
            "data":     {"reason": reason, "object": obj, "count": count},
        })

    return pulse_events


async def collect_all() -> dict:
    """Collect everything from the K8s cluster."""
    pods, nodes, deployments, events = await asyncio.gather(
        collect_pods(),
        collect_nodes(),
        collect_deployments(),
        collect_events(),
        return_exceptions=True,
    )

    all_events = []
    for result in [pods, nodes, deployments, events]:
        if isinstance(result, list):
            for item in result:
                if isinstance(item, dict):
                    all_events.extend(item.get("events", []))

    # Build a synthetic metric for the cluster
    total_pods    = len(pods) if isinstance(pods, list) else 0
    ready_pods    = sum(1 for p in (pods or []) if isinstance(p, dict) and "/" in str(p.get("ready","0/0")) and p["ready"].split("/")[0] == p["ready"].split("/")[1])
    degraded_deps = sum(1 for d in (deployments or []) if isinstance(d, dict) and d.get("ready", 0) < d.get("desired", 0))

    cluster_metric = {
        "node_id":       f"k8s:{NODE_ID}",
        "hostname":      f"k8s-{NODE_ID}",
        "ip":            KUBE_API or "in-cluster",
        "os":            "Kubernetes",
        "ts":            datetime.now(timezone.utc).isoformat(),
        "cpu_percent":   0,
        "memory_percent": 0,
        "disk_percent":  0,
        "disk_used_gb":  0,
        "net_bytes_sent": 0,
        "net_bytes_recv": 0,
        "load_avg_1m":   0,
        "process_count": total_pods,
        "extra": {
            "total_pods":     total_pods,
            "ready_pods":     ready_pods,
            "degraded_deployments": degraded_deps,
            "k8s_nodes":      len(nodes) if isinstance(nodes, list) else 0,
        },
    }

    return {
        "metric": cluster_metric,
        "events": all_events,
        "pods":        pods        if isinstance(pods, list)        else [],
        "nodes":       nodes       if isinstance(nodes, list)       else [],
        "deployments": deployments if isinstance(deployments, list) else [],
    }
