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

## Firewall — CORRECTION, Nov 5, 2026 (agent v0.6.0, not yet pushed)

INPUT-only does NOT work for Docker. Live Droplet work Nov 5, verified:
only 22 + 80 open, direct Docker ports closed via DOCKER-USER.
Agent now writes Docker blocks to DOCKER-USER on the container port
(Nope 3000->3000, TSP 3001->3000, Speed 3002->3000, PIA 8003->8000),
with RETURN 127/8 + 172.17/16 first, then netfilter-persistent save,
then laptop verifies by re-reading live rules. Host services stay
on INPUT. Shared container 3000 blocks Nope, TSP, and Speed together
— UI shows that plainly, and TAIG Speed has no Nginx route (fix is a
proper host/subdomain route, Tee's call, NOT a subpath, NOT in Helm).
Also corrected: host 3000 is Nope portal, not TAIG Service Portal
(that was the v1 mapping error). Reboot survival not yet verified live.

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

## Updates — PARTIALLY good, NOT closed (Tee, Nov 4, 7:17 PM EST)

Missing portion, logged as an OPEN improvement, not built yet:
feedback DURING install. Current Updates gives preview + apply +
verify-after by re-read, plus helm.log after the fact — but no live
progress feedback while apt is actually installing (what's installing
now, progress, any apt prompt/error as it happens). Do NOT claim
Updates is fully done until that during-install feedback is added.
That improvement is separate work, after Logs unless Tee says otherwise.

## THIRD FEATURE after v1 — Logs (Nov 4, 7:17 PM EST)

Logs group is the ONE intuitive place to find logs for anything.
Intuitiveness is the core requirement (ASCIF Q7, Nov 4): pick
service/box/time in plain terms, no log paths or command syntax
needed. If Logs is not intuitive, the design fails.
Read-only — Logs never changes anything, so there is NO
preview-token apply here, only list + read.
Coverage, plain names: System log, Sign-ins, Kernel messages,
Package changes, Update history, Automatic security updates,
First-boot setup, Website visits, Website errors, TAIG Helm agent,
plus Docker apps PIA, Nope portal, TAIG Speed, TAIG Service Portal.
Live Droplet log facts at build time (Nov 4, 7:17 PM):
/var/log/syslog 1.8M, journal 20M, auth.log 1.0M,
taig-helm-agent.log 108K, nginx access/error logs present
(access.log.1 124K), dpkg.log 32K, apt logs,
unattended-upgrades logs, cloud-init logs, kern.log/dmesg.
Containers live: pia, nope-portal, taig-speed, tsp.

## Logs — BUGS OPEN / DEFERRED (Tee, Nov 4, 7:26 PM EST)

Logs feature has some bugs, fix LATER — do NOT fix Logs bugs now.
Exact bugs are Tee's to name when he reports them — NO bug list is
invented here. When Tee reports the exact bugs he saw, log those
verbatim and fix them in that later step.
Logs is NOT closed as bug-free. The Processes build below does NOT
touch Logs code.

## FOURTH FEATURE after v1 — Processes / Task-Process (Nov 4, 7:26 PM EST)

Task/Process Management group, MVP READ-ONLY, same read-everything
order as Logs (cool UI theme later, on Tee's ask, not now).
Agent processes list: running systemd services, top processes by CPU,
running Docker containers — plain names, CPU, memory, status,
structured only. Helm server GET /api/processes, web/processes.html.
NO kill/stop/restart/start in this build — execution actions are a
later step, with preview/approve.
Live Droplet facts at build time (Nov 4, 7:26 PM):
23 systemd services running (docker, containerd, nginx, ssh, cron,
rsyslog, systemd-journald, unattended-upgrades, do-agent,
droplet-agent, etc.). Containers: pia (Up 3h, 8003), nope-portal
(Up 5h, healthy, 3000), taig-speed (Up 24h, healthy, 3002), tsp
(Up 25h, healthy, 3001). Top processes include containerd, dockerd,
node servers for the containers, python PIA backend.
Logs bugs from Nov 4, 7:26 PM are NOT fixed in this build — see the
Logs bugs section above. No Logs code touched here.

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
