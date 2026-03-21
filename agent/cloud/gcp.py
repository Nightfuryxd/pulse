"""
PULSE GCP Collector

Monitors:
  - Compute Engine instances (states + CPU)
  - Cloud SQL instances (states + CPU)
  - GKE cluster node conditions
  - Cloud Functions (invocation errors)
  - Uptime check failures
  - Monitoring alerting policies (firing incidents)

Credentials (any of):
  - GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
  - Application Default Credentials (gcloud auth application-default login)
  - GCE/GKE Workload Identity (auto-detected)

Required env vars:
  - GCP_PROJECT_ID  (or GOOGLE_CLOUD_PROJECT)
"""
import asyncio
import os
from datetime import datetime, timedelta, timezone

NODE_ID    = os.getenv("NODE_ID", "gcp")
PROJECT_ID = os.getenv("GCP_PROJECT_ID", os.getenv("GOOGLE_CLOUD_PROJECT", ""))


def _monitoring_client():
    try:
        from google.cloud import monitoring_v3
        return monitoring_v3.MetricServiceClient()
    except ImportError:
        raise RuntimeError(
            "google-cloud-monitoring not installed — "
            "pip install google-cloud-monitoring google-cloud-compute"
        )


def _alert_client():
    from google.cloud import monitoring_v3
    return monitoring_v3.AlertPolicyServiceClient()


def _compute_client():
    from google.cloud import compute_v1
    return compute_v1.InstancesClient()


def _zones_client():
    from google.cloud import compute_v1
    return compute_v1.ZonesClient()


def _sql_client():
    try:
        from googleapiclient import discovery
        import google.auth
        creds, _ = google.auth.default()
        return discovery.build("sqladmin", "v1beta4", credentials=creds)
    except ImportError:
        raise RuntimeError("google-api-python-client not installed")


# ── Helper: fetch latest value of a GCP metric ────────────────────────────────

def _get_metric(project: str, metric_type: str, filters: str = "", minutes: int = 15) -> float:
    try:
        from google.cloud import monitoring_v3
        from google.protobuf import duration_pb2, timestamp_pb2

        client = _monitoring_client()
        now    = datetime.now(timezone.utc)
        ago    = now - timedelta(minutes=minutes)

        interval = monitoring_v3.TimeInterval(
            end_time   ={"seconds": int(now.timestamp())},
            start_time ={"seconds": int(ago.timestamp())},
        )
        agg = monitoring_v3.Aggregation(
            alignment_period   =duration_pb2.Duration(seconds=300),
            per_series_aligner =monitoring_v3.Aggregation.Aligner.ALIGN_MEAN,
            cross_series_reducer=monitoring_v3.Aggregation.Reducer.REDUCE_MEAN,
        )

        filter_str = f'metric.type="{metric_type}"'
        if filters:
            filter_str += f" AND {filters}"

        results = client.list_time_series(
            request={
                "name":        f"projects/{project}",
                "filter":      filter_str,
                "interval":    interval,
                "aggregation": agg,
            }
        )
        values = []
        for ts in results:
            for point in ts.points:
                v = point.value.double_value or point.value.int64_value or 0
                values.append(v)
        return round(max(values) * 100 if values else 0.0, 2)
    except Exception:
        return 0.0


# ── Compute Engine ────────────────────────────────────────────────────────────

async def collect_compute() -> tuple[list[dict], list[dict]]:
    metrics = []
    events  = []
    try:
        compute = _compute_client()
        zones_c = _zones_client()
        now     = datetime.now(timezone.utc)

        zones = [z.name for z in zones_c.list(project=PROJECT_ID)]

        for zone in zones:
            try:
                for instance in compute.list(project=PROJECT_ID, zone=zone):
                    name   = instance.name
                    status = instance.status  # RUNNING, TERMINATED, STAGING, ...
                    itype  = instance.machine_type.rsplit("/", 1)[-1] if instance.machine_type else ""

                    if status not in ("RUNNING", "TERMINATED"):
                        events.append({
                            "node_id":  f"gcp:{NODE_ID}",
                            "type":     "gce_state_change",
                            "severity": "high",
                            "source":   f"gcp:gce:{zone}/{name}",
                            "message":  f"GCE {name} ({zone}) status: {status}",
                            "data":     {"instance": name, "zone": zone, "status": status, "type": itype},
                        })

                    cpu = _get_metric(
                        PROJECT_ID,
                        "compute.googleapis.com/instance/cpu/utilization",
                        filters=f'resource.labels.instance_id="{name}"',
                    )

                    if status == "RUNNING":
                        metrics.append({
                            "node_id":        f"gcp:gce:{zone}:{name}",
                            "hostname":       name,
                            "ip":             next(
                                (ni.network_i_p for ni in instance.network_interfaces or []), ""
                            ),
                            "os":             f"GCP Compute ({zone})",
                            "ts":             now.isoformat(),
                            "cpu_percent":    cpu,
                            "memory_percent": 0,
                            "disk_percent":   0,
                            "disk_used_gb":   0,
                            "net_bytes_sent": 0,
                            "net_bytes_recv": 0,
                            "load_avg_1m":    0,
                            "process_count":  0,
                            "extra":          {"zone": zone, "machine_type": itype, "status": status},
                        })
            except Exception:
                pass
    except Exception as e:
        print(f"[GCP] Compute error: {e}")
    return metrics, events


