"""
Scheduled Reports — HTML/email reports for PULSE.

Generates periodic reports with:
  - Infrastructure health summary
  - Alert/incident statistics
  - SLO compliance status
  - Top issues and trends
  - Predictive insights

Reports can be sent via email (SMTP) or retrieved via API.
"""
import asyncio
import os
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

# ── Configuration ────────────────────────────────────────────────────────────

SMTP_HOST     = os.getenv("SMTP_HOST", "")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM     = os.getenv("SMTP_FROM", "pulse@localhost")
REPORT_RECIPIENTS = os.getenv("REPORT_RECIPIENTS", "").split(",")  # comma-separated emails

# Report schedule
DAILY_REPORT_HOUR  = int(os.getenv("DAILY_REPORT_HOUR", "8"))   # 8 AM
WEEKLY_REPORT_DAY  = int(os.getenv("WEEKLY_REPORT_DAY", "1"))   # Monday

_recent_reports: list[dict] = []


# ── HTML report generation ───────────────────────────────────────────────────

async def generate_report(period: str = "daily", db=None) -> dict:
    """Generate an HTML report for the given period (daily/weekly/monthly)."""
    now = datetime.utcnow()

    if period == "daily":
        since = now - timedelta(days=1)
        period_label = "Daily"
    elif period == "weekly":
        since = now - timedelta(weeks=1)
        period_label = "Weekly"
    else:
        since = now - timedelta(days=30)
        period_label = "Monthly"

    # Gather data
    data = await _gather_report_data(since, now, db)

    # Build HTML
    html = _build_html_report(data, period_label, since, now)

    report = {
        "period": period,
        "generated_at": now.isoformat(),
        "since": since.isoformat(),
        "until": now.isoformat(),
        "html": html,
        "stats": data.get("summary", {}),
    }

    _recent_reports.append(report)
    if len(_recent_reports) > 50:
        _recent_reports[:] = _recent_reports[-25:]

    return report


async def _gather_report_data(since: datetime, until: datetime, db=None) -> dict:
    """Gather all data needed for the report."""
    from synthetic import get_synthetic_results
    from anomaly import get_recent_anomalies
    from slo import get_slo_status, get_slo_breaches
    from predict import get_predictions

    # Get metrics from in-memory caches
    from main import _recent_metrics, _node_cache

    nodes = dict(_node_cache)
    metrics = dict(_recent_metrics)

    # Alert/incident counts from DB
    alert_stats = {}
    incident_stats = {}
    if db:
        from sqlalchemy import select, func
        from db import Alert, Incident

        total_alerts = (await db.execute(
            select(func.count(Alert.id)).where(Alert.ts >= since)
        )).scalar() or 0

        critical_alerts = (await db.execute(
            select(func.count(Alert.id)).where(Alert.ts >= since, Alert.severity == "critical")
        )).scalar() or 0

        resolved_alerts = (await db.execute(
            select(func.count(Alert.id)).where(Alert.ts >= since, Alert.resolved == True)
        )).scalar() or 0

        total_incidents = (await db.execute(
            select(func.count(Incident.id)).where(Incident.ts >= since)
        )).scalar() or 0

        resolved_incidents = (await db.execute(
            select(func.count(Incident.id)).where(Incident.ts >= since, Incident.status == "resolved")
        )).scalar() or 0

        alert_stats = {
            "total": total_alerts,
            "critical": critical_alerts,
            "resolved": resolved_alerts,
            "resolution_rate": round((resolved_alerts / total_alerts * 100) if total_alerts > 0 else 100, 1),
        }
        incident_stats = {
            "total": total_incidents,
            "resolved": resolved_incidents,
        }

    synthetic = get_synthetic_results()
    synthetic_up = sum(1 for r in synthetic if r.get("status") == "up")

    anomalies = get_recent_anomalies(limit=50)
    slo_status = get_slo_status()
    slo_breaches = get_slo_breaches(limit=20)
    predictions = get_predictions(limit=20)

    # Node health summary
    node_health = []
    for node_id, latest in metrics.items():
        if latest:
            last = latest[-1] if isinstance(latest, list) else latest
            node_health.append({
                "node_id": node_id,
                "cpu": last.get("cpu_percent", 0),
                "memory": last.get("memory_percent", 0),
                "disk": last.get("disk_percent", 0),
            })

    return {
        "summary": {
            "total_nodes": len(nodes),
            "alerts": alert_stats,
            "incidents": incident_stats,
            "synthetic_up": synthetic_up,
            "synthetic_total": len(synthetic),
            "anomaly_count": len(anomalies),
            "slo_breaches": len(slo_breaches),
            "predictions": len(predictions),
        },
        "node_health": sorted(node_health, key=lambda x: x.get("cpu", 0), reverse=True),
        "synthetic": synthetic,
        "anomalies": anomalies[:10],
        "slo_status": slo_status,
        "slo_breaches": slo_breaches,
        "predictions": predictions[:10],
    }


