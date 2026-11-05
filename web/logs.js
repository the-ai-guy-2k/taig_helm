// TAIG Helm Logs GUI — polls the LOCAL service only. Read-only.
async function loadList(){
  const banner = document.getElementById("banner");
  try{
    const r = await fetch("/api/logs");
    const j = await r.json();
    if(!r.ok) throw new Error(j.error || ("HTTP " + r.status));
    banner.className = "banner " + (j.meta.source === "live" ? "live" : "mock");
    banner.textContent = j.meta.source === "live" ? "LIVE — log list from the Droplet." : "MOCK — example list only, NOT the live Droplet list.";
    const sel = document.getElementById("service");
    const files = (j.data.sources || []).filter(s => s.kind === "file");
    const dock = (j.data.sources || []).filter(s => s.kind === "docker");
    const opt = s => `<option value="${s.key}">${s.name} — ${s.description}</option>`;
    sel.innerHTML = `<optgroup label="System logs">${files.map(opt).join("")}</optgroup><optgroup label="Apps (Docker)">${dock.map(opt).join("")}</optgroup>`;
  }catch(e){
    banner.className = "banner error";
    banner.textContent = "ERROR — " + e.message;
  }
}
document.getElementById("read-form").onsubmit = async (e) => {
  e.preventDefault();
  const body = {
    service: document.getElementById("service").value,
    since_hours: document.getElementById("since").value,
    lines: parseInt(document.getElementById("lines").value, 10),
    search: document.getElementById("search").value.trim() || null,
  };
  const r = await fetch("/api/logs/read", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  const j = await r.json();
  if(!r.ok){ document.getElementById("lines").textContent = "Could not read logs: " + (j.error || "unknown"); return; }
  const d = j.data;
  document.getElementById("result-title").textContent = "Logs — " + (d.name || d.service);
  document.getElementById("result-meta").textContent = `Showing ${d.returned} of ${d.total_matched} matching lines` + (d.search ? ` for "${d.search}"` : "") + (d.since_hours ? ` in the last ${d.since_hours} hour(s)` : "") + ".";
  document.getElementById("lines").textContent = (d.lines || []).join("\n") || "(no matching lines)";
  document.getElementById("result-note").textContent = d.note || "";
};
loadList();
