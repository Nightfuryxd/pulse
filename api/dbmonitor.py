"""
PULSE Database Monitor — query-level visibility for PostgreSQL, MySQL, Redis.

Collects: active connections, slow queries, table sizes, replication lag,
cache hit ratio, memory usage, keyspace stats.
"""
import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml


_config_path = Path(__file__).parent.parent / "config" / "databases.yaml"
_targets: list[dict] = []
_latest_results: dict[str, dict] = {}


def load_targets() -> list[dict]:
    global _targets
    for candidate in [Path(__file__).parent / "config" / "databases.yaml", _config_path]:
        if candidate.exists():
            try:
                data = yaml.safe_load(candidate.read_text())
                _targets = (data or {}).get("targets") or []
                return _targets
            except Exception as e:
                print(f"[DBMonitor] Config error: {e}")
    _targets = []
    return _targets


async def collect_postgres(target: dict) -> dict:
    """Collect metrics from PostgreSQL."""
    result = {
        "target_id": target["id"],
        "type": "postgres",
        "ts": datetime.now(timezone.utc).isoformat(),
        "metrics": {},
        "slow_queries": [],
        "events": [],
    }

    try:
        import asyncpg
        dsn = target.get("dsn", "")
        conn = await asyncpg.connect(dsn, timeout=10)

        collect = target.get("collect", [])

        # Active connections
        if "active_connections" in collect:
            rows = await conn.fetch(
                "SELECT state, count(*) as cnt FROM pg_stat_activity GROUP BY state"
            )
            conns = {row["state"] or "null": row["cnt"] for row in rows}
            result["metrics"]["connections"] = conns
            total = sum(conns.values())
            result["metrics"]["total_connections"] = total

            max_conn = await conn.fetchval("SHOW max_connections")
            result["metrics"]["max_connections"] = int(max_conn)
            usage_pct = round(total / int(max_conn) * 100, 1)
            result["metrics"]["connection_usage_pct"] = usage_pct

            if usage_pct > 80:
                result["events"].append({
                    "node_id": f"db:{target['id']}",
                    "type": "db_connection_high",
                    "severity": "high" if usage_pct > 90 else "medium",
                    "source": f"db:{target['id']}",
                    "message": f"PostgreSQL {target['id']} connection usage at {usage_pct}% ({total}/{max_conn})",
                    "data": {"connections": conns, "usage_pct": usage_pct},
                })

        # Cache hit ratio
        if "cache_hit_ratio" in collect:
            row = await conn.fetchrow("""
                SELECT
                    sum(heap_blks_hit) / NULLIF(sum(heap_blks_hit) + sum(heap_blks_read), 0) as ratio
                FROM pg_statio_user_tables
            """)
            if row and row["ratio"] is not None:
                ratio = round(float(row["ratio"]) * 100, 2)
                result["metrics"]["cache_hit_ratio"] = ratio
                if ratio < 90:
                    result["events"].append({
                        "node_id": f"db:{target['id']}",
                        "type": "db_cache_low",
                        "severity": "medium",
                        "source": f"db:{target['id']}",
                        "message": f"PostgreSQL {target['id']} cache hit ratio low: {ratio}%",
                        "data": {"cache_hit_ratio": ratio},
                    })

        # Slow queries
        if "slow_queries" in collect:
            threshold = target.get("slow_query_ms", 1000)
            rows = await conn.fetch("""
                SELECT pid, now() - pg_stat_activity.query_start AS duration,
                       query, state
                FROM pg_stat_activity
                WHERE (now() - pg_stat_activity.query_start) > interval '$1 milliseconds'
                  AND state != 'idle'
                ORDER BY duration DESC
                LIMIT 10
            """.replace("$1", str(threshold)))
            for row in rows:
                result["slow_queries"].append({
                    "pid": row["pid"],
                    "duration": str(row["duration"]),
                    "query": (row["query"] or "")[:500],
                    "state": row["state"],
                })
            if len(rows) > 0:
                result["events"].append({
                    "node_id": f"db:{target['id']}",
                    "type": "db_slow_queries",
                    "severity": target.get("severity", "high"),
                    "source": f"db:{target['id']}",
                    "message": f"PostgreSQL {target['id']} has {len(rows)} slow queries (>{threshold}ms)",
                    "data": {"count": len(rows), "threshold_ms": threshold},
                })

        # Table sizes
        if "table_sizes" in collect:
            rows = await conn.fetch("""
                SELECT schemaname || '.' || tablename as table_name,
                       pg_total_relation_size(schemaname || '.' || tablename) as size_bytes
                FROM pg_tables
                WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
                ORDER BY size_bytes DESC
                LIMIT 20
            """)
            result["metrics"]["table_sizes"] = {
                row["table_name"]: row["size_bytes"] for row in rows
            }

        # Dead tuples (needs vacuuming)
        if "dead_tuples" in collect:
            rows = await conn.fetch("""
                SELECT schemaname || '.' || relname as table_name,
                       n_dead_tup, n_live_tup,
                       CASE WHEN n_live_tup > 0
                            THEN round(n_dead_tup::numeric / n_live_tup * 100, 2)
                            ELSE 0 END as dead_ratio
                FROM pg_stat_user_tables
                WHERE n_dead_tup > 1000
                ORDER BY n_dead_tup DESC
                LIMIT 10
            """)
            result["metrics"]["dead_tuples"] = [
                {"table": row["table_name"], "dead": row["n_dead_tup"],
                 "live": row["n_live_tup"], "dead_ratio": float(row["dead_ratio"])}
                for row in rows
            ]

        # Replication lag
        if "replication_lag" in collect:
            rows = await conn.fetch("""
                SELECT client_addr, state,
                       pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) as lag_bytes
                FROM pg_stat_replication
            """)
            result["metrics"]["replication"] = [
                {"client": str(row["client_addr"]), "state": row["state"],
                 "lag_bytes": row["lag_bytes"]}
                for row in rows
            ]

        await conn.close()

    except ImportError:
        result["metrics"]["error"] = "asyncpg not installed"
    except Exception as e:
        result["metrics"]["error"] = str(e)[:500]
        result["events"].append({
            "node_id": f"db:{target['id']}",
            "type": "db_connection_error",
            "severity": "critical",
            "source": f"db:{target['id']}",
            "message": f"Cannot connect to PostgreSQL {target['id']}: {str(e)[:200]}",
            "data": {"error": str(e)[:500]},
        })

    return result


