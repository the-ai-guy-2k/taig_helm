# TAIG Helm — laptop side

Web GUI in a browser + a local service on the laptop that stays running.
That local service is the laptop-side counterpart to the Droplet agent.

Path, v1: Web GUI -> local service -> SSH -> Droplet agent -> box systems.
- The browser NEVER talks to the Droplet directly.
- The laptop is NOT reachable from the internet, so there is NO push.
  The GUI polls this service, this service polls the agent.
- The agent is dumb on purpose: info + (later) approved structured tasks
  + exit code/output. Laptop decides, laptop verifies by re-reading
  state (NOT by exit code alone), laptop logs every command sent.

## v1 proof — the only test that matters first

From Tee's laptop, open the Helm web GUI and see the Droplet's
resources in a Hestia-layout dashboard: CPU, memory, and storage.
Real data from the Droplet agent, NOT mock data for the final test.
Mock mode is fine for a frontend demo step, but the v1 proof must be
live agent data.

After that proof passes, then add the task flow on top:
info -> decide -> send -> execute -> verify -> log, with structured
task payloads only, preview-approve gate before any change, verification
by state re-read on the laptop. No free-form shell strings from GUI
to agent, ever.

## Run (dev, v1)

```sh
cp config.example.json config.json
# Edit config.json: droplet_host, ssh_user, ssh_key, agent_path, status_file_path
# config.json is gitignored — do not commit it.
./run.sh
# Open http://127.0.0.1:8080/ in a browser
```

Mock demo only (never the proof):

```sh
HELM_MOCK=1 ./run.sh
```

## Files

- `server.py` — local service, stdlib only, localhost only.
  Firewall APIs: GET /api/firewall, POST /api/firewall/preview,
  POST /api/firewall/apply (preview-token gate, single-use).
- `web/` — Hestia-layout GUI: index.html, style.css, app.js,
  plus firewall.html + firewall.js (first feature after v1).
- `config.example.json` — copy to config.json, fill in your details.
- `run.sh` — dev runner.
- `local-service/taig-helm.service` — example systemd user unit template
  for autostart on a Linux laptop. Windows autostart is a later, Tee-picked
  step, not invented here.
- `BUILD_PLAN.md` — v1 proof plan + what comes after it.
- `logs/helm.log` — every SSH command sent, with exit code and duration.
  Key contents are never logged.

## Security, v1

- Fixed remote commands only, allow-listed subcommands, no shell=True.
- No GUI input ever reaches the remote command.
- SSH key lives in the laptop's local config, referenced, never committed,
  never printed in logs or API replies.
- Do NOT deploy this to a client box or lab machine. Droplet only, for v1.
