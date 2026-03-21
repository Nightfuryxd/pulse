"""
PULSE AWS Collector

Pulls metrics and events from:
  - CloudWatch (EC2, RDS, ELB, Lambda, ECS)
  - EC2 instance states
  - RDS database events
  - ELB/ALB health
  - Lambda error rates
  - ECS task states
  - CloudWatch Alarms
  - Cost anomalies (optional)

Requires: boto3, AWS credentials (IAM role, env vars, or ~/.aws/credentials)
"""
import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

NODE_ID = os.getenv("NODE_ID", "aws")
AWS_REGION = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1"))


def _boto3_client(service: str):
    try:
        import boto3
        return boto3.client(service, region_name=AWS_REGION)
    except ImportError:
        raise RuntimeError("boto3 not installed — pip install boto3")


async def collect_cloudwatch_alarms() -> list[dict]:
    """Get all CloudWatch alarms in ALARM state."""
    events = []
    try:
        cw = _boto3_client("cloudwatch")
        paginator = cw.get_paginator("describe_alarms")
        for page in paginator.paginate(StateValue="ALARM"):
            for alarm in page.get("MetricAlarms", []):
                events.append({
                    "node_id":  f"aws:{NODE_ID}",
                    "type":     "cloudwatch_alarm",
                    "severity": "critical" if "Critical" in alarm.get("AlarmName","") else "high",
                    "source":   "aws:cloudwatch",
                    "message":  f"[ALARM] {alarm['AlarmName']}: {alarm.get('StateReason','')}",
                    "data": {
                        "alarm_name":    alarm["AlarmName"],
                        "metric_name":   alarm.get("MetricName",""),
                        "namespace":     alarm.get("Namespace",""),
                        "threshold":     alarm.get("Threshold"),
                        "state_reason":  alarm.get("StateReason",""),
                        "region":        AWS_REGION,
                    },
                })
    except Exception as e:
        print(f"[AWS] CloudWatch alarms error: {e}")
    return events


async def collect_ec2_instances() -> tuple[list[dict], list[dict]]:
    """Collect EC2 instance states and metrics."""
    metrics = []
    events  = []
    try:
        ec2 = _boto3_client("ec2")
        cw  = _boto3_client("cloudwatch")
        response = ec2.describe_instances()
        now  = datetime.now(timezone.utc)
        ago  = now - timedelta(minutes=15)

        for reservation in response.get("Reservations", []):
            for instance in reservation.get("Instances", []):
                iid    = instance["InstanceId"]
                state  = instance["State"]["Name"]
                itype  = instance.get("InstanceType","")
                az     = instance.get("Placement",{}).get("AvailabilityZone","")
                name   = next((t["Value"] for t in instance.get("Tags",[]) if t["Key"]=="Name"), iid)

                if state not in ("running", "stopped", "terminated"):
                    events.append({
                        "node_id":  f"aws:{NODE_ID}",
                        "type":     "ec2_state_change",
                        "severity": "high",
                        "source":   f"aws:ec2:{iid}",
                        "message":  f"EC2 {name} ({iid}) state: {state}",
                        "data":     {"instance_id": iid, "name": name, "state": state, "type": itype},
                    })

                # Fetch CPU from CloudWatch
                cpu = 0.0
                try:
                    r = cw.get_metric_statistics(
                        Namespace="AWS/EC2",
                        MetricName="CPUUtilization",
                        Dimensions=[{"Name": "InstanceId", "Value": iid}],
                        StartTime=ago, EndTime=now,
                        Period=300, Statistics=["Average"],
                    )
                    if r["Datapoints"]:
                        cpu = max(d["Average"] for d in r["Datapoints"])
                except Exception:
                    pass

                if state == "running":
                    metrics.append({
                        "node_id":     f"aws:ec2:{iid}",
                        "hostname":    name,
                        "ip":          instance.get("PrivateIpAddress",""),
                        "os":          "AWS EC2",
                        "ts":          now.isoformat(),
                        "cpu_percent": round(cpu, 1),
                        "memory_percent": 0,
                        "disk_percent":   0,
                        "disk_used_gb":   0,
                        "net_bytes_sent": 0,
                        "net_bytes_recv": 0,
                        "load_avg_1m":    0,
                        "process_count":  0,
                        "extra": {"instance_type": itype, "az": az, "state": state},
                    })
    except Exception as e:
        print(f"[AWS] EC2 error: {e}")
    return metrics, events


