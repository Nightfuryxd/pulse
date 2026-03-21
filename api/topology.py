"""
PULSE Topology Engine

Builds and maintains a real-time service dependency graph from:
- Network connections reported by agents
- Service spans reported by app SDKs
- SNMP interface data from network equipment

The graph answers:
  "If this service fails, what else breaks?"
  "What does this service depend on?"
  "Show me the full call chain for this incident."
"""
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional

# Well-known port → service name
PORT_TO_SERVICE = {
    21:    "ftp",         22:    "ssh",
    25:    "smtp",        53:    "dns",
    80:    "http",        443:   "https",
    1433:  "mssql",       1521:  "oracle",
    3306:  "mysql",       3389:  "rdp",
    5432:  "postgres",    5672:  "rabbitmq",
    6379:  "redis",       6380:  "redis",
    8080:  "http-alt",    8443:  "https-alt",
    9042:  "cassandra",   9092:  "kafka",
    9200:  "elasticsearch", 9300: "elasticsearch",
    11211: "memcached",   15672: "rabbitmq-mgmt",
    27017: "mongodb",     27018: "mongodb",
    2181:  "zookeeper",   2379:  "etcd",
    4222:  "nats",        6443:  "kubernetes",
}

# Service criticality tiers
SERVICE_TIER = {
    "postgres": "data",   "mysql": "data",      "mongodb": "data",
    "redis": "cache",     "memcached": "cache",  "kafka": "queue",
    "rabbitmq": "queue",  "elasticsearch": "search",
    "http": "app",        "https": "app",
    "dns": "infra",       "ssh": "infra",
}

# In-memory graph: src_node → {dst_node → {service: conn_info}}
_graph: dict[str, dict] = defaultdict(lambda: defaultdict(dict))
# IP → node_id resolution cache
_ip_to_node: dict[str, str] = {}


def resolve_service(port: int) -> str:
    return PORT_TO_SERVICE.get(port, f"port-{port}")


def update_ip_map(node_id: str, ip: str):
    """Register an IP → node_id mapping for topology resolution."""
    if ip and ip not in ("0.0.0.0", "127.0.0.1", "::1"):
        _ip_to_node[ip] = node_id


def record_connection(src_node: str, src_port: int,
                      dst_ip: str, dst_port: int,
                      bytes_sent: int = 0) -> dict:
    """
    Record an observed TCP connection. Returns edge dict for DB persistence.
    """
    dst_node    = _ip_to_node.get(dst_ip, dst_ip)
    src_service = resolve_service(src_port) if src_port < 1024 else "client"
    dst_service = resolve_service(dst_port)

    edge = {
        "src_node":    src_node,
        "src_service": src_service,
        "src_port":    src_port,
        "dst_ip":      dst_ip,
        "dst_node":    dst_node,
        "dst_service": dst_service,
        "dst_port":    dst_port,
        "bytes_sent":  bytes_sent,
        "last_seen":   datetime.utcnow().isoformat(),
    }

    _graph[src_node][dst_node][dst_service] = edge
    return edge


def get_dependencies(node_id: str) -> list[dict]:
    """What does this node depend on? (outbound connections)"""
    deps = []
    for dst_node, services in _graph.get(node_id, {}).items():
        for service, edge in services.items():
            deps.append({**edge, "direction": "outbound"})
    return deps


def get_dependents(node_id: str) -> list[dict]:
    """What depends on this node? (inbound connections from others)"""
    deps = []
    for src_node, targets in _graph.items():
        if src_node == node_id:
            continue
        for dst_node, services in targets.items():
            if dst_node == node_id:
                for service, edge in services.items():
                    deps.append({**edge, "direction": "inbound"})
    return deps


def get_blast_radius(node_id: str, depth: int = 3) -> dict:
    """
    Given a node, find everything that would be impacted if it went down.
    Returns affected nodes per hop depth.
    """
    visited  = set()
    affected = defaultdict(list)   # depth → [node_ids]
    queue    = [(node_id, 0)]

    while queue:
        current, d = queue.pop(0)
        if current in visited or d > depth:
            continue
        visited.add(current)
        dependents = get_dependents(current)
        for dep in dependents:
            dependent_node = dep["src_node"]
            if dependent_node not in visited:
                affected[d + 1].append(dependent_node)
                queue.append((dependent_node, d + 1))

    return {
        "origin":          node_id,
        "total_affected":  len(visited) - 1,
        "by_depth":        {str(k): list(set(v)) for k, v in affected.items()},
        "critical_services": _find_critical_services(node_id),
    }


def _find_critical_services(node_id: str) -> list[str]:
    """What critical services does this node host?"""
    critical = []
    for dst_node, services in _graph.get(node_id, {}).items():
        for service in services:
            if SERVICE_TIER.get(service) in ("data", "queue", "cache"):
                critical.append(service)
    # Also check what's connecting to this node
    for src_node, targets in _graph.items():
        for dst_node, services in targets.items():
            if dst_node == node_id:
                for service in services:
                    if SERVICE_TIER.get(service) in ("data", "queue", "cache"):
                        if service not in critical:
                            critical.append(service)
    return critical


def get_full_graph() -> dict:
    """Return the full topology as a graph for dashboard rendering."""
    nodes = set()
    edges = []

    for src_node, targets in _graph.items():
        nodes.add(src_node)
        for dst_node, services in targets.items():
            nodes.add(dst_node)
            for service, edge in services.items():
                edges.append({
                    "source":      src_node,
                    "target":      dst_node,
                    "service":     service,
                    "port":        edge.get("dst_port", 0),
                    "bytes_sent":  edge.get("bytes_sent", 0),
                    "last_seen":   edge.get("last_seen", ""),
                })

    return {
        "nodes": [{"id": n, "type": "node"} for n in nodes],
        "edges": edges,
        "updated": datetime.utcnow().isoformat(),
    }


def find_common_dependency(node_ids: list[str]) -> Optional[str]:
    """
    Given a list of affected nodes, find the common upstream dependency.
    Used by the correlation engine to identify root cause node.
    """
    if not node_ids:
        return None

    # Build dependency sets for each node
    dep_sets = []
    for node_id in node_ids:
        deps = {e["dst_node"] for e in get_dependencies(node_id)}
        if deps:
            dep_sets.append(deps)

    if not dep_sets:
        return None

    # Find intersection
    common = dep_sets[0]
    for s in dep_sets[1:]:
        common &= s

    if not common:
        return None

    # Prefer the one that hosts a critical service
    for candidate in common:
        if _find_critical_services(candidate):
            return candidate
    return next(iter(common))
