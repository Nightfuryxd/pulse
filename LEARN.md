# How PULSE Works — Learn DevOps From What You Built

---

## 1. Docker — Why We Use It

**Problem:** "It works on my machine" — but breaks on yours.

**Solution:** Docker packages your app + all its dependencies into a container. Same environment everywhere.

**Your PULSE setup has 4 containers:**

```
pulse-api       → Your FastAPI app (the brain)
pulse-postgres  → Database (stores metrics, alerts, incidents)
pulse-redis     → Cache (fast temporary storage)
pulse-agent     → Collector (gathers CPU, memory, disk data)
```

**docker-compose.yml** ties them together. Key concepts:

```yaml
services:
  api:
    build: ./api              # Build image from api/Dockerfile
    ports:
      - "8001:8000"           # YOUR Mac port 8001 → container port 8000
    depends_on:
      postgres:
        condition: service_healthy   # Don't start API until DB is ready
```

- **Port mapping `8001:8000`** — Container runs on 8000 internally. You access it on 8001 from your browser. Like an apartment number vs street address.
- **depends_on + healthy** — Without this, API starts before database is ready → crash.
- **Volumes** — Files shared between your Mac and the container. That's why code changes appear instantly.

**Commands you should know:**
```bash
docker compose up -d        # Start everything in background
docker compose down         # Stop everything
docker compose logs api     # See what API is printing
docker compose build api    # Rebuild after code changes
docker compose ps           # What's running?
```

---

## 2. PostgreSQL — The Database

**What it stores:** Every metric, alert, incident, event, node — permanently.

**Why not just keep it in memory?** Restart the app → everything gone. Database survives restarts.

**Your tables (defined in `api/db.py`):**

| Table | What It Stores |
|---|---|
| `nodes` | Every server/device being monitored |
| `metrics` | CPU %, memory %, disk %, network — every 10 seconds |
| `events` | Security events (SSH brute force, port scans) |
| `alerts` | When a detection rule fires (CPU > 95%) |
| `incidents` | When AI analyzes an alert and produces RCA |

**SQLAlchemy** is the Python library that talks to PostgreSQL. Instead of writing raw SQL:
```python
# Instead of: SELECT * FROM nodes WHERE node_id = 'prod-01'
# You write:
node = await db.execute(select(Node).where(Node.node_id == "prod-01"))
```

**Why also Redis?** PostgreSQL is reliable but slow for real-time. Redis is RAM-based — instant reads. We use it for caching and pub/sub (WebSocket broadcasts).

---

## 3. FastAPI — The API

**What it is:** A Python web framework. It receives HTTP requests and returns JSON.

**The flow when the agent sends metrics:**

```
Agent (collector.py) every 10 seconds:
  → POST http://pulse-api:8000/api/ingest/metrics
  → Body: {"node_id": "prod-01", "cpu": 85.2, "memory": 62.1, ...}

API (main.py) receives it:
  1. Save to PostgreSQL (permanent storage)
  2. Check detection rules (is CPU > 95%? → fire alert)
  3. If alert → run AI RCA → create incident → notify teams
  4. Broadcast to WebSocket (dashboard updates live)
```

**Key decorators:**
```python
@app.get("/api/nodes")      # Handles GET requests to /api/nodes
@app.post("/api/ingest/metrics")  # Handles POST requests
```

**Pydantic** validates incoming data — rejects garbage before it hits your database.

---

## 4. The Notification System You Built

**Architecture — Provider Pattern:**

```
Incident fires
  → router.py: "Which teams own this?" (matches by category/AI)
  → notifications.py: "What channels does each team use?" (from teams.yaml)
  → Send to ALL channels in parallel (Slack + Telegram + PagerDuty at once)
  → escalation.py: "Start timer — if not acknowledged in 5 min, escalate"
```

**To add a 14th provider, you'd:**
1. Write one async function in `notifications.py` (copy any existing one as template)
2. Add it to `PROVIDER_MAP` dict at the bottom
3. Add the contact field in `teams.yaml`
4. Add env var in `.env.example` if it needs an API key

