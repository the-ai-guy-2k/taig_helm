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

import hashlib
import ipaddress
import json
import os
import re
import secrets
import subprocess
import sys
import time
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

# Preview tokens: single-use, 10-minute expiry, in-memory only.
# An apply without a fresh preview token is rejected — this is the
# preview-approve gate, enforced server-side, not just a GUI button.
PREVIEW_TOKENS = {}


def make_preview_token(payload):
    token = secrets.token_hex(16)
    PREVIEW_TOKENS[token] = {"payload": payload, "expires": time.time() + 600}
    return token


def take_preview_token(token):
    entry = PREVIEW_TOKENS.pop(token, None)
    if not entry or entry["expires"] < time.time():
        return None
    return entry["payload"]


def validate_firewall_payload(body):
    """Mirror the agent's validation, on the laptop, before any send."""
    if not isinstance(body, dict):
        return None, "payload must be an object"
    op = body.get("op")
    if op not in ("add", "remove"):
        return None, "op must be add or remove"
    action = body.get("action")
    protocol = body.get("protocol")
    try:
        port = int(body.get("port"))
    except Exception:
        return None, "port must be a number"
    source = body.get("source", "any")
    if action not in ("allow", "deny"):
        return None, "action must be allow or deny"
    if protocol not in ("tcp", "udp"):
        return None, "protocol must be tcp or udp"
    if not 1 <= port <= 65535:
        return None, "port must be 1-65535"
    if action == "deny" and port == 22:
        return None, "refused: deny on SSH port 22 would lock out the box"
    if source in ("any", "0.0.0.0/0", "::/0"):
        source_norm = "0.0.0.0/0"
    else:
        try:
            source_norm = str(ipaddress.ip_network(source, strict=False))
        except Exception:
            return None, "source must be an IP/CIDR or 'any'"
    payload = {"op": op, "action": action, "protocol": protocol,
               "port": port, "source": source_norm}
    return payload, None


SERVICE_NAMES = {
    22: "SSH", 80: "Web", 443: "Secure web", 53: "DNS",
    3000: "TAIG Service Portal", 3002: "TAIG Speed", 8003: "PIA",
}


def service_name(port):
    return SERVICE_NAMES.get(port, f"Port {port}")


def firewall_safety_checks(payload, current_rules):
    """Plain-language checks, no chain names, no rule order, no syntax.
    If Firewall is not intuitive, it fails its own requirement, even
    if the rules are technically correct (Tee, Nov 4, 6:40 PM EST)."""
    checks = []
    if payload["port"] == 22 and payload["action"] == "allow":
        checks.append("Port 22 is SSH — this is an allow, not a block, "
                      "so it does not lock you out.")
    checks.append("This only changes Helm's own rules for this box. "
                  "It never touches Docker's own rules.")
    checks.append("You do not need to know rule order — Helm puts the "
                  "rule where it belongs. No position to pick.")
    checks.append("Runtime rule only — it does NOT survive a reboot "
                  "until the persistence decision in main chat is made.")
    if payload["op"] == "remove":
        checks.append("Remove only works for rules Helm created. "
                      "Rules from anything else are never removed.")
    return checks

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


def run_firewall_ssh(cfg, subcommand, payload=None):
    """Run ONE fixed firewall command over SSH. payload fields are
    validated before this point, and quoted as single args — no shell."""
    if subcommand == "list":
        remote = f"python3 {cfg['agent_path']} firewall list"
    elif subcommand in ("add", "remove"):
        remote = (f"python3 {cfg['agent_path']} firewall {subcommand} "
                  f"--action {payload['action']} "
                  f"--protocol {payload['protocol']} "
                  f"--port {payload['port']} "
                  f"--source {payload['source']}")
    else:
        raise ValueError("unknown firewall subcommand")
    key = os.path.expanduser(cfg["ssh_key"])
    ssh_cmd = ["ssh", "-i", key, "-o", "BatchMode=yes",
               "-o", "ConnectTimeout=10",
               f"{cfg['ssh_user']}@{cfg['droplet_host']}", remote]
    start = time.time()
    proc = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=30)
    duration_ms = int((time.time() - start) * 1000)
    log_ssh(remote, proc.returncode, duration_ms, "")
    if proc.returncode != 0:
        raise RuntimeError(f"ssh/firewall failed rc={proc.returncode}: "
                           f"{proc.stderr.strip()[:300]}")
    return json.loads(proc.stdout)


