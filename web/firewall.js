// TAIG Helm Firewall GUI — polls the LOCAL service only.
let previewToken = null;
async function load(){
  const banner = document.getElementById("banner");
  try{
    const r = await fetch("/api/firewall");
    const j = await r.json();
    if(!r.ok) throw new Error(j.error || ("HTTP " + r.status));
    const d = j.data;
    banner.className = "banner " + (j.meta.source === "live" ? "live" : "mock");
    banner.textContent = j.meta.source === "live" ? "LIVE — real iptables rules from the Droplet agent." : "MOCK — demo rules only, NOT live.";
    document.getElementById("policy").textContent = "INPUT policy: " + (d.input_policy || "—") + " · " + (d.persistent_note || "");
    document.getElementById("rules").innerHTML = (d.rules || []).map(x => {
      const rm = x.helm_managed ? `<button data-op="remove" data-action="${x.action}" data-proto="${x.protocol}" data-port="${x.port}" data-source="${x.source || "0.0.0.0/0"}">Remove</button>` : "";
      const act = x.action === "allow" ? "Allow" : (x.action === "deny" ? "Block" : (x.action || "—"));
      const src = (x.source === "0.0.0.0/0" ? "Anywhere" : (x.source || "—"));
      return `<tr><td>${act}</td><td>${x.service || ("Port " + (x.port ?? "—"))}</td><td>${(x.protocol || "—").toUpperCase()}</td><td>${x.port ?? "—"}</td><td>${src}</td><td>${x.helm_managed ? "Yes" : "No"}</td><td>${rm}</td></tr>`;
    }).join("") || "<tr><td colspan=7>No rules yet.</td></tr>";
    document.getElementById("listening").innerHTML = (d.listening_ports || []).map(x => `<tr><td>${x.proto}</td><td>${x.local}</td></tr>`).join("") || "<tr><td colspan=2>—</td></tr>";
    // Live list: pick a listening port by name, no typing the port number.
    const live = document.getElementById("live-list");
    const ports = [...new Set((d.listening_ports || []).map(x => {
      const m = String(x.local).match(/:(\d+)$/); return m ? m[1] : null;
    }).filter(Boolean))];
    live.innerHTML = "<option value=''>— pick a listening port —</option>" + ports.map(p => `<option value="${p}">Port ${p} (already listening)</option>`).join("");
    document.querySelectorAll("[data-op=remove]").forEach(b => b.onclick = () => preview({
      op: "remove", action: b.dataset.action, protocol: b.dataset.proto,
      port: parseInt(b.dataset.port, 10), source: b.dataset.source
    }));
  }catch(e){
    banner.className = "banner error";
    banner.textContent = "ERROR — " + e.message;
  }
}
async function preview(payload){
  const r = await fetch("/api/firewall/preview", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
  const j = await r.json();
  if(!r.ok){ alert("Preview refused: " + (j.error || "unknown")); return; }
  previewToken = j.preview_token;
  document.getElementById("preview-effect").textContent = j.effect + (j.technical ? " " + j.technical : "");
  document.getElementById("preview-checks").innerHTML = (j.safety_checks || []).map(c => `<li>${c}</li>`).join("");
  document.getElementById("preview").style.display = "block";
  document.getElementById("result").style.display = "none";
}
document.getElementById("preset").onchange = (e) => {
  const v = e.target.value;
  if(v !== "custom"){ document.getElementById("port").value = v; document.getElementById("protocol").value = "tcp"; }
  if(v === "22"){ document.getElementById("action").value = "allow"; }
};
document.getElementById("live-list").onchange = (e) => {
  if(e.target.value){ document.getElementById("port").value = e.target.value; document.getElementById("preset").value = "custom"; }
};
document.getElementById("add-form").onsubmit = async (e) => {
  e.preventDefault();
  await preview({
    op: "add",
    action: document.getElementById("action").value,
    protocol: document.getElementById("protocol").value,
    port: parseInt(document.getElementById("port").value, 10),
    source: document.getElementById("source").value.trim() || "any"
  });
};
document.getElementById("cancel-preview").onclick = () => { previewToken = null; document.getElementById("preview").style.display = "none"; };
document.getElementById("approve").onclick = async () => {
  if(!previewToken) return;
  const r = await fetch("/api/firewall/apply", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({preview_token: previewToken})});
  const j = await r.json();
  previewToken = null;
  document.getElementById("preview").style.display = "none";
  document.getElementById("result").style.display = "block";
  if(!r.ok){ document.getElementById("result-text").textContent = "Apply failed: " + (j.error || "unknown"); document.getElementById("verify-text").textContent = ""; }
  else{
    document.getElementById("result-text").textContent = "Apply sent. Agent result: " + JSON.stringify(j.applied || j);
    const v = j.verification || {};
    document.getElementById("verify-text").textContent = "Verification (laptop re-read): " + (v.verified === true ? "VERIFIED — rule state matches expectation." : v.verified === false ? "NOT VERIFIED — re-read does not match. Check rules above." : JSON.stringify(v));
  }
  load();
};
load();
