---
name: pulse-status
description: Quick health check of the entire PULSE platform
user_invocable: true
---

Check PULSE platform health:

1. Run `docker compose ps` from `/Users/aniketgupta/Desktop/Claude/pulse` to check container states
2. Run `curl -s http://localhost:8001/api/stats` to get platform stats
3. Run `curl -s http://localhost:8001/api/notifications/providers` to check notification config
4. Run `curl -s "http://localhost:8001/api/alerts?limit=3"` to check recent alerts
5. Run `curl -s http://localhost:8001/api/maintenance` to check maintenance windows
6. Check API logs: `docker compose logs api --tail 5`

Report a concise dashboard:
- Containers: running/stopped
- Nodes monitored: count
- Open alerts/incidents: count
- Notification providers: configured vs total
- Active maintenance windows: count
- Any errors in logs