def _build_html_report(data: dict, period_label: str, since: datetime, until: datetime) -> str:
    """Build the HTML report."""
    summary = data.get("summary", {})
    alerts = summary.get("alerts", {})
    incidents = summary.get("incidents", {})

    # Node health rows
    node_rows = ""
    for n in data.get("node_health", [])[:20]:
        cpu_color = "#e74c3c" if n["cpu"] > 80 else ("#f39c12" if n["cpu"] > 60 else "#27ae60")
        mem_color = "#e74c3c" if n["memory"] > 85 else ("#f39c12" if n["memory"] > 70 else "#27ae60")
        disk_color = "#e74c3c" if n["disk"] > 85 else ("#f39c12" if n["disk"] > 70 else "#27ae60")
        node_rows += f"""<tr>
            <td style="padding:8px;border-bottom:1px solid #eee">{n['node_id']}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;color:{cpu_color};font-weight:bold">{n['cpu']:.1f}%</td>
            <td style="padding:8px;border-bottom:1px solid #eee;color:{mem_color};font-weight:bold">{n['memory']:.1f}%</td>
            <td style="padding:8px;border-bottom:1px solid #eee;color:{disk_color};font-weight:bold">{n['disk']:.1f}%</td>
        </tr>"""

    # Synthetic rows
    synthetic_rows = ""
    for s in data.get("synthetic", []):
        status_color = "#27ae60" if s.get("status") == "up" else "#e74c3c"
        latency = s.get("response_time_ms", 0)
        synthetic_rows += f"""<tr>
            <td style="padding:8px;border-bottom:1px solid #eee">{s.get('id','')}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;color:{status_color};font-weight:bold">{s.get('status','?').upper()}</td>
            <td style="padding:8px;border-bottom:1px solid #eee">{latency:.0f}ms</td>
        </tr>"""

    # SLO rows
    slo_rows = ""
    for slo_id, status in data.get("slo_status", {}).items():
        slo_color = "#27ae60" if status.get("status") == "met" else "#e74c3c"
        compliance = status.get("compliance")
        compliance_str = f"{compliance:.2f}%" if compliance is not None else "N/A"
        slo_rows += f"""<tr>
            <td style="padding:8px;border-bottom:1px solid #eee">{status.get('name', slo_id)}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;color:{slo_color};font-weight:bold">{status.get('status','?').upper()}</td>
            <td style="padding:8px;border-bottom:1px solid #eee">{compliance_str}</td>
        </tr>"""

    # Prediction rows
    prediction_rows = ""
    for p in data.get("predictions", []):
        prediction_rows += f"""<tr>
            <td style="padding:8px;border-bottom:1px solid #eee">{p.get('node_id','')}</td>
            <td style="padding:8px;border-bottom:1px solid #eee">{p.get('metric','')}</td>
            <td style="padding:8px;border-bottom:1px solid #eee">{p.get('current_value',0)}{p.get('unit','')}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;color:#e74c3c;font-weight:bold">{p.get('predicted_value',0)}{p.get('unit','')}</td>
            <td style="padding:8px;border-bottom:1px solid #eee">{p.get('time_to_breach_minutes',0):.0f}m</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>PULSE {period_label} Report</title></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:800px;margin:0 auto;padding:20px;color:#333;background:#f8f9fa">

<div style="background:linear-gradient(135deg,#667eea,#764ba2);color:white;padding:30px;border-radius:12px;margin-bottom:20px">
    <h1 style="margin:0;font-size:28px">PULSE {period_label} Report</h1>
    <p style="margin:5px 0 0;opacity:0.9">{since.strftime('%Y-%m-%d %H:%M')} — {until.strftime('%Y-%m-%d %H:%M')} UTC</p>
</div>

<!-- Summary Cards -->
<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px">
    <div style="background:white;padding:16px;border-radius:8px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,0.1)">
        <div style="font-size:32px;font-weight:bold;color:#667eea">{summary.get('total_nodes',0)}</div>
        <div style="color:#888;font-size:13px">Nodes</div>
    </div>
    <div style="background:white;padding:16px;border-radius:8px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,0.1)">
        <div style="font-size:32px;font-weight:bold;color:#e74c3c">{alerts.get('total',0)}</div>
        <div style="color:#888;font-size:13px">Alerts</div>
    </div>
    <div style="background:white;padding:16px;border-radius:8px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,0.1)">
        <div style="font-size:32px;font-weight:bold;color:#f39c12">{incidents.get('total',0)}</div>
        <div style="color:#888;font-size:13px">Incidents</div>
    </div>
    <div style="background:white;padding:16px;border-radius:8px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,0.1)">
        <div style="font-size:32px;font-weight:bold;color:#27ae60">{summary.get('synthetic_up',0)}/{summary.get('synthetic_total',0)}</div>
        <div style="color:#888;font-size:13px">Probes UP</div>
    </div>
</div>

<!-- Alert Resolution -->
<div style="background:white;padding:20px;border-radius:8px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,0.1)">
    <h2 style="margin-top:0;color:#333;border-bottom:2px solid #667eea;padding-bottom:8px">Alert Summary</h2>
    <table style="width:100%">
        <tr><td>Total Alerts</td><td style="font-weight:bold;text-align:right">{alerts.get('total',0)}</td></tr>
        <tr><td>Critical Alerts</td><td style="font-weight:bold;text-align:right;color:#e74c3c">{alerts.get('critical',0)}</td></tr>
        <tr><td>Resolved</td><td style="font-weight:bold;text-align:right;color:#27ae60">{alerts.get('resolved',0)}</td></tr>
        <tr><td>Resolution Rate</td><td style="font-weight:bold;text-align:right">{alerts.get('resolution_rate',100)}%</td></tr>
    </table>
</div>

<!-- Node Health -->
<div style="background:white;padding:20px;border-radius:8px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,0.1)">
    <h2 style="margin-top:0;color:#333;border-bottom:2px solid #667eea;padding-bottom:8px">Node Health</h2>
    <table style="width:100%;border-collapse:collapse">
        <thead><tr style="background:#f8f9fa">
            <th style="padding:8px;text-align:left">Node</th>
            <th style="padding:8px;text-align:left">CPU</th>
            <th style="padding:8px;text-align:left">Memory</th>
            <th style="padding:8px;text-align:left">Disk</th>
        </tr></thead>
        <tbody>{node_rows if node_rows else '<tr><td colspan="4" style="padding:8px;color:#888">No node data</td></tr>'}</tbody>
    </table>
</div>

<!-- Synthetic Monitoring -->
<div style="background:white;padding:20px;border-radius:8px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,0.1)">
    <h2 style="margin-top:0;color:#333;border-bottom:2px solid #667eea;padding-bottom:8px">Synthetic Monitoring</h2>
    <table style="width:100%;border-collapse:collapse">
        <thead><tr style="background:#f8f9fa">
            <th style="padding:8px;text-align:left">Target</th>
            <th style="padding:8px;text-align:left">Status</th>
            <th style="padding:8px;text-align:left">Latency</th>
        </tr></thead>
        <tbody>{synthetic_rows if synthetic_rows else '<tr><td colspan="3" style="padding:8px;color:#888">No synthetic data</td></tr>'}</tbody>
    </table>
</div>

<!-- SLO Compliance -->
{"" if not slo_rows else f'''<div style="background:white;padding:20px;border-radius:8px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,0.1)">
    <h2 style="margin-top:0;color:#333;border-bottom:2px solid #667eea;padding-bottom:8px">SLO Compliance</h2>
    <table style="width:100%;border-collapse:collapse">
        <thead><tr style="background:#f8f9fa">
            <th style="padding:8px;text-align:left">SLO</th>
            <th style="padding:8px;text-align:left">Status</th>
            <th style="padding:8px;text-align:left">Compliance</th>
        </tr></thead>
        <tbody>{slo_rows}</tbody>
    </table>
</div>'''}

<!-- Predictive Insights -->
{"" if not prediction_rows else f'''<div style="background:white;padding:20px;border-radius:8px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,0.1)">
    <h2 style="margin-top:0;color:#333;border-bottom:2px solid #667eea;padding-bottom:8px">Predictive Insights</h2>
    <table style="width:100%;border-collapse:collapse">
        <thead><tr style="background:#f8f9fa">
            <th style="padding:8px;text-align:left">Node</th>
            <th style="padding:8px;text-align:left">Metric</th>
            <th style="padding:8px;text-align:left">Current</th>
            <th style="padding:8px;text-align:left">Predicted</th>
            <th style="padding:8px;text-align:left">Time to Breach</th>
        </tr></thead>
        <tbody>{prediction_rows}</tbody>
    </table>
</div>'''}

<div style="text-align:center;color:#888;font-size:12px;padding:20px">
    Generated by PULSE v4.0 | {until.strftime('%Y-%m-%d %H:%M:%S')} UTC
</div>

</body></html>"""

    return html