That's it. Every provider follows the same pattern:
```python
async def send_whatever(target: str, payload: dict) -> dict:
    # Format message for this platform
    # POST to their API
    # Return {"provider": "whatever", "status": "sent" or "failed"}
```

---

## 5. YAML Config — Why Not Hardcode?

**Problem:** Changing alert thresholds means editing Python code, rebuilding Docker, restarting.

**Solution:** YAML config files. Change a number, restart, done.

```yaml
# config/rules.yaml — change threshold without touching code
- id: cpu_critical
  condition: "cpu_percent >= 95"
  for_seconds: 60
  teams: [infra, appdev]
```

```yaml
# config/teams.yaml — add a new team without touching code
- id: secops
  domains: [threat, auth_failure]
  contact:
    slack: "#secops-alerts"
    telegram: "982892344"
```

```yaml
# config/escalation.yaml — change timing without touching code
critical:
  tiers:
    - after_minutes: 5    # L1 at 5 min
    - after_minutes: 15   # L2 at 15 min
```

**Key principle:** Code handles logic. Config handles settings. Separate them.

---

## 6. Git — Version Control

**What it does:** Tracks every change you make. You can undo anything, see who changed what, and work with others without overwriting each other.

**Commands you need:**
```bash
git status          # What changed?
git add file.py     # Stage a file for commit
git commit -m "..."  # Save a checkpoint
git push            # Upload to GitHub
git pull            # Download latest from GitHub
git log --oneline   # See history
git diff            # See what changed line by line
```

**Your PULSE history:**
```
2eb7e44  feat: 13-provider notification engine, escalation, MCP server
4fac3fa  feat: Azure/GCP collectors + Topology/Logs/KB dashboard views
1e49c2f  feat: full observability — correlation, KB, SDK, K8s, cloud, remediation
3e93eaa  feat: initial PULSE platform — universal monitoring + AI RCA
```

Each commit is a save point you can always go back to.

---

## 7. Networking Basics

**Ports** — Think of them as doors on a building. Each service listens on a different port:
- PostgreSQL: 5432
- Redis: 6379
- PULSE API: 8000
- Your browser: 8001 (mapped to 8000)

**HTTP Methods:**
- `GET` = read data (give me the list of nodes)
- `POST` = send/create data (here are new metrics)
- `DELETE` = remove data (delete this maintenance window)

**WebSocket** — Normal HTTP is request-response (you ask, server answers). WebSocket keeps a persistent connection open — server can push data to you anytime. That's how your dashboard updates in real-time without refreshing.

**SNMP** — Protocol for talking to network devices (routers, switches). You send "what's your CPU usage?" and the device responds. PULSE polls devices every 10 seconds this way.

**SNMP v2c vs v3:**
- **v2c** — Uses a "community string" (basically a password in plain text). Fine for labs, NOT for production.
- **v3** — Adds real security: username authentication (SHA/MD5) + encryption (AES/DES). Required by enterprise/government compliance standards. PULSE supports both.

```bash
# v2c (simple, insecure)
SNMP_VERSION=2c
SNMP_COMMUNITY=public

# v3 (secure — use this in production)
SNMP_VERSION=3
SNMP_V3_USER=pulseMonitor
SNMP_V3_AUTH_KEY=MyAuthPass123
SNMP_V3_PRIV_KEY=MyPrivPass456
SNMP_V3_AUTH_PROTO=SHA          # authentication hash
SNMP_V3_PRIV_PROTO=AES          # encryption algorithm
SNMP_V3_SECURITY_LEVEL=authPriv # full auth + encryption
```

---

## 8. What DevOps Actually Means

It's not a tool. It's the practice of:

1. **Writing code** (Dev)
2. **Deploying and running it reliably** (Ops)
3. **Automating everything in between**

```
Code → Build → Test → Deploy → Monitor → Alert → Fix → Repeat
         ↑                                              |
         └──────────────────────────────────────────────┘
```

PULSE sits in the **Monitor → Alert → Fix** part. But a DevOps engineer handles the ENTIRE pipeline.

