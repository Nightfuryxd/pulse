# PULSE — AI-Powered Infrastructure Intelligence Platform

PULSE is an industry-grade, fully air-gappable monitoring, threat detection, and incident response platform. It works on any OS, any platform, and any IP-connected device — and uses AI to tell engineers exactly what broke, why, and what to fix.

> Think SolarWinds + PagerDuty + Datadog — but open-source, AI-native, and works with zero internet dependency.

---

## What It Does

| Capability | Details |
|---|---|
| **Universal Monitoring** | Linux, Windows, macOS, Docker containers, VMs, bare metal |
| **Network Equipment** | Routers, switches, firewalls, printers, UPS via SNMP v2c |
| **Agentless SSH Collection** | Collect from remote Linux hosts without installing anything |
| **Auto Network Discovery** | Ping sweep a CIDR range, auto-probe SNMP + SSH |
| **AI Root Cause Analysis** | GPT-4o or local Ollama (air-gapped) — tells you why, not just what |
| **Team Auto-Routing** | Routes incidents to SecOps, NetOps, AppDev, DBA, Infra automatically |
| **War Room Bridging** | Creates Slack/Teams channels, notifies all SMEs with full context pre-loaded |
| **Real-Time Dashboard** | Live WebSocket feed, multi-node charts, incident drill-down with RCA |
| **Detection Rules** | YAML-defined rules — thresholds, windows, composite conditions |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        PULSE Platform                            │
│                                                                  │
│  ┌─────────────┐   ┌──────────────┐   ┌────────────────────┐    │
│  │  Collector  │   │  Detection   │   │    AI RCA Engine   │    │
│  │   Agent     │──▶│   Engine     │──▶│  GPT-4o / Ollama   │    │
│  │  (Universal)│   │  (YAML Rules)│   │                    │    │
│  └──────┬──────┘   └──────┬───────┘   └─────────┬──────────┘    │
│         │                 │                     │               │
│         ▼                 ▼                     ▼               │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                  FastAPI + PostgreSQL                    │    │
│  │         /api/ingest/metrics  /api/ingest/events          │    │
│  │         /api/alerts  /api/incidents  /ws/live             │    │
│  └──────────────────────────┬──────────────────────────────┘    │
│                             │                                    │
│            ┌────────────────┼────────────────┐                  │
│            ▼                ▼                ▼                  │
│   ┌──────────────┐  ┌─────────────┐  ┌──────────────┐          │
│   │  Team Router │  │  Slack Bot  │  │ Teams Webhook│          │
│   │ (YAML-based) │  │  War Room   │  │  Adaptive    │          │
│   └──────────────┘  └─────────────┘  └──────────────┘          │
└──────────────────────────────────────────────────────────────────┘

Monitored Sources:
  [Linux Agent] [macOS Agent] [Windows Agent]
  [SNMP: Router/Switch/Firewall/UPS] [SSH Agentless] [Auto-Discovered]
```

---

## Quick Start

**1. Clone and configure**
```bash
git clone https://github.com/YOUR_ORG/pulse.git
cd pulse
cp .env.example .env
# Edit .env — minimum required: OPENAI_API_KEY (or OLLAMA_URL for air-gapped)
```

**2. Start the platform**
```bash
docker compose up -d
```

Dashboard: `http://localhost:8000`

**3. Install agent on a node** (one command)
```bash
# Linux / macOS
curl -sSL http://your-pulse-server:8000/install.sh | \
  PULSE_API_URL=http://your-pulse-server:8000 sudo bash

# Windows (PowerShell as Administrator)
$env:PULSE_API_URL = "http://your-pulse-server:8000"
irm http://your-pulse-server:8000/install.ps1 | iex
```

**4. Monitor network equipment (SNMP)**
```bash
# Edit .env:
SNMP_TARGETS=192.168.1.1,192.168.1.254
SNMP_COMMUNITY=public
```

**5. Auto-discover everything on LAN**
```bash
# Edit .env:
ENABLE_DISCOVERY=true
NETWORK_RANGE=192.168.1.0/24
```

---

## Stack

```
FastAPI          — REST API + WebSocket real-time feed
PostgreSQL       — Time-series metrics, events, alerts, incidents
Redis            — Caching, pub/sub
psutil           — Cross-platform system metrics (Linux/Windows/macOS)
pysnmp           — SNMP v2c polling for network devices
OpenAI / Ollama  — AI root cause analysis (cloud or air-gapped)
Docker Compose   — One-command startup
Chart.js         — Real-time metric charts in dashboard
```

---

## Project Structure

