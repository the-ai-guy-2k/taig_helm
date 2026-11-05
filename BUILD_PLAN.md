# TAIG Helm — Build plan

## Approval routing — LOCKED, Tee, Nov 4, 6:10 PM EST

- If ANY approval is needed (build go, deploy, task list, transport,
  anything), it goes in MAIN CHAT via Tim, NOT in a build window.
- Build windows are for back-reference later: work, design, and
  records live here, but this window does NOT ask Tee for approvals
  and does NOT wait on an approval here.
- Route: propose / prepare here, Tim carries the approval question
  to main chat, Tee decides there, Tim brings the decision back here.
- Do not change this routing unless Tee says so in main chat.

## V1 proof (this build, nothing fancier yet)

Goal: from Tee's laptop, open Helm web GUI, see Droplet CPU / memory /
storage in a Hestia-layout dashboard, real agent data.

Steps:
1. Push `taig_helm_agent` to GitHub. Droplet pulls it (pull-only).
   On the Droplet: `./install.sh`, then `agent.py status` must print JSON.
2. Push `taig_helm` to GitHub. On the laptop: copy
   `config.example.json` to `config.json`, fill in Droplet host / SSH
   user / key / agent path, run `./run.sh`, open http://127.0.0.1:8080/
3. Proof check: banner says LIVE (not MOCK), hostname matches the
   Droplet, CPU / memory / storage numbers move on refresh, and
   `logs/helm.log` shows the SSH commands sent. If any of that fails,
   fix it in dev — do NOT try to fix everything before first deploy.
   Ship v1, fix problems as they go.

## FIRST FEATURE after v1 — Firewall (Nov 4, 6:38 PM EST)

Firewall group = iptables GUI home. Built, in order:
INTUITIVENESS RULE (Tee, Nov 4, 6:40 PM EST, same as Logs): an
operator must NOT need iptables syntax, chain names, or rule order
to use Firewall. Pick in plain terms (allow/block, service/port by
name from a live list where possible, protocol dropdown), see in
plain words what the rule will do before approve, see current rules
in a plain table, never type a raw firewall command. If Firewall is
not intuitive, it fails its own requirement, even if the rules are
technically correct.
1. Read-only rules view: current iptables INPUT rules + listening
   ports, Hestia table style, at `web/firewall.html`.
2. Add/remove allow/deny form: action dropdown, port number, protocol
   tcp/udp, source validated — through the locked flow:
   info -> decide -> preview/approve -> send structured payload ->
   agent executes -> laptop verifies by re-reading rules -> log.
   No free-form shell, no auto-apply, no Docker-chain edits, no SSH block.
3. Persistence is OPEN, in main chat only: install iptables-persistent,
   or save rules another way. Do NOT install it yet. Until decided,
   rules are runtime only and the GUI says so plainly.

## SECOND FEATURE after v1 — Updates (Nov 4, 6:55 PM EST)

Updates group is the ONE place to update the whole box OR just one
package — manual pick, NOT auto-apply. Box auto-checks on page open;
checking never installs. Preview in plain words ("Update tmux from
3.3a-1 to 3.3a-1ubuntu0.1", or "Update the whole box"), approve, then
send structured choice, agent updates, laptop verifies by re-reading
the list, log everything. No apt syntax needed, no release upgrade,
no Docker changes, apt packages only, MVP scope.
Live state at build time (Nov 4, 6:55 PM, after apt-get update):
13 packages upgradable, including apt security 2.8.3 -> 2.8.4ubuntu0.1,
cloud-init, glib, python3-twisted security, tmux, ubuntu-pro-client.
Unattended-upgrades is enabled/active for security updates — Helm
still shows the full list and lets the operator pick manually.

## After v1 proof passes — task flow, in order

1. Info: GUI asks, local service sends a structured read request,
   agent returns live state. No free-form shell.
2. Decide: operator picks a task in the GUI, fills a typed form.
3. Preview + approve: GUI shows plain-language effect + structured
   payload. Nothing sends until the operator approves.
4. Send: local service sends ONLY the approved structured payload
   over SSH to the agent.
5. Execute: agent runs it with static logic, returns exit code/output.
6. Verify: laptop re-reads box state and compares to the expected
   state. Exit code alone is NEVER proof.
7. Log: laptop logs the command sent, the result, and the verification
   read-back, with snapshot reference on failure.

Groups, in locked order, when tasks land: Config, Task / Process
Management, Updates, Firewall, Logs, Restarts. Home = normal status +
alerts (client/TAIG services + connections, show-only for now).

## Monitoring (v1 + later)

- Agent writes status to a file constantly (cron, 1 minute in v1,
  overwritten every run — file never grows).
- Laptop requests/polls that file over SSH, or runs a fresh status.
- No push to the laptop, ever — laptop is not internet-reachable.
- Status file rotation/cap: single overwritten file + logrotate
  (1 MB, 3 rotations) for the writer log.

## Out of scope for v1

- Task execution, firewall rules, updates, restarts, user management.
- Fleet / lab boxes. Droplet only.
- Client deployment. Droplet only.
- Perfecting everything before first deploy. Dev, fix as you go.