**What you'd learn next to complete the picture:**

| Skill | What It Does | PULSE Example |
|---|---|---|
| **Kubernetes** | Runs containers at scale, self-heals | Deploy PULSE on K8s instead of docker-compose |
| **Terraform** | Creates cloud infrastructure with code | Provision Azure VMs + database for PULSE |
| **CI/CD** | Auto-test and deploy on every git push | GitHub Actions pipeline for PULSE |
| **Helm** | Package K8s apps for easy install | `helm install pulse` — one command |

---

## 9. Kubernetes — Production-Grade Deployment

**Problem with Docker Compose:** Runs containers on ONE machine. If that machine dies, everything dies. No auto-scaling, no self-healing, no rolling updates.

**Kubernetes (K8s) solves this:** It's a container orchestrator — manages containers across multiple machines, auto-heals crashes, scales up/down, and deploys with zero downtime.

### Docker Compose vs Kubernetes

| Feature | Docker Compose | Kubernetes |
|---|---|---|
| Runs on | 1 machine | Cluster of machines |
| Container crashes | Stays dead until you restart | Auto-restarts in seconds |
| Deploy new version | Stop old, start new (downtime) | Rolling update (zero downtime) |
| Scale | Manual `replicas: 3` then recreate | `kubectl scale` — instant |
| Load balancing | None built-in | Built-in via Services |
| Health checks | Basic | Full liveness + readiness probes |

### How PULSE Runs on K8s

We use **minikube** — a local single-node K8s cluster that runs inside Docker. In production, you'd use EKS (AWS), AKS (Azure), or GKE (Google).

```
Your Mac
  └── Docker Desktop
        └── minikube (K8s cluster)
              └── pulse namespace
                    ├── postgres (1 pod + persistent disk)
                    ├── redis (1 pod)
                    ├── pulse-api (2 pods — high availability)
                    └── pulse-agent (1 pod per node — DaemonSet)
```

### K8s Objects — What Each One Does

**Namespace** (`k8s/namespace.yaml`) — A folder for your app. Keeps PULSE resources separate from other apps in the cluster.
```bash
kubectl get all -n pulse    # Only see PULSE stuff
```

**Deployment** (`k8s/api.yaml`, `k8s/postgres.yaml`, `k8s/redis.yaml`) — Tells K8s "keep N copies of this container running." If one crashes, K8s auto-creates a replacement.
```yaml
replicas: 2    # Always keep 2 API pods running
```

**DaemonSet** (`k8s/agent.yaml`) — Like Deployment, but runs exactly ONE copy on EVERY node. Perfect for monitoring agents — when you add a server to the cluster, K8s auto-deploys the agent there.

**Service** — Gives pods a stable network address. Pod IPs change on restart, but Service name stays the same.
```
pulse-api:8000    → routes to whichever API pod is healthy
postgres:5432     → routes to the database pod
redis:6379        → routes to the cache pod
```

**Secret** (`k8s/secrets.yaml`) — Stores sensitive data (passwords, API keys) separately from code. Base64-encoded, not visible in YAML manifests you'd share.

**ConfigMap** (`k8s/configmap.yaml`) — Non-secret config (env vars, config files). Can be mounted as files or injected as environment variables.

**PersistentVolumeClaim** (`k8s/postgres.yaml`) — Reserves disk space that survives pod restarts. Without this, database data disappears when postgres restarts.

### Rolling Updates — Zero Downtime Deploys

When you update PULSE, K8s doesn't stop everything and restart. It:

```
1. Start 1 NEW pod with new code          [old1] [old2] [new1]
2. Wait until new pod passes health check  [old1] [old2] [new1 OK]
3. Kill 1 OLD pod                          [old1] [new1]
4. Start another NEW pod                   [old1] [new1] [new2]
5. Wait for health check                   [old1] [new1] [new2 OK]
6. Kill last OLD pod                       [new1] [new2]
```

Users never see downtime. This is configured in `api.yaml`:
```yaml
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxSurge: 1          # Add 1 extra during update
    maxUnavailable: 0    # Never have 0 running
```

