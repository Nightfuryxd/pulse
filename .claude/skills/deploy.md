---
name: deploy
description: Rebuild and restart PULSE — rebuilds API container and verifies it's healthy
user_invocable: true
---

Rebuild and restart the PULSE platform:

1. Run `cd /Users/aniketgupta/Desktop/Claude/pulse && docker compose build api` to rebuild
2. Run `docker compose up -d api` to restart
3. Wait 3 seconds, then check `docker compose logs api --tail 10` for errors
4. Run `curl -s http://localhost:8001/api/stats` to verify API is healthy
5. Report: build status, startup logs, health check result