# ── Email delivery ───────────────────────────────────────────────────────────

def send_report_email(report: dict, recipients: list[str] = None) -> dict:
    """Send report via SMTP email."""
    if not SMTP_HOST:
        return {"error": "SMTP not configured. Set SMTP_HOST, SMTP_USER, SMTP_PASSWORD."}

    to_addrs = recipients or [r.strip() for r in REPORT_RECIPIENTS if r.strip()]
    if not to_addrs:
        return {"error": "No recipients configured. Set REPORT_RECIPIENTS env var."}

    period = report.get("period", "daily").capitalize()
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"PULSE {period} Report — {report.get('generated_at', '')[:10]}"
    msg["From"] = SMTP_FROM
    msg["To"] = ", ".join(to_addrs)

    html_part = MIMEText(report.get("html", ""), "html")
    msg.attach(html_part)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            if SMTP_USER:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, to_addrs, msg.as_string())
        return {"sent": True, "recipients": to_addrs}
    except Exception as e:
        return {"error": f"Email send failed: {e}"}


# ── Query ────────────────────────────────────────────────────────────────────

def get_recent_reports(limit: int = 10) -> list[dict]:
    """Get recent reports (without HTML body for listing)."""
    return [
        {k: v for k, v in r.items() if k != "html"}
        for r in _recent_reports[-limit:]
    ]


# ── Scheduled loop ──────────────────────────────────────────────────────────

async def report_loop():
    """Background loop that generates daily/weekly reports on schedule."""
    last_daily = None
    last_weekly = None

    while True:
        try:
            now = datetime.utcnow()

            # Daily report
            if now.hour == DAILY_REPORT_HOUR and (not last_daily or last_daily.date() < now.date()):
                print(f"[Reports] Generating daily report...")
                report = await generate_report("daily")
                if SMTP_HOST:
                    result = send_report_email(report)
                    print(f"[Reports] Daily report email: {result}")
                last_daily = now

            # Weekly report (Monday)
            if now.weekday() == WEEKLY_REPORT_DAY and now.hour == DAILY_REPORT_HOUR:
                if not last_weekly or (now - last_weekly).days >= 6:
                    print(f"[Reports] Generating weekly report...")
                    report = await generate_report("weekly")
                    if SMTP_HOST:
                        result = send_report_email(report)
                        print(f"[Reports] Weekly report email: {result}")
                    last_weekly = now

        except Exception as e:
            print(f"[Reports] Error: {e}")

        await asyncio.sleep(300)  # Check every 5 minutes
