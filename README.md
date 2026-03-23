# PULSE — AI-Powered Infrastructure Intelligence Platform

PULSE is an industry-grade monitoring, observability, and incident response platform. It combines real-time infrastructure monitoring, AI-powered root cause analysis, custom dashboards, on-call scheduling, and workflow automation — everything you need to run production infrastructure, at a fraction of the cost of Datadog + PagerDuty + Statuspage.

> 18,000+ lines of code. 45+ Python modules. 31 dashboard views. Deployed on Kubernetes.

---

## What It Does

| Category | Capabilities |
|---|---|
| **Monitoring** | Linux, Windows, macOS, Docker, VMs, SNMP devices (routers, switches, firewalls, UPS), SSH agentless, auto-discovery |
| **Observability** | Real-time metrics, distributed tracing (OpenTelemetry), log aggregation, service topology, anomaly detection |
| **Alerting** | YAML rules engine, log-based alerts (keyword/regex/rate/absence), pre-built template packs, 13 notification channels, multi-step escalation |
| **AI Intelligence** | GPT-4o / Ollama RCA, natural language queries, predictive alerting, anomaly detection |
| **Incident Response** | Auto-correlation, AI root cause analysis, team routing, collaborative war room with live timeline, runbook automation |
| **Custom Dashboards** | Drag-and-drop widget builder — stat cards, charts, gauges, alert feeds, node lists |
| **On-Call Management** | Rotation schedules, escalation policies, overrides, page tracking (PagerDuty replacement) |
| **Status Pages** | Public-facing status page, service health tracking, incident updates (Statuspage.io replacement) |
| **Service Catalog** | Service definitions, ownership, dependencies, tiers, MTTR tracking |
| **Workflow Automation** | Visual trigger → condition → action chains for automated incident response |
| **SLO/SLA Tracking** | Error budget tracking, burn rate alerts, compliance reporting |
| **APM / Tracing** | Distributed tracing, span waterfall visualization, service dependency map, latency percentiles |
| **Metric Explorer** | Interactive query builder, 20 metrics, 9 aggregation functions, multi-series charting |
| **User Management** | Invite users, role-based access (admin/editor/viewer/responder), team assignment |
| **Billing & Usage** | Plan comparison (Free/Pro/Enterprise), usage meters, daily usage trends, overage tracking |
| **Multi-Environment** | Production/Staging/Dev/DR environment switcher, per-environment dashboards |
| **Audit Log** | Compliance-grade audit trail — auth, config, alert, incident, workflow events |
| **Integrations** | Jira, ServiceNow, Slack, Teams, Discord, Telegram, PagerDuty, Opsgenie, webhooks |

---

## Architecture

```
PULSE Platform
├── Agent (collector.py)          — Runs on every node, ships metrics + events
├── API (FastAPI)                 — REST + WebSocket, 150+ endpoints
│   ├── Detection Engine          — YAML rules, threshold evaluation
│   ├── AI RCA Engine             — GPT-4o / Ollama root cause analysis
│   ├── Correlation Engine        — Links alerts into incidents
│   ├── Notification Engine       — 13 channels (Slack, Teams, email, SMS, etc.)
│   ├── Escalation Engine         — Multi-step auto-escalation
│   ├── Anomaly Detection         — Statistical baseline deviation
│   ├── Predictive Engine         — Forecast metrics, predict alerts
│   ├── NL Query Engine           — Natural language → metric queries
│   ├── Workflow Engine           — Trigger → Condition → Action automation
│   ├── On-Call Scheduler         — Rotations, overrides, escalation policies
│   ├── Dashboard Builder         — Custom widget-based dashboards
│   ├── Service Catalog           — Service ownership + dependency mapping
│   ├── Status Page               — Public service health page
│   ├── Auth (JWT)                — Signup, login, RBAC
│   ├── Metric Explorer            — Interactive query builder, 9 aggregation functions
│   ├── Alert Templates            — Pre-built packs (Linux, K8s, PostgreSQL, Redis, Docker, Network)
│   ├── War Room                   — Collaborative incident timeline with responders
│   ├── User & Team Mgmt           — Invite, roles, teams, deactivation
│   ├── Billing Engine             — Plans, usage tracking, overage alerts
│   ├── APM / Tracing              — Distributed traces, span waterfall, service map
│   ├── Log Alerting               — Keyword, regex, rate, absence-based rules
│   ├── Environments               — Multi-env support (prod/staging/dev/DR)
│   ├── Audit Log                  — Compliance-grade event trail
│   └── Integrations               — Jira, ServiceNow, OpenTelemetry
├── Dashboard (index.html)         — 31-view SPA, Chart.js, Lucide icons
├── Database (PostgreSQL)         — Metrics, events, alerts, incidents, logs
├── Cache (Redis)                 — Real-time data, pub/sub
└── Kubernetes (minikube)         — 2x API replicas, DaemonSet agent
```

---

## Quick Start

**Docker Compose (simplest):**
```bash
git clone https://github.com/YOUR_ORG/pulse.git && cd pulse
cp .env.example .env    # Edit: OPENAI_API_KEY or OLLAMA_URL
docker compose up -d
# Dashboard: http://localhost:8000
```

**Kubernetes (production):**
```bash
kubectl apply -f k8s/
minikube service pulse-api -n pulse --url
```

**Install agent on any node:**
```bash
# Linux / macOS
curl -sSL http://pulse-server:8000/install.sh | PULSE_API_URL=http://pulse-server:8000 sudo bash

# Windows (PowerShell as Admin)
$env:PULSE_API_URL = "http://pulse-server:8000"; irm http://pulse-server:8000/install.ps1 | iex
```