### Health Probes — Auto-Healing

K8s constantly checks if your app is actually working:

- **readinessProbe** — "Is this pod ready to receive traffic?" If no, K8s stops sending requests to it.
- **livenessProbe** — "Is this pod alive?" If no, K8s kills and restarts it.

```yaml
readinessProbe:
  httpGet:
    path: /api/stats     # K8s hits this endpoint
    port: 8000
  periodSeconds: 10      # Every 10 seconds
```

If your API freezes (deadlock, memory leak), K8s detects it via the probe and restarts the pod automatically. No human intervention needed.

### K8s Commands You Should Know

```bash
# Cluster status
minikube status                          # Is the cluster running?
kubectl get pods -n pulse                # What pods are running?
kubectl get svc -n pulse                 # What services exist?

# Debugging
kubectl logs deployment/pulse-api -n pulse        # See API logs
kubectl describe pod <pod-name> -n pulse           # Why is a pod failing?
kubectl exec -n pulse deployment/pulse-api -- ls   # Run command inside pod

# Scaling
kubectl scale deployment/pulse-api -n pulse --replicas=3   # Scale to 3 copies

# Updates
kubectl rollout restart deployment/pulse-api -n pulse      # Redeploy with new image
kubectl rollout status deployment/pulse-api -n pulse       # Watch the rollout

# Access from browser (minikube on Mac)
minikube service pulse-api -n pulse --url                   # Get the URL

# Nuclear options (careful!)
kubectl delete pod <name> -n pulse       # Kill a pod (K8s auto-recreates)
kubectl delete namespace pulse           # Delete EVERYTHING in PULSE
```

### How We Deploy Updates to K8s

```bash
# 1. Rebuild the Docker image
docker build -f api/Dockerfile -t pulse-api:latest .

# 2. Load into minikube (because minikube can't pull from local Docker)
docker save -o /tmp/pulse-api.tar pulse-api:latest
minikube image load /tmp/pulse-api.tar

# 3. Restart the deployment (picks up new image)
kubectl rollout restart deployment/pulse-api -n pulse

# 4. Watch it roll out
kubectl rollout status deployment/pulse-api -n pulse
```

---

## 10. Your PULSE File Map

```
pulse/
├── api/
│   ├── main.py           ← API brain — all endpoints, WebSocket, incident flow
│   ├── db.py             ← Database tables and connection
│   ├── detection.py      ← Rules engine — evaluates YAML rules against metrics
│   ├── rca.py            ← AI root cause analysis (GPT-4o / Ollama)
│   ├── router.py         ← Team routing + notification dispatch
│   ├── notifications.py  ← 13 notification providers
│   ├── escalation.py     ← Auto-escalation + maintenance windows
│   ├── correlate.py      ← Groups related alerts together
│   ├── topology.py       ← Service dependency mapping
│   ├── remediate.py      ← Auto-fix playbooks (restart services, etc.)
│   ├── knowledge.py      ← Knowledge base for RCA context
│   ├── synthetic.py      ← HTTP health checks + SSL cert monitoring
│   ├── dbmonitor.py      ← PostgreSQL/Redis query-level monitoring
│   ├── anomaly.py        ← Z-score baseline anomaly detection
│   └── otel.py           ← OpenTelemetry OTLP receiver
├── agent/
│   └── collector.py      ← Runs on each server, collects metrics, sends to API
├── config/
│   ├── rules.yaml        ← Detection rules (when to fire alerts)
│   ├── teams.yaml        ← Team definitions + notification channels
│   ├── escalation.yaml   ← Escalation policies
│   ├── maintenance.yaml  ← Maintenance windows
│   ├── synthetic.yaml    ← URL/API monitoring targets
│   └── databases.yaml    ← Database monitoring targets
├── dashboard/
│   └── index.html        ← Real-time web dashboard
├── mcp/
│   └── pulse_mcp.py      ← MCP server (Claude can query PULSE)
├── k8s/
│   ├── namespace.yaml    ← Creates "pulse" namespace
│   ├── secrets.yaml      ← Passwords and API keys (base64-encoded)
│   ├── configmap.yaml    ← Non-secret env vars
│   ├── postgres.yaml     ← Database: PVC + Deployment + Service
│   ├── redis.yaml        ← Cache: Deployment + Service
│   ├── api.yaml          ← API: Deployment (2 replicas) + NodePort Service
│   ├── agent.yaml        ← Agent: DaemonSet (1 per node)
│   └── rbac.yaml         ← ServiceAccount + permissions for K8s API access
├── docker-compose.yml    ← Dev environment (ties containers together)
├── .env                  ← Your secrets (API keys, passwords) — NEVER commit this
└── .env.example          ← Template showing what secrets are needed
```

