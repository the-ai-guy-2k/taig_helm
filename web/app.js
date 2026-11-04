// TAIG Helm v1 GUI — polls the LOCAL service only. No direct Droplet calls.
function fmtBytes(n){if(n==null)return "—";const u=["B","KB","MB","GB","TB"];let i=0;while(n>=1024&&i<u.length-1){n/=1024;i++}return n.toFixed(1)+" "+u[i]}
function fmtUptime(s){if(s==null)return "—";const d=Math.floor(s/86400),h=Math.floor(s%86400/3600),m=Math.floor(s%3600/60);return `${d}d ${h}h ${m}m`}
async function load(useFile){
  const banner=document.getElementById("banner");
  try{
    const r=await fetch(useFile?"/api/status-file":"/api/status");
    const j=await r.json();
    if(!r.ok) throw new Error(j.error||("HTTP "+r.status));
    const d=j.data, m=j.meta||{};
    const live=m.source==="live";
    banner.className="banner "+(live?"live":(m.source==="mock"?"mock":"error"));
    banner.textContent=live?`LIVE — real Droplet data via local service + SSH. Verified by: ${m.verified_by||"fresh_read"}`
      : (m.source==="mock"?`MOCK — demo data only, NOT the v1 proof.`:`Status: ${m.source||"unknown"}`);
    document.getElementById("hostname").textContent=d.hostname||"—";
    document.getElementById("os").textContent=d.os||"—";
    document.getElementById("uptime").textContent=fmtUptime(d.uptime_seconds);
    document.getElementById("load").textContent=(d.load_avg||[]).map(x=>x.toFixed(2)).join(" / ")||"—";
    document.getElementById("updated").textContent=d.timestamp||"—";
    document.getElementById("cpu-pct").textContent=(d.cpu_percent??"—")+"%";
    document.getElementById("cpu-bar").style.width=(d.cpu_percent||0)+"%";
    document.getElementById("cpu-detail").textContent=`${d.cpu_count||"?"} CPUs · load ${d.load_avg?d.load_avg[0].toFixed(2):"—"}`;
    document.getElementById("mem-pct").textContent=(d.memory.percent??"—")+"%";
    document.getElementById("mem-bar").style.width=(d.memory.percent||0)+"%";
    document.getElementById("mem-detail").textContent=`${fmtBytes(d.memory.used)} used / ${fmtBytes(d.memory.total)} total`;
    const s=d.storage||{};
    document.getElementById("disk-pct").textContent=(s.percent??"—")+"%";
    document.getElementById("disk-bar").style.width=(s.percent||0)+"%";
    document.getElementById("disk-detail").textContent=`${s.mount||"/"} · ${fmtBytes(s.used)} used / ${fmtBytes(s.total)} total`;
    document.getElementById("disks").innerHTML=(d.disks||[]).map(x=>`<tr><td>${x.mount}</td><td>${fmtBytes(x.used)}</td><td>${fmtBytes(x.free)}</td><td>${fmtBytes(x.total)}</td><td>${x.percent}%</td></tr>`).join("")||"<tr><td colspan=5>—</td></tr>";
  }catch(e){
    banner.className="banner error";
    banner.textContent="ERROR — could not reach the Droplet agent via the local service: "+e.message;
  }
}
document.getElementById("refresh").onclick=()=>load(false);
document.getElementById("poll-file").onclick=()=>load(true);
let timer=setInterval(()=>{if(document.getElementById("auto").checked) load(false)},30000);
load(false);