---

## Dashboard Views (31 total)

| Section | Views |
|---|---|
| **Monitor** | Overview, Nodes, Metric History |
| **Respond** | Alerts, Alert Rules, Incidents, Log Alerts |
| **Observe** | Event Feed, Service Topology, Log Stream, Synthetic Monitoring, APM / Traces |
| **Explore** | Metric Explorer |
| **Reliability** | SLO/SLA Tracking, Predictive Forecasts |
| **Intelligence** | Ask PULSE (NL Query), Reports, Knowledge Base |
| **Operate** | Custom Dashboards, Service Catalog, Workflows, On-Call, Status Page, Alert Templates |
| **Collaborate** | Incident War Room |
| **Admin** | Users & Teams, Billing & Usage, Audit Log, Environments, Settings |

---

## Feature Highlights

### Custom Dashboard Builder
Create unlimited dashboards with drag-and-drop widgets. Widget types: stat cards, line/area/bar charts, gauges, alert feeds, node lists, text/markdown, uptime bars. Save, duplicate, and share dashboards.

### On-Call Management (PagerDuty Replacement)
Define rotation schedules (daily/weekly), assign team members, manage escalation policies with multi-level rules. Override system for temporary schedule changes. Full page tracking and audit.

### Alerting Workflow Builder
Visual automation chains: **Trigger** (metric threshold, alert fired, security event, anomaly, SLO breach, schedule) → **Conditions** (time window, node filter, severity, business hours, cooldown) → **Actions** (notify, page on-call, create incident, run playbook, webhook, update status page, escalate).

### Public Status Page (Statuspage.io Replacement)
Define services, track operational status, publish incidents with update timelines. Public-facing page at `/status` — no auth required. 90-day uptime tracking per service.

### Service Catalog
Map every service in your organization: ownership (team), tier (0-3), dependencies, language/framework, repository, runbook links, SLO links, deploy frequency, MTTR, and incident count.

### Incident War Room
Real-time collaborative incident timeline. Auto-correlates alerts, metric spikes, log patterns, deployments, and responder actions into a single chronological view. Add responders, post communications, resolve incidents — all from one screen.

### Metric Explorer
Interactive query builder with 20 metrics across 5 groups (System, Network, Disk, Application, Container). 9 aggregation functions (avg, sum, max, min, rate, count, p95, p99, stddev). Adaptive time granularity with multi-series Chart.js visualization.

### Alert Template Packs
Pre-built alert rule libraries for Linux (6 rules), Kubernetes (7), PostgreSQL (6), Redis (5), Docker (5), and Network/HTTP (5). One-click import into active rules — get production-ready alerting in seconds.

### Billing & Usage Dashboard
Usage meters for metrics, logs, API calls, nodes, and storage. Daily usage trend charts, plan comparison cards (Free/Pro/Enterprise), and one-click plan changes. Built for SaaS self-service.

### Notification Center
In-app notification bell with unread count badge. Persistent feed of alerts, incidents, security events, deployments, and system notifications. Mark read/unread, filter by type.

---

## Stack

```
Python 3.11 / FastAPI      — API server (150+ endpoints)
PostgreSQL 15              — Persistent storage
Redis 7                    — Cache + real-time pub/sub
psutil                     — Cross-platform system metrics
Chart.js + Lucide          — Dashboard charting + icons
OpenAI / Ollama            — AI root cause analysis
Docker / Kubernetes        — Container orchestration
```

---

## Build Phases

| Phase | Features | Modules |
|---|---|---|
| **Phase 1** | Agent, detection, AI RCA, correlation, 13 notification channels, escalation, auto-remediation, topology, knowledge base, SDK, MCP | 15 modules |
| **Phase 2** | Synthetic monitoring, DB monitoring, anomaly detection, OpenTelemetry | 4 modules |
| **Phase 3** | RBAC, SLO/SLA, predictive alerting, NL query, Jira, ServiceNow, reports | 7 modules |
| **Phase 4** | JWT auth, login/signup, onboarding wizard, settings UI, alert rules CRUD, search, user profile | 1 module |
| **Phase 5** | Custom dashboards, on-call scheduling, public status page | 3 modules |
| **Phase 6** | Notification center, service catalog, alerting workflow builder | 3 modules |
| **Phase 7** | Log-based alerting, APM/distributed tracing, multi-environment, audit log, auto-refresh, WebSocket | 4 modules |
| **Phase 8** | Metric explorer, alert template packs, incident war room, user & team management, billing & usage | 5 modules |

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | For cloud RCA | GPT-4o root cause analysis |
| `OLLAMA_URL` | For air-gapped RCA | e.g. `http://ollama:11434` |
| `POSTGRES_PASSWORD` | Yes | Database password |
| `JWT_SECRET` | Optional | JWT signing key (auto-generated if not set) |
| `SLACK_BOT_TOKEN` | Optional | Slack notifications |
| `TEAMS_WEBHOOK_URL` | Optional | Microsoft Teams |
| `PAGERDUTY_API_KEY` | Optional | PagerDuty |
| `SNMP_TARGETS` | Optional | Comma-separated IPs |
| `SSH_TARGETS` | Optional | `user@host` pairs |
| `ENABLE_DISCOVERY` | Optional | LAN auto-discovery |

---

## Status

Production-ready. 8 phases complete. Deployed on Kubernetes with 2 API replicas and DaemonSet agent.
