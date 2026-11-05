// TAIG Helm Updates GUI — polls the LOCAL service only.
let previewToken = null;
async function load(){
  const banner = document.getElementById("banner");
  try{
    const r = await fetch("/api/updates");
    const j = await r.json();
    if(!r.ok) throw new Error(j.error || ("HTTP " + r.status));
    const d = j.data;
    banner.className = "banner " + (j.meta.source === "live" ? "live" : "mock");
    banner.textContent = j.meta.source === "live" ? `LIVE — ${d.count} package(s) ready to update. Checking installed nothing.` : `MOCK — example list only, NOT the live Droplet list.`;
    document.getElementById("count").textContent = d.count;
    document.getElementById("unattended").textContent = d.unattended_upgrades_active ? "Note: security updates may already auto-apply in the background (unattended-upgrades is on). Helm still shows the full list, and you still pick manually here." : "";
    document.getElementById("pkgs").innerHTML = (d.packages || []).map(p => `<tr><td>${p.name}</td><td>${p.current}</td><td>${p.new}</td><td>${p.security === true ? "Yes — security" : (p.security === false ? "No" : "Unknown")}</td></tr>`).join("") || "<tr><td colspan=4>Nothing to update — box is up to date.</td></tr>";
    document.getElementById("one-pkg").innerHTML = (d.packages || []).map(p => `<option value="${p.name}">${p.name} — ${p.current} → ${p.new}</option>`).join("");
  }catch(e){
    banner.className = "banner error";
    banner.textContent = "ERROR — " + e.message;
  }
}
document.getElementById("refresh").onclick = load;
document.getElementById("pick-form").onsubmit = async (e) => {
  e.preventDefault();
  const scope = document.querySelector('input[name="scope"]:checked').value;
  const body = scope === "whole" ? {scope: "whole"} : {scope: "one", package: document.getElementById("one-pkg").value};
  const r = await fetch("/api/updates/preview", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  const j = await r.json();
  if(!r.ok){ alert("Preview refused: " + (j.error || "unknown")); return; }
  previewToken = j.preview_token;
  document.getElementById("preview-effect").textContent = j.effect;
  document.getElementById("preview-detail").textContent = j.detail || "";
  document.getElementById("preview-checks").innerHTML = (j.safety_checks || []).map(c => `<li>${c}</li>`).join("");
  document.getElementById("preview").style.display = "block";
  document.getElementById("result").style.display = "none";
};
document.getElementById("cancel-preview").onclick = () => { previewToken = null; document.getElementById("preview").style.display = "none"; };
document.getElementById("approve").onclick = async () => {
  if(!previewToken) return;
  const r = await fetch("/api/updates/apply", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({preview_token: previewToken})});
  const j = await r.json();
  previewToken = null;
  document.getElementById("preview").style.display = "none";
  document.getElementById("result").style.display = "block";
  if(!r.ok){ document.getElementById("result-text").textContent = "Update failed: " + (j.error || "unknown"); document.getElementById("verify-text").textContent = ""; }
  else{
    document.getElementById("result-text").textContent = "Update sent. Agent result: " + JSON.stringify(j.applied || j);
    const v = j.verification || {};
    document.getElementById("verify-text").textContent = "Verification (laptop re-read): " + (v.verified === true ? "VERIFIED — " + (v.text || "") : v.verified === false ? "NOT VERIFIED — " + (v.text || "") : JSON.stringify(v));
  }
  load();
};
load();