```
pulse/
├── api/
│   ├── main.py         # FastAPI — ingest, alerts, incidents, WebSocket
│   ├── db.py           # SQLAlchemy models (Node, Metric, Event, Alert, Incident)
│   ├── detection.py    # YAML rule engine — windowed threshold evaluation
│   ├── rca.py          # AI root cause analysis (GPT-4o or Ollama)
│   ├── router.py       # Team routing + Slack/Teams war room bridging
│   ├── Dockerfile
│   └── requirements.txt
├── agent/
│   ├── collector.py    # Universal collector — psutil + SNMP + SSH + discovery
│   ├── Dockerfile
│   └── requirements.txt
├── config/
│   ├── rules.yaml      # Detection rules (CPU, memory, auth brute force, port scan…)
│   └── teams.yaml      # Team definitions (SecOps, NetOps, AppDev, DBA, Infra)
├── dashboard/
│   └── index.html      # Real-time dashboard (no build step, pure HTML/JS)
├── install.sh          # Linux/macOS one-liner installer (systemd / launchd service)
├── install.ps1         # Windows one-liner installer (Windows Service)
├── docker-compose.yml
└── .env.example
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | For cloud RCA | GPT-4o root cause analysis |
| `OLLAMA_URL` | For air-gapped RCA | e.g. `http://ollama:11434` |
| `POSTGRES_PASSWORD` | Yes | Database password |
| `SLACK_BOT_TOKEN` | Optional | War room Slack messages |
| `TEAMS_WEBHOOK_URL` | Optional | Microsoft Teams notifications |
| `PAGERDUTY_API_KEY` | Optional | PagerDuty escalation |
| `SNMP_TARGETS` | Optional | Comma-separated IPs of network devices |
| `SNMP_COMMUNITY` | Optional | SNMP v2c community string (default: `public`) |
| `SSH_TARGETS` | Optional | `user@host` pairs for agentless collection |
| `ENABLE_DISCOVERY` | Optional | `true` to enable LAN auto-discovery |
| `NETWORK_RANGE` | Optional | CIDR to sweep e.g. `192.168.1.0/24` |
| `TECH_STACK` | Optional | `django,postgres,nginx` — for stack-aware RCA advice |

---

## Detection Rules

Rules are defined in `config/rules.yaml`. Example:

```yaml
- id: cpu_critical
  name: Critical CPU Usage
  category: performance
  severity: critical
  condition: "cpu_percent >= 95"
  for_seconds: 60       # must be true for 60s window
  teams: [infra, appdev]

- id: auth_brute_force
  name: SSH Brute Force Attack
  category: security
  severity: critical
  condition: "count >= 10 and type == 'auth_failure'"
  window_seconds: 60
  teams: [secops]
```

---

## Team Routing

Teams are defined in `config/teams.yaml`:

```yaml
teams:
  - id: secops
    name: Security Operations
    domains: [security, auth, network]
    slack_channel: "#secops-incidents"
    pagerduty_service: security-oncall

  - id: netops
    name: Network Operations
    domains: [network, connectivity, snmp]
    slack_channel: "#netops-incidents"
```

---

## AI Root Cause Analysis

When a critical/high alert fires, PULSE automatically:

1. Collects the last 20 metric readings + 20 security events for that node
2. Sends them to GPT-4o (or Ollama) with full context: node info, tech stack, alert details
3. Gets back structured JSON:
   - `root_cause` — plain-English explanation
   - `confidence` — 0.0–1.0
   - `affected_components` — what's impacted
   - `blast_radius` — how far the impact spreads
   - `recommended_actions` — numbered steps to fix it
   - `stack_specific_advice` — specific commands for your tech stack
   - `owning_teams` — who should respond

4. Routes to the right teams and creates a Slack/Teams war room with all this context pre-loaded

---

## Air-Gapped Deployment

PULSE works with zero internet access:

```bash
# 1. Run Ollama on any machine with a GPU
docker run -d -p 11434:11434 ollama/ollama
docker exec ollama ollama pull llama3.1:8b

# 2. Point PULSE at it
OLLAMA_URL=http://your-ollama-host:11434
```

The API, detection engine, team routing, and dashboard all work fully offline. Only the RCA engine needs a model — either GPT-4o (internet) or Ollama (local).

---

## Agent Installer

### Linux / macOS
```bash
# Basic install
PULSE_API_URL=http://pulse:8000 sudo bash install.sh

# With SNMP targets
PULSE_API_URL=http://pulse:8000 \
SNMP_TARGETS=192.168.1.1,10.0.0.254 \
sudo bash install.sh

# Uninstall
sudo bash install.sh uninstall
```

### Windows (PowerShell as Administrator)
```powershell
$env:PULSE_API_URL = "http://pulse:8000"
$env:SNMP_TARGETS  = "192.168.1.1"
.\install.ps1

# Uninstall
.\install.ps1 -Uninstall
```

The installer:
- Detects the OS and registers as a proper service (systemd / launchd / Windows Service)
- Auto-installs Python if missing
- Creates a virtualenv with all dependencies
- Configures auto-restart on failure
- Downloads `collector.py` directly from your PULSE server

---

## Dashboard Views

| View | What You See |
|---|---|
| **Overview** | Live CPU/memory/disk/network charts, active alerts, node health sidebar, recent incidents |
| **Nodes** | Card grid of every monitored node (local agent, SNMP, SSH) with health status |
| **Metrics** | Historical charts for any node — 1h / 6h / 24h range |
| **Alerts** | Full alert table with severity filters, bulk resolve, per-alert resolve |
| **Incidents** | Incident list with expandable RCA — root cause, blast radius, action steps, team tags, bridge status |
| **Event Feed** | Security + system events — auth failures, port scans, OOM kills, segfaults |

---

## What Gets Monitored

**System metrics** (every 10s)
- CPU %, memory %, disk %, network bytes in/out
- Load average (1m, 5m, 15m)
- Process count
- Temperature sensors (Linux/macOS)

**Security events** (every 10s)
- SSH brute force (3+ failures in 60s → high, 10+ → critical)
- Port scan detection (20+ unique ports from one IP)
- Suspicious processes (crypto miners, reverse shells, known malware patterns)
- Zombie processes
- OOM kills
- Kernel segfaults
- Windows failed logon events (Event ID 4625)

**SNMP devices** (every 10s per device)
- CPU utilization
- Memory utilization
- Interface traffic (bytes in/out per interface)
- Interface errors
- System uptime
- Device description / model

---

## Status

Production-ready core: metrics pipeline, detection engine, AI RCA, team routing, dashboard.

Roadmap: SNMP v3, WMI Windows metrics, Kubernetes pod monitoring, custom webhook alerting, mobile push notifications.