def mock_firewall():
    return {
        "input_policy": "ACCEPT",
        "rules": [
            {"chain": "INPUT", "action": "allow", "protocol": "tcp",
             "port": 80, "service": "Web", "source": "0.0.0.0/0",
             "helm_managed": True,
             "raw": "-A INPUT -p tcp --dport 80 -m comment --comment taig-helm -j ACCEPT"},
        ],
        "listening_ports": [{"proto": "tcp", "local": "0.0.0.0:22"},
                            {"proto": "tcp", "local": "0.0.0.0:3002"}],
        "persistent_note": "MOCK — runtime rules only, persistence open.",
        "guards": ["never deny SSH port 22", "never touch DOCKER chains"],
    }


def run_updates_ssh(cfg, subcommand, payload=None):
    if subcommand == "check":
        remote = f"python3 {cfg['agent_path']} updates check"
    elif subcommand == "apply":
        if payload["scope"] == "whole":
            remote = f"python3 {cfg['agent_path']} updates apply --scope whole"
        else:
            remote = (f"python3 {cfg['agent_path']} updates apply "
                      f"--scope one --package {payload['package']}")
    else:
        raise ValueError("unknown updates subcommand")
    key = os.path.expanduser(cfg["ssh_key"])
    ssh_cmd = ["ssh", "-i", key, "-o", "BatchMode=yes",
               "-o", "ConnectTimeout=10",
               f"{cfg['ssh_user']}@{cfg['droplet_host']}", remote]
    start = time.time()
    proc = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=960)
    duration_ms = int((time.time() - start) * 1000)
    log_ssh(remote, proc.returncode, duration_ms, "")
    if proc.returncode != 0:
        raise RuntimeError(f"ssh/updates failed rc={proc.returncode}: "
                           f"{proc.stderr.strip()[-500:]}")
    return json.loads(proc.stdout)


def validate_updates_payload(body):
    if not isinstance(body, dict):
        return None, "payload must be an object"
    scope = body.get("scope")
    if scope not in ("whole", "one"):
        return None, "scope must be whole or one"
    package = body.get("package")
    if scope == "one":
        if not package or not re.match(r"^[a-z0-9][a-z0-9+.\-]*$", package):
            return None, "package name is not valid"
    else:
        package = None
    return {"kind": "updates", "scope": scope, "package": package}, None


def mock_updates():
    pkgs = [
        {"name": "apt", "current": "2.8.3", "new": "2.8.4ubuntu0.1", "security": True},
        {"name": "apt-utils", "current": "2.8.3", "new": "2.8.4ubuntu0.1", "security": True},
        {"name": "libapt-pkg", "current": "2.8.3", "new": "2.8.4ubuntu0.1", "security": True},
        {"name": "cloud-init", "current": "24.1", "new": "24.2", "security": False},
        {"name": "python3-twisted", "current": "22.1", "new": "22.2", "security": True},
        {"name": "tmux", "current": "3.3a-1", "new": "3.3a-1ubuntu0.1", "security": False},
        {"name": "ubuntu-pro-client", "current": "32.1", "new": "32.2", "security": False},
    ]
    return {"count": len(pkgs), "packages": pkgs,
            "unattended_upgrades_active": True,
            "note": "MOCK — example list only, not the live Droplet list. "
                    "Run live for the real 13-package list."}


def run_logs_ssh(cfg, subcommand, payload=None):
    if subcommand == "list":
        remote = f"python3 {cfg['agent_path']} logs list"
    elif subcommand == "read":
        remote = (f"python3 {cfg['agent_path']} logs read "
                  f"--service {payload['service']} "
                  f"--lines {payload['lines']}")
        if payload.get("search"):
            remote += f" --search {payload['search']}"
        if payload.get("since_hours"):
            remote += f" --since-hours {payload['since_hours']}"
    else:
        raise ValueError("unknown logs subcommand")
    key = os.path.expanduser(cfg["ssh_key"])
    ssh_cmd = ["ssh", "-i", key, "-o", "BatchMode=yes",
               "-o", "ConnectTimeout=10",
               f"{cfg['ssh_user']}@{cfg['droplet_host']}", remote]
    start = time.time()
    proc = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=120)
    duration_ms = int((time.time() - start) * 1000)
    log_ssh(remote, proc.returncode, duration_ms, "")
    if proc.returncode != 0:
        raise RuntimeError(f"ssh/logs failed rc={proc.returncode}: "
                           f"{proc.stderr.strip()[-500:]}")
    return json.loads(proc.stdout)


