"""
PULSE MCP Server — Model Context Protocol server that lets Claude
query PULSE monitoring data directly.

Tools exposed:
  - pulse_status: Get platform stats (nodes, alerts, incidents)
  - pulse_nodes: List all monitored nodes with health
  - pulse_alerts: Get recent alerts with severity filter
  - pulse_incidents: Get incidents with RCA details
  - pulse_events: Get security/system events
  - pulse_maintenance: List active maintenance windows
  - pulse_providers: Check notification provider status
  - pulse_test_notify: Send a test notification
"""
import json
import httpx
import sys

# MCP protocol via stdio
PULSE_API = "http://localhost:8001"


def call_pulse(path: str, method: str = "GET", body: dict = None) -> dict:
    """Synchronous call to PULSE API."""
    try:
        with httpx.Client(timeout=10) as client:
            if method == "GET":
                resp = client.get(f"{PULSE_API}{path}")
            else:
                resp = client.post(f"{PULSE_API}{path}", json=body or {})
            return resp.json()
    except Exception as e:
        return {"error": str(e)}


# ── MCP Tool Definitions ─────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "pulse_status",
        "description": "Get PULSE platform stats: node count, open alerts, incidents, connected clients",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "pulse_nodes",
        "description": "List all monitored nodes with OS, IP, health status, and last seen time",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "pulse_alerts",
        "description": "Get recent alerts. Optionally filter by severity or node.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "severity": {"type": "string", "description": "Filter: critical, high, medium, low"},
                "node_id": {"type": "string", "description": "Filter by node ID"},
                "limit": {"type": "integer", "description": "Max results (default 20)", "default": 20},
            },
        },
    },
    {
        "name": "pulse_incidents",
        "description": "Get incidents with full AI root cause analysis, team routing, and remediation details",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 10},
                "status": {"type": "string", "description": "Filter: open, acknowledged, resolved"},
            },
        },
    },
    {
        "name": "pulse_events",
        "description": "Get security and system events (auth failures, port scans, OOM kills, etc.)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "description": "Event type filter"},
                "node_id": {"type": "string"},
                "limit": {"type": "integer", "default": 50},
            },
        },
    },
    {
        "name": "pulse_maintenance",
        "description": "List active maintenance windows that are suppressing alerts",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "pulse_providers",
        "description": "Check which notification providers are configured (Slack, Teams, Discord, Telegram, etc.)",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "pulse_test_notify",
        "description": "Send a test notification via a specific provider",
        "inputSchema": {
            "type": "object",
            "properties": {
                "provider": {"type": "string", "description": "Provider name: slack, teams, discord, telegram, email, sms, webhook, etc."},
                "target": {"type": "string", "description": "Target: channel, webhook URL, email, phone number, chat ID"},
                "message": {"type": "string", "description": "Optional custom message", "default": "PULSE MCP Test"},
            },
            "required": ["provider", "target"],
        },
    },
]


def handle_tool(name: str, args: dict) -> str:
    """Execute a tool and return the result as a string."""
    if name == "pulse_status":
        return json.dumps(call_pulse("/api/stats"), indent=2)

    elif name == "pulse_nodes":
        return json.dumps(call_pulse("/api/nodes"), indent=2)

    elif name == "pulse_alerts":
        params = []
        if args.get("severity"):
            params.append(f"severity={args['severity']}")
        if args.get("node_id"):
            params.append(f"node_id={args['node_id']}")
        params.append(f"limit={args.get('limit', 20)}")
        return json.dumps(call_pulse(f"/api/alerts?{'&'.join(params)}"), indent=2)

    elif name == "pulse_incidents":
        params = [f"limit={args.get('limit', 10)}"]
        if args.get("status"):
            params.append(f"status={args['status']}")
        return json.dumps(call_pulse(f"/api/incidents?{'&'.join(params)}"), indent=2)

    elif name == "pulse_events":
        params = [f"limit={args.get('limit', 50)}"]
        if args.get("type"):
            params.append(f"type={args['type']}")
        if args.get("node_id"):
            params.append(f"node_id={args['node_id']}")
        return json.dumps(call_pulse(f"/api/events?{'&'.join(params)}"), indent=2)

    elif name == "pulse_maintenance":
        return json.dumps(call_pulse("/api/maintenance"), indent=2)

    elif name == "pulse_providers":
        return json.dumps(call_pulse("/api/notifications/providers"), indent=2)

    elif name == "pulse_test_notify":
        body = {"provider": args["provider"], "target": args["target"]}
        if args.get("message"):
            body["message"] = args["message"]
        return json.dumps(call_pulse("/api/notifications/test", method="POST", body=body), indent=2)

    return json.dumps({"error": f"Unknown tool: {name}"})


# ── MCP stdio Protocol Handler ───────────────────────────────────────────────

def main():
    """MCP server running over stdio."""
    import sys

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        msg_id = msg.get("id")
        method = msg.get("method", "")

        if method == "initialize":
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "pulse-mcp", "version": "1.0.0"},
                },
            }
        elif method == "tools/list":
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": TOOLS},
            }
        elif method == "tools/call":
            tool_name = msg.get("params", {}).get("name", "")
            tool_args = msg.get("params", {}).get("arguments", {})
            result_text = handle_tool(tool_name, tool_args)
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": result_text}],
                },
            }
        elif method == "notifications/initialized":
            continue  # No response needed for notifications
        else:
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }

        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