async def collect_redis(target: dict) -> dict:
    """Collect metrics from Redis."""
    result = {
        "target_id": target["id"],
        "type": "redis",
        "ts": datetime.now(timezone.utc).isoformat(),
        "metrics": {},
        "events": [],
    }

    try:
        import redis.asyncio as aioredis
        url = target.get("url", "redis://localhost:6379")
        r = aioredis.from_url(url, decode_responses=True, socket_timeout=5)

        info = await r.info()
        collect = target.get("collect", [])

        if "memory_usage" in collect:
            used_mb = round(info.get("used_memory", 0) / 1024 / 1024, 1)
            peak_mb = round(info.get("used_memory_peak", 0) / 1024 / 1024, 1)
            result["metrics"]["memory_used_mb"] = used_mb
            result["metrics"]["memory_peak_mb"] = peak_mb
            result["metrics"]["memory_fragmentation_ratio"] = info.get("mem_fragmentation_ratio", 0)

        if "connected_clients" in collect:
            result["metrics"]["connected_clients"] = info.get("connected_clients", 0)
            result["metrics"]["blocked_clients"] = info.get("blocked_clients", 0)

        if "keyspace_stats" in collect:
            total_keys = 0
            for key, val in info.items():
                if key.startswith("db"):
                    if isinstance(val, dict):
                        total_keys += val.get("keys", 0)
            result["metrics"]["total_keys"] = total_keys

        if "evicted_keys" in collect:
            result["metrics"]["evicted_keys"] = info.get("evicted_keys", 0)
            if info.get("evicted_keys", 0) > 0:
                result["events"].append({
                    "node_id": f"db:{target['id']}",
                    "type": "redis_evictions",
                    "severity": "medium",
                    "source": f"db:{target['id']}",
                    "message": f"Redis {target['id']} has evicted {info['evicted_keys']} keys",
                    "data": {"evicted_keys": info["evicted_keys"]},
                })

        if "hit_rate" in collect:
            hits = info.get("keyspace_hits", 0)
            misses = info.get("keyspace_misses", 0)
            total = hits + misses
            hit_rate = round(hits / total * 100, 2) if total > 0 else 100
            result["metrics"]["hit_rate"] = hit_rate
            result["metrics"]["keyspace_hits"] = hits
            result["metrics"]["keyspace_misses"] = misses

        result["metrics"]["uptime_seconds"] = info.get("uptime_in_seconds", 0)
        result["metrics"]["ops_per_second"] = info.get("instantaneous_ops_per_sec", 0)

        await r.aclose()

    except ImportError:
        result["metrics"]["error"] = "redis package not installed"
    except Exception as e:
        result["metrics"]["error"] = str(e)[:500]
        result["events"].append({
            "node_id": f"db:{target['id']}",
            "type": "db_connection_error",
            "severity": "critical",
            "source": f"db:{target['id']}",
            "message": f"Cannot connect to Redis {target['id']}: {str(e)[:200]}",
            "data": {"error": str(e)[:500]},
        })

    return result


async def collect_target(target: dict) -> dict:
    """Route to the right collector based on type."""
    db_type = target.get("type", "").lower()
    if db_type == "postgres":
        return await collect_postgres(target)
    elif db_type == "redis":
        return await collect_redis(target)
    else:
        return {"target_id": target.get("id", "?"), "error": f"Unknown type: {db_type}"}


async def dbmonitor_loop():
    """Background loop — polls all configured databases."""
    load_targets()
    if not _targets:
        print("[DBMonitor] No targets configured — skipping")
        return

    print(f"[DBMonitor] Monitoring {len(_targets)} databases")
    import httpx

    next_run: dict[str, float] = {}

    while True:
        now = asyncio.get_event_loop().time()

        for target in _targets:
            tid = target.get("id", "")
            interval = target.get("interval_seconds", 30)
            if now >= next_run.get(tid, 0):
                next_run[tid] = now + interval
                try:
                    result = await collect_target(target)
                    _latest_results[tid] = result

                    # Ship events
                    if result.get("events"):
                        async with httpx.AsyncClient() as client:
                            for ev in result["events"]:
                                try:
                                    await client.post(
                                        f"http://localhost:{os.getenv('PORT', '8000')}/api/ingest/events",
                                        json=ev, timeout=5
                                    )
                                except Exception:
                                    pass
                except Exception as e:
                    print(f"[DBMonitor] Error polling {tid}: {e}")

        await asyncio.sleep(5)


def get_db_results() -> list[dict]:
    return list(_latest_results.values())


def get_db_targets() -> list[dict]:
    if not _targets:
        load_targets()
    return _targets