def validate_logs_payload(body):
    if not isinstance(body, dict):
        return None, "payload must be an object"
    service = body.get("service")
    if not service or not re.match(r"^[a-z0-9\-]+$", service):
        return None, "service must be a plain log name from the list"
    try:
        lines = int(body.get("lines", 100))
    except Exception:
        return None, "lines must be a number"
    if not 1 <= lines <= 500:
        return None, "lines must be 1-500"
    search = body.get("search") or None
    if search and (len(search) > 100
                   or not re.match(r"^[A-Za-z0-9 _\-./:]+$", search)):
        return None, "search must be plain words/numbers, no shell characters"
    since = body.get("since_hours")
    if since in (None, "", "all"):
        since_hours = None
    else:
        try:
            since_hours = int(since)
        except Exception:
            return None, "time filter must be last hour, last day, last 7 days, or all"
        if since_hours not in (1, 24, 168):
            return None, "time filter must be last hour, last day, last 7 days, or all"
    return {"service": service, "lines": lines, "search": search,
            "since_hours": since_hours}, None


def mock_logs():
    sources = [
        {"key": "system", "name": "System log", "kind": "file",
         "description": "The box's main system log.", "exists": True, "size_bytes": 1800000},
        {"key": "signins", "name": "Sign-ins", "kind": "file",
         "description": "Who signed in.", "exists": True, "size_bytes": 1000000},
        {"key": "helm-agent", "name": "TAIG Helm agent", "kind": "file",
         "description": "Helm agent's own log.", "exists": True, "size_bytes": 108000},
        {"key": "website-visits", "name": "Website visits", "kind": "file",
         "description": "Visits to the web server.", "exists": True, "size_bytes": 124000},
        {"key": "pia", "name": "PIA", "kind": "docker",
         "description": "PIA app.", "exists": True},
        {"key": "nope-portal", "name": "Nope portal", "kind": "docker",
         "description": "Nope operator portal.", "exists": True},
        {"key": "taig-speed", "name": "TAIG Speed", "kind": "docker",
         "description": "TAIG Speed inventory service.", "exists": True},
        {"key": "tsp", "name": "TAIG Service Portal", "kind": "docker",
         "description": "TAIG Service Portal (TSP) service.", "exists": True},
    ]
    return {"sources": sources,
            "note": "MOCK — example list only, not the live Droplet list."}


