// TAIG Helm Processes GUI — polls the LOCAL service only. Read-only.
async function load(){
  const banner = document.getElementById("banner");
  try{
    const r = await fetch("/api/processes");
    const j = await r.json();
    if(!r.ok) throw new Error(j.error || ("HTTP " + r.status));
    const d = j.data;
    banner.className = "banner " + (j.meta.source === "live" ? "live" : "mock");
    banner.textContent = j.meta.source === "live" ? "LIVE — processes from the Droplet. Read-only, nothing stopped or restarted." : "MOCK — example data only, NOT the live Droplet list.";
    document.getElementById("svc-count").textContent = d.service_count;
    document.getElementById("services").innerHTML = (d.services || []).map(s => `<tr><td>${s.plain_name}</td><td>${s.active} / ${s.sub}</td><td>${s.description}</td></tr>`).join("") || "<tr><td colspan=3>(none running)</td></tr>";
    document.getElementById("ctr-count").textContent = d.container_count;
    document.getElementById("containers").innerHTML = (d.containers || []).map(c => `<tr><td>${c.plain_name}</td><td>${c.status}</td><td>${c.ports}</td></tr>`).join("") || "<tr><td colspan=3>(no containers running)</td></tr>";
    document.getElementById("top").innerHTML = (d.top_processes || []).map(p => `<tr><td>${p.name}</td><td>${p.pid}</td><td>${p.cpu_percent}</td><td>${p.mem_percent}</td><td>${p.elapsed}</td></tr>`).join("") || "<tr><td colspan=5>—</td></tr>";
  }catch(e){
    banner.className = "banner error";
    banner.textContent = "ERROR — " + e.message;
  }
}
document.getElementById("refresh").onclick = load;
load();
