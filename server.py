#!/usr/bin/env python3
"""TAIG Helm — laptop local service. v1 proof: status dashboard only.

Web GUI (browser) -> this local service -> SSH -> Droplet agent.
The browser NEVER talks to the Droplet directly. The laptop is NOT
reachable from the internet, so there is NO push — the GUI polls this
service, this service polls the agent over SSH.

Stdlib only. No dependencies.

Safety, v1:
- Only FIXED remote commands are ever sent. The remote command is built
  from config (agent path) + an allow-listed subcommand, never from GUI
  input. No shell=True, no free-form shell strings from GUI to agent.
- Every SSH command sent is logged (see log_ssh). The log records the
  command template, exit code, and duration — never key contents.
- Verification lives HERE, on the laptop, not on the agent: for a
  read-only status call, verification is the fresh read itself. For a
  future change, verification MUST be a state re-read, NOT exit code
  alone. Exit code is recorded, it is never treated as proof.

API:
  GET /api/status       fresh agent status over SSH (or mock, see below)
  GET /api/status-file  agent status file, polled over SSH (cat, fixed path)
  GET /                 web GUI (web/index.html)

Mock mode (frontend demo ONLY, never the v1 proof):
  HELM_MOCK=1 python3 server.py
  Every response is then labeled "source": "mock". The v1 proof MUST run
  with mock OFF, against the real Droplet agent.

Config: copy config.example.json to config.json and fill in your
Droplet host, SSH user, SSH key path, and agent paths. config.json is
gitignored — do not commit it.
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

BASE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE, "web")
LOG_DIR = os.path.join(BASE, "logs")
LOG_FILE = os.path.join(LOG_DIR, "helm.log")

ALLOWED_COMMANDS = {"status", "write-status", "version"}
HOST_RE = re.compile(r"^[A-Za-z0-9._-]+$")
USER_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def load_config():
    path = os.path.join(BASE, "config.json")
    if not os.path.exists(path):
        raise SystemExit("config.json missing — copy config.example.json to "
                         "config.json and fill in your Droplet details.")
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    if not HOST_RE.match(cfg.get("droplet_host", "")):
        raise SystemExit("config droplet_host looks invalid")
    if not USER_RE.match(cfg.get("ssh_user", "")):
        raise SystemExit("config ssh_user looks invalid")
    agent_path = cfg.get("agent_path", "")
    if not agent_path.startswith("/") or ".." in agent_path:
        raise SystemExit("config agent_path must be an absolute path")
    return cfg


def log_ssh(remote_command, exit_code, duration_ms, note=""):
    """Log every command sent. Never log key contents, never log output
    bodies here — output length only. Full status JSON is the API reply,
    not the log."""
    os.makedirs(LOG_DIR, exist_ok=True)
    line = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "remote_command": remote_command,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "note": note,
    }
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n")


def run_agent(cfg, command, use_status_file=False):
    """Run ONE fixed agent command over SSH. command must be allow-listed.
    Returns (parsed_json, meta). Raises on SSH / JSON failure."""
    if command not in ALLOWED_COMMANDS:
        raise ValueError(f"command not allowed: {command!r}")
    if use_status_file:
        remote = f"cat {cfg['status_file_path']}"
    else:
        remote = f"python3 {cfg['agent_path']} {command}"
    key = os.path.expanduser(cfg["ssh_key"])
    ssh_cmd = [
        "ssh", "-i", key,
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=10",
        f"{cfg['ssh_user']}@{cfg['droplet_host']}",
        remote,
    ]
    start = time.time()
    try:
        proc = subprocess.run(ssh_cmd, capture_output=True, text=True,
                              timeout=30)
    except Exception as exc:
        log_ssh(remote, -1, int((time.time() - start) * 1000), str(exc))
        raise
    duration_ms = int((time.time() - start) * 1000)
    log_ssh(remote, proc.returncode, duration_ms,
            "stderr_truncated" if proc.stderr else "")
    if proc.returncode != 0:
        raise RuntimeError(f"ssh/agent failed rc={proc.returncode}: "
                           f"{proc.stderr.strip()[:300]}")
    try:
        data = json.loads(proc.stdout)
    except Exception as exc:
        raise RuntimeError(f"agent did not return JSON: {exc}") from exc
    meta = {
        "source": "live",
        "verified_by": "fresh_read",
        "ssh_exit_code": proc.returncode,
        "note": "v1 read-only: fresh read IS the verification. "
                "For future changes, verification must be a state "
                "re-read, not exit code alone.",
    }
    return data, meta


def mock_status():
    return {
        "agent": "taig_helm_agent",
        "version": "0.1.0",
        "hostname": "droplet-mock",
        "os": "mock",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": 86400,
        "load_avg": [0.5, 0.4, 0.3],
        "cpu_count": 2,
        "cpu_percent": 12.5,
        "memory": {"total": 2147483648, "used": 1073741824,
                   "free": 1073741824, "available": 1073741824,
                   "percent": 50.0},
        "storage": {"mount": "/", "total": 64424509440,
                    "used": 20000000000, "free": 44424509440,
                    "percent": 31.0},
        "disks": [{"mount": "/", "total": 64424509440,
                   "used": 20000000000, "free": 44424509440,
                   "percent": 31.0}],
    }, {"source": "mock", "verified_by": "none",
        "note": "MOCK ONLY — not the v1 proof. Run with HELM_MOCK unset "
                "for live Droplet data."}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def log_message(self, *args):
        pass  # keep stdout clean; SSH commands go to logs/helm.log

    def send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/status":
            self.handle_status(use_status_file=False)
        elif path == "/api/status-file":
            self.handle_status(use_status_file=True)
        else:
            super().do_GET()

    def handle_status(self, use_status_file):
        if os.environ.get("HELM_MOCK") == "1":
            data, meta = mock_status()
            return self.send_json({"data": data, "meta": meta})
        try:
            cfg = load_config()
            data, meta = run_agent(cfg, "status",
                                   use_status_file=use_status_file)
        except Exception as exc:
            return self.send_json({"error": str(exc)}, status=502)
        return self.send_json({"data": data, "meta": meta})


def main():
    port = int(os.environ.get("HELM_PORT", "8080"))
    # Localhost only. This service is not internet-facing.
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"TAIG Helm local service on http://127.0.0.1:{port}/")
    print("Open that URL in a browser. Ctrl+C to stop (dev mode).")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