async def collect_rds() -> tuple[list[dict], list[dict]]:
    """Collect RDS instance states and metrics."""
    metrics = []
    events  = []
    try:
        rds = _boto3_client("rds")
        cw  = _boto3_client("cloudwatch")
        response = rds.describe_db_instances()
        now = datetime.now(timezone.utc)
        ago = now - timedelta(minutes=15)

        for db in response.get("DBInstances", []):
            did    = db["DBInstanceIdentifier"]
            status = db["DBInstanceStatus"]
            engine = db.get("Engine","")

            if status != "available":
                events.append({
                    "node_id":  f"aws:{NODE_ID}",
                    "type":     "rds_state_change",
                    "severity": "critical" if status in ("failed","incompatible-network") else "high",
                    "source":   f"aws:rds:{did}",
                    "message":  f"RDS {did} ({engine}) status: {status}",
                    "data":     {"db_id": did, "status": status, "engine": engine},
                })

            # CPU + connections
            cpu_pct = conn_count = 0.0
            for metric_name, var_name in [("CPUUtilization","cpu_pct"),("DatabaseConnections","conn_count")]:
                try:
                    r = cw.get_metric_statistics(
                        Namespace="AWS/RDS",
                        MetricName=metric_name,
                        Dimensions=[{"Name": "DBInstanceIdentifier", "Value": did}],
                        StartTime=ago, EndTime=now,
                        Period=300, Statistics=["Average"],
                    )
                    if r["Datapoints"]:
                        val = max(d["Average"] for d in r["Datapoints"])
                        if var_name == "cpu_pct":   cpu_pct    = val
                        if var_name == "conn_count": conn_count = val
                except Exception:
                    pass

            metrics.append({
                "node_id":       f"aws:rds:{did}",
                "hostname":      did,
                "ip":            db.get("Endpoint",{}).get("Address",""),
                "os":            f"AWS RDS {engine}",
                "ts":            now.isoformat(),
                "cpu_percent":   round(cpu_pct, 1),
                "memory_percent": 0,
                "disk_percent":   0,
                "disk_used_gb":   db.get("AllocatedStorage", 0),
                "net_bytes_sent": 0,
                "net_bytes_recv": 0,
                "load_avg_1m":    0,
                "process_count":  int(conn_count),
                "extra":         {"engine": engine, "status": status, "connections": conn_count},
            })
    except Exception as e:
        print(f"[AWS] RDS error: {e}")
    return metrics, events


async def collect_lambda() -> list[dict]:
    """Get Lambda function error rates."""
    events = []
    try:
        lmb = _boto3_client("lambda")
        cw  = _boto3_client("cloudwatch")
        now = datetime.now(timezone.utc)
        ago = now - timedelta(minutes=15)
        fns = lmb.list_functions().get("Functions", [])

        for fn in fns:
            fname = fn["FunctionName"]
            try:
                r = cw.get_metric_statistics(
                    Namespace="AWS/Lambda",
                    MetricName="Errors",
                    Dimensions=[{"Name": "FunctionName", "Value": fname}],
                    StartTime=ago, EndTime=now,
                    Period=300, Statistics=["Sum"],
                )
                errors = sum(d["Sum"] for d in r.get("Datapoints", []))
                if errors > 0:
                    events.append({
                        "node_id":  f"aws:{NODE_ID}",
                        "type":     "lambda_errors",
                        "severity": "high",
                        "source":   f"aws:lambda:{fname}",
                        "message":  f"Lambda {fname}: {errors:.0f} errors in last 15min",
                        "data":     {"function": fname, "errors": errors},
                    })
            except Exception:
                pass
    except Exception as e:
        print(f"[AWS] Lambda error: {e}")
    return events


async def collect_all() -> dict:
    """Collect everything from AWS."""
    alarm_events, (ec2_metrics, ec2_events), (rds_metrics, rds_events), lambda_events = \
        await asyncio.gather(
            collect_cloudwatch_alarms(),
            collect_ec2_instances(),
            collect_rds(),
            collect_lambda(),
            return_exceptions=True,
        )

    all_metrics = []
    all_events  = []

    for result in [alarm_events, ec2_events, rds_events, lambda_events]:
        if isinstance(result, list):
            all_events.extend(result)

    for result in [ec2_metrics, rds_metrics]:
        if isinstance(result, list):
            all_metrics.extend(result)

    return {"metrics": all_metrics, "events": all_events}