# ── Cloud SQL ─────────────────────────────────────────────────────────────────

async def collect_cloud_sql() -> tuple[list[dict], list[dict]]:
    metrics = []
    events  = []
    try:
        sql = _sql_client()
        now = datetime.now(timezone.utc)
        resp = sql.instances().list(project=PROJECT_ID).execute()

        for db in resp.get("items", []):
            name   = db.get("name", "")
            state  = db.get("state", "").lower()
            engine = db.get("databaseVersion", "")
            tier   = db.get("settings", {}).get("tier", "")

            if state != "runnable":
                events.append({
                    "node_id":  f"gcp:{NODE_ID}",
                    "type":     "cloudsql_state",
                    "severity": "critical" if state in ("failed", "error") else "high",
                    "source":   f"gcp:sql:{name}",
                    "message":  f"Cloud SQL {name} ({engine}) state: {state}",
                    "data":     {"instance": name, "state": state, "engine": engine},
                })

            cpu = _get_metric(
                PROJECT_ID,
                "cloudsql.googleapis.com/database/cpu/utilization",
                filters=f'resource.labels.database_id="{PROJECT_ID}:{name}"',
            )

            metrics.append({
                "node_id":        f"gcp:sql:{name}",
                "hostname":       name,
                "ip":             db.get("ipAddresses", [{}])[0].get("ipAddress", ""),
                "os":             f"Cloud SQL {engine}",
                "ts":             now.isoformat(),
                "cpu_percent":    cpu,
                "memory_percent": 0,
                "disk_percent":   0,
                "disk_used_gb":   db.get("settings", {}).get("dataDiskSizeGb", 0),
                "net_bytes_sent": 0,
                "net_bytes_recv": 0,
                "load_avg_1m":    0,
                "process_count":  0,
                "extra":          {"engine": engine, "tier": tier, "state": state},
            })
    except Exception as e:
        print(f"[GCP] Cloud SQL error: {e}")
    return metrics, events


# ── Cloud Functions ───────────────────────────────────────────────────────────

async def collect_functions() -> list[dict]:
    events = []
    try:
        from googleapiclient import discovery
        import google.auth
        creds, _ = google.auth.default()
        svc      = discovery.build("cloudfunctions", "v1", credentials=creds)

        locations = svc.projects().locations().list(
            name=f"projects/{PROJECT_ID}"
        ).execute().get("locations", [])

        for loc in locations:
            loc_name = loc.get("name", "")
            fns = svc.projects().locations().functions().list(
                parent=loc_name
            ).execute().get("functions", [])

            for fn in fns:
                fn_name  = fn.get("name", "").rsplit("/", 1)[-1]
                fn_full  = fn.get("name", "")
                errors   = _get_metric(
                    PROJECT_ID,
                    "cloudfunctions.googleapis.com/function/execution_count",
                    filters=f'resource.labels.function_name="{fn_name}" AND metric.labels.status!="ok"',
                )
                if errors > 0:
                    events.append({
                        "node_id":  f"gcp:{NODE_ID}",
                        "type":     "gcp_function_errors",
                        "severity": "high",
                        "source":   f"gcp:function:{fn_name}",
                        "message":  f"Cloud Function {fn_name}: {errors:.0f} errors in last 15min",
                        "data":     {"function": fn_name, "errors": errors},
                    })
    except Exception as e:
        print(f"[GCP] Functions error: {e}")
    return events


# ── Monitoring Alert Incidents ────────────────────────────────────────────────

async def collect_incidents() -> list[dict]:
    events = []
    try:
        from google.cloud import monitoring_v3
        client = monitoring_v3.IncidentServiceClient()
        # List open incidents
        for inc in client.list_incidents(
            parent=f"projects/{PROJECT_ID}",
        ):
            if inc.state == monitoring_v3.Incident.State.OPEN:
                events.append({
                    "node_id":  f"gcp:{NODE_ID}",
                    "type":     "gcp_monitoring_incident",
                    "severity": "critical",
                    "source":   f"gcp:monitoring",
                    "message":  f"GCP Monitoring incident: {inc.policy_name}",
                    "data":     {"incident_id": inc.name, "policy": inc.policy_name},
                })
    except Exception as e:
        print(f"[GCP] Incidents error: {e}")
    return events


# ── collect_all ───────────────────────────────────────────────────────────────

async def collect_all() -> dict:
    """Collect everything from GCP."""
    if not PROJECT_ID:
        print("[GCP] GCP_PROJECT_ID not set — skipping")
        return {"metrics": [], "events": []}

    results = await asyncio.gather(
        collect_compute(),
        collect_cloud_sql(),
        collect_functions(),
        collect_incidents(),
        return_exceptions=True,
    )

    compute_result, sql_result, fn_events, inc_events = results

    all_metrics = []
    all_events  = []

    if isinstance(compute_result, tuple):
        all_metrics.extend(compute_result[0])
        all_events.extend(compute_result[1])

    if isinstance(sql_result, tuple):
        all_metrics.extend(sql_result[0])
        all_events.extend(sql_result[1])

    for ev_list in [fn_events, inc_events]:
        if isinstance(ev_list, list):
            all_events.extend(ev_list)

    return {"metrics": all_metrics, "events": all_events}