def mock_logs_read(payload):
    # Mock mirrors the live allowlist: unknown service is refused here too.
    known = {s["key"]: s["name"] for s in mock_logs()["sources"]}
    if payload["service"] not in known:
        raise ValueError(f"unknown log service: {payload['service']!r}")
    lines = [
        "Nov  4 19:17:37 droplet sshd[123]: Accepted publickey for root",
        "Nov  4 19:17:38 droplet systemd[1]: Started TAIG Helm status writer.",
        "Nov  4 19:18:02 droplet nginx: GET / 200",
    ]
    if payload.get("search"):
        needle = payload["search"].lower()
        lines = [l for l in lines if needle in l.lower()]
    lines = lines[-payload["lines"]:]
    return {"service": payload["service"],
            "name": known[payload["service"]], "kind": "mock",
            "lines": lines, "total_matched": len(lines),
            "returned": len(lines), "search": payload.get("search"),
            "since_hours": payload.get("since_hours"),
            "note": "MOCK — example lines only, not live Droplet lines."}


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
        elif path == "/api/firewall":
            self.handle_firewall_read()
        elif path == "/api/updates":
            self.handle_updates_read()
        elif path == "/api/logs":
            self.handle_logs_list()
        else:
            super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except Exception:
            return self.send_json({"error": "body must be JSON"}, status=400)
        if path == "/api/firewall/preview":
            return self.handle_firewall_preview(body)
        if path == "/api/firewall/apply":
            return self.handle_firewall_apply(body)
        if path == "/api/updates/preview":
            return self.handle_updates_preview(body)
        if path == "/api/updates/apply":
            return self.handle_updates_apply(body)
        if path == "/api/logs/read":
            return self.handle_logs_read(body)
        return self.send_json({"error": "unknown endpoint"}, status=404)

    def handle_logs_list(self):
        if os.environ.get("HELM_MOCK") == "1":
            return self.send_json({"data": mock_logs(),
                                   "meta": {"source": "mock"}})
        try:
            cfg = load_config()
            data = run_logs_ssh(cfg, "list")
        except Exception as exc:
            return self.send_json({"error": str(exc)}, status=502)
        return self.send_json({"data": data, "meta": {"source": "live"}})

    def handle_logs_read(self, body):
        payload, err = validate_logs_payload(body)
        if err:
            return self.send_json({"error": err}, status=400)
        # Read-only: no preview token, no apply endpoint exists for Logs.
        if os.environ.get("HELM_MOCK") == "1":
            try:
                data = mock_logs_read(payload)
            except Exception as exc:
                return self.send_json({"error": str(exc)}, status=400)
            return self.send_json({"data": data,
                                   "meta": {"source": "mock"}})
        try:
            cfg = load_config()
            data = run_logs_ssh(cfg, "read", payload)
        except Exception as exc:
            return self.send_json({"error": str(exc)}, status=502)
        return self.send_json({"data": data, "meta": {"source": "live"}})

    def handle_updates_read(self):
        if os.environ.get("HELM_MOCK") == "1":
            return self.send_json({"data": mock_updates(),
                                   "meta": {"source": "mock"}})
        try:
            cfg = load_config()
            data = run_updates_ssh(cfg, "check")
        except Exception as exc:
            return self.send_json({"error": str(exc)}, status=502)
        return self.send_json({"data": data, "meta": {"source": "live"}})

    def handle_updates_preview(self, body):
        payload, err = validate_updates_payload(body)
        if err:
            return self.send_json({"error": err}, status=400)
        # Preview does NOT install anything. Current list, best-effort,
        # for plain-words preview text with versions, e.g.
        # "Update tmux from 3.3a-1 to 3.3a-1ubuntu0.1."
        current_list = []
        if os.environ.get("HELM_MOCK") == "1":
            current_list = mock_updates()["packages"]
        else:
            try:
                current_list = run_updates_ssh(load_config(), "check")["packages"]
            except Exception:
                current_list = []
        if payload["scope"] == "whole":
            effect = (f"Update the whole box — all {len(current_list)} "
                      f"package(s) in the list above.")
            detail = "Whole-box update: apt upgrade only, never a release upgrade, never Docker."
        else:
            match = next((p for p in current_list
                          if p["name"] == payload["package"]), None)
            if match:
                effect = (f"Update {match['name']} from {match['current']} "
                          f"to {match['new']}.")
            else:
                effect = f"Update just one package: {payload['package']}."
            detail = "One-package update only. Nothing else in the list changes."
        token = make_preview_token(payload)
        return self.send_json({
            "payload": payload, "preview_token": token,
            "effect": effect, "detail": detail,
            "safety_checks": [
                "Nothing is installed yet — this is preview only.",
                "No auto-apply. You approve, then it sends.",
                "No release upgrade, no Docker changes — apt packages only.",
                "After apply, the laptop re-reads the update list to verify.",
            ],
            "note": "Nothing has been sent yet. Approve to send this exact choice.",
        })

    def handle_updates_apply(self, body):
        payload = take_preview_token(body.get("preview_token", ""))
        if payload is None or payload.get("kind") != "updates":
            return self.send_json(
                {"error": "preview token missing, expired, or already used — "
                          "preview the update again before applying"}, status=400)
        if os.environ.get("HELM_MOCK") == "1":
            return self.send_json({
                "applied": True, "source": "mock", "payload": payload,
                "verification": {"method": "mock re-read (not live)",
                                 "note": "MOCK ONLY — run live for real verification"},
            })
        try:
            cfg = load_config()
            result = run_updates_ssh(cfg, "apply", payload)
            verified = run_updates_ssh(cfg, "check")
            remaining = [p["name"] for p in verified.get("packages", [])]
            if payload["scope"] == "whole":
                verified_ok = len(remaining) == 0
                verify_text = f"{len(remaining)} packages still listed after whole-box update."
            else:
                verified_ok = payload["package"] not in remaining
                verify_text = (f"{payload['package']} is no longer in the list."
                               if verified_ok else
                               f"{payload['package']} is still in the list.")
            verification = {"method": "state re-read (updates check)",
                            "verified": verified_ok,
                            "remaining_packages": remaining,
                            "text": verify_text}
        except Exception as exc:
            return self.send_json({"error": str(exc)}, status=502)
        return self.send_json({
            "applied": result, "verification": verification,
            "meta": {"source": "live",
                     "note": "Verification is the re-read above, not the agent exit code."},
        })

    def handle_firewall_read(self):
        if os.environ.get("HELM_MOCK") == "1":
            return self.send_json({"data": mock_firewall(),
                                   "meta": {"source": "mock"}})
        try:
            cfg = load_config()
            data = run_firewall_ssh(cfg, "list")
            for r in data.get("rules", []):
                if isinstance(r.get("port"), int):
                    r["service"] = service_name(r["port"])
        except Exception as exc:
            return self.send_json({"error": str(exc)}, status=502)
        return self.send_json({"data": data, "meta": {"source": "live"}})

    def handle_firewall_preview(self, body):
        payload, err = validate_firewall_payload(body)
        if err:
            return self.send_json({"error": err}, status=400)
        # Preview does NOT send anything. It shows the payload + checks.
        # Current rules are read for duplicate context, best-effort.
        current = []
        if os.environ.get("HELM_MOCK") == "1":
            current = mock_firewall()["rules"]
        else:
            try:
                current = run_firewall_ssh(load_config(), "list")["rules"]
            except Exception:
                current = []
        token = make_preview_token(payload)
        # Intuitive first: plain words, no iptables syntax required.
        # Technical detail is kept, but second, not as the headline.
        verb = "Allow" if payload["action"] == "allow" else "Block"
        whom = ("from anywhere" if payload["source"] == "0.0.0.0/0"
                else f"only from {payload['source']}")
        svc = service_name(payload["port"])
        plain = (f"{'Add' if payload['op'] == 'add' else 'Remove'}: "
                 f"{verb} {svc} ({payload['protocol'].upper()} "
                 f"port {payload['port']}) {whom}.")
        return self.send_json({
            "payload": payload,
            "preview_token": token,
            "safety_checks": firewall_safety_checks(payload, current),
            "effect": plain,
            "technical": (f"Technical: {payload['op']} INPUT rule, "
                          f"{payload['action']} {payload['protocol']} "
                          f"port {payload['port']} from {payload['source']}, "
                          f"comment taig-helm, INPUT only."),
            "note": "Nothing has been sent yet. Approve to send this exact payload.",
        })

    def handle_firewall_apply(self, body):
        payload = take_preview_token(body.get("preview_token", ""))
        if payload is None or payload.get("kind") == "updates":
            return self.send_json(
                {"error": "preview token missing, expired, or already used — "
                          "preview the rule again before applying"}, status=400)
        if os.environ.get("HELM_MOCK") == "1":
            return self.send_json({
                "applied": True, "source": "mock",
                "payload": payload,
                "verification": {"method": "mock re-read (not live)",
                                 "note": "MOCK ONLY — run live for real verification"},
            })
        try:
            cfg = load_config()
            result = run_firewall_ssh(cfg, payload["op"], payload)
            # Verification, on the laptop, by RE-READING rules — never
            # exit code alone. The apply result above is not proof.
            verified = run_firewall_ssh(cfg, "list")
            found = any(
                r.get("action") == payload["action"]
                and r.get("protocol") == payload["protocol"]
                and r.get("port") == payload["port"]
                for r in verified.get("rules", []))
            expected = payload["op"] == "add"
            verification = {
                "method": "state re-read (firewall list)",
                "expected_present": expected,
                "found_present": found,
                "verified": found == expected,
            }
        except Exception as exc:
            return self.send_json({"error": str(exc)}, status=502)
        return self.send_json({
            "applied": result, "verification": verification,
            "meta": {"source": "live",
                     "note": "Verification is the re-read above, not the agent exit code."},
        })

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