---

## 11. Phase 2 — Observability Pillars

### Synthetic Monitoring (`api/synthetic.py`)

**What it does:** Probes URLs/APIs on a schedule to check if they're up, fast, and have valid SSL certs.

**Why it matters:** Your users shouldn't be the first to know your site is down. Synthetic checks catch outages before users do.

```yaml
# config/synthetic.yaml
targets:
  - id: company-api
    url: https://api.example.com/health
    interval_seconds: 30
    expected_status: 200
    check_ssl: true
    ssl_warn_days: 14    # Alert 2 weeks before cert expires
```

PULSE checks each target and generates events for: timeouts, wrong status codes, slow responses, and expiring SSL certs.

### Database Monitoring (`api/dbmonitor.py`)

**What it does:** Connects to PostgreSQL and Redis, collects query performance, connection counts, cache stats, and replication lag.

**Why it matters:** "The app is slow" is often "the database is slow." You need to see inside the database to find the bottleneck.

Key metrics collected:
- **PostgreSQL:** active connections, slow queries, cache hit ratio, table sizes, dead tuples, replication lag
- **Redis:** memory usage, connected clients, evicted keys, hit rate, ops/second

### Anomaly Detection (`api/anomaly.py`)

**What it does:** Learns what "normal" looks like for each metric on each server, then alerts when values deviate significantly.

**How it works — Z-Score:**
```
1. Collect 30+ data points (baseline)
2. Calculate mean and standard deviation
3. For each new value: z-score = (value - mean) / std_dev
4. If |z-score| > 3 → anomaly alert
```

**Example:** CPU normally at 20% (std=5%). A spike to 55% has z-score = (55-20)/5 = 7 → anomaly.

Static threshold (e.g., alert at 95%) would miss this. Anomaly detection catches it because 55% is abnormal *for this server*.

### OpenTelemetry (`api/otel.py`)

**What it is:** The industry standard for instrumenting applications. Any app using OpenTelemetry can send metrics, traces, and logs to PULSE.

**Why it matters:** Instead of writing custom integrations for every language/framework, apps just use the OTel SDK and point it at PULSE. One protocol, every language.

**Endpoints:**
```
POST /v1/traces   → App sends distributed traces (spans)
POST /v1/metrics  → App sends custom metrics
POST /v1/logs     → App sends structured logs
```

**The Three Pillars of Observability:**
```
Metrics  → "What is happening?" (CPU at 95%, response time 500ms)
Logs     → "What happened?" (error messages, debug output)
Traces   → "Where did it happen?" (request flow across services)
```

PULSE now has all three. This is what makes it a complete observability platform, not just a monitoring tool.

---

## 12. One-Liners to Remember

```bash
# "Is PULSE alive?"
curl -s http://localhost:8001/api/stats | python3 -m json.tool

# "What's being monitored?"
curl -s http://localhost:8001/api/nodes | python3 -m json.tool

# "Any problems?"
curl -s http://localhost:8001/api/alerts?limit=5 | python3 -m json.tool

# "Test my Telegram notifications"
curl -s -X POST http://localhost:8001/api/notifications/test \
  -H "Content-Type: application/json" \
  -d '{"provider":"telegram","target":"982892344","message":"Test!"}'

# "Rebuild after code changes"
docker compose build api && docker compose up -d api

# "What did I change?"
git diff

# "Save and push my work"
git add -A && git commit -m "description" && git push
```
