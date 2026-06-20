"use strict";
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;" }[c]));
const chipsHtml = (arr) => (arr || []).map(x => `<span class="chip">${esc(x)}</span>`).join("");
const fmtTime = (s) => { s=Math.max(0,Math.round(s||0)); return `${Math.floor(s/60)}:${String(s%60).padStart(2,"0")}`; };

function applyTheme(t){ document.documentElement.dataset.theme=t; try{localStorage.setItem("brief.theme",t);}catch{} }
applyTheme((()=>{try{return localStorage.getItem("brief.theme")}catch{return null}})()||"light");
$("#theme-btn").onclick=()=>applyTheme(document.documentElement.dataset.theme==="dark"?"light":"dark");

let BRIEF=null;
const F={themes:new Set(),shows:new Set(),labels:new Set(),q:""};

function chainHtml(edges){
  if(!edges||!edges.length) return "";
  const rows = edges.map(e=>`<div class="step">
      <span class="node">${esc(e.from)}</span>
      <span class="rel">${esc(e.relation)}</span><span class="arrow">→</span>
      <span class="node k-${esc(e.kind)}">${esc(e.to)}</span></div>`).join("");
  return `<div class="sec-k">Financial reasoning chain</div><div class="chain">${rows}</div>`;
}

function momentHtml(m){
  const badge = m.delivery==="clip" ? `<span class="badge b-clip">🎧 clip</span>`
              : m.delivery==="summary" ? `<span class="badge b-summary">summary</span>`
              : `<span class="badge b-note">note</span>`;
  const risk = m.risk_direction && m.risk_direction!=="neutral"
    ? `<span class="risk ${esc(m.risk_direction)}">${esc(m.risk_direction)}</span>`:"";
  const f=[];
  if(m.thesis) f.push(`<div><b>Thesis:</b> ${esc(m.thesis)}</div>`);
  if((m.exposures||[]).length) f.push(`<div><b>Exposed:</b> ${chipsHtml(m.exposures)}${(m.second_order||[]).length?` <b>· 2nd-order:</b> ${chipsHtml(m.second_order)}`:""}</div>`);
  if(m.consensus_variant) f.push(`<div><b>Variant vs consensus:</b> ${esc(m.consensus_variant)}</div>`);
  if(m.credible) f.push(`<div><b>Who / credibility:</b> ${esc(m.credible)}</div>`);
  if(m.catalyst) f.push(`<div><b>Catalyst:</b> ${esc(m.catalyst)}</div>`);
  if(m.action) f.push(`<div><b>Action:</b> ${esc(m.action)}</div>`);
  if(m.watch_next) f.push(`<div><b>Watch next:</b> ${esc(m.watch_next)}</div>`);
  return `<div class="item">
    <div class="item-h">${badge}<span class="lbl">${esc(m.label)}</span>${risk}<span class="lbl">${fmtTime(m.start)}</span></div>
    <div class="headline">${esc(m.headline)}</div>
    ${m.quote?`<div class="fields" style="font-style:italic;color:var(--muted)">“${esc(m.quote)}”</div>`:""}
    <div class="fields">${f.join("")}</div>
  </div>`;
}

function clipsHtmlBlock(clips){
  if(!clips||!clips.length) return "";
  const rows = clips.map(c=>`<div class="audio">
      <div class="cap">🎧 ${esc(c.label)} · ${esc(c.headline)}${c.dur?` · ${Math.round(c.dur)}s`:""} · @${fmtTime(c.start)}</div>
      <audio controls preload="none" src="${esc(c.path)}"></audio></div>`).join("");
  return `<div class="sec-k">Clips</div>${rows}`;
}

function epVisible(ep){
  if(F.themes.size && !F.themes.has(ep.theme)) return false;
  if(F.shows.size && !F.shows.has(ep.show)) return false;
  const q=F.q.toLowerCase();
  if(q){ const hay=(ep.show+" "+ep.title+" "+ep.summary+" "+JSON.stringify(ep.moments)+" "+JSON.stringify(ep.reasoning_chain)).toLowerCase();
    if(!hay.includes(q)) return false; }
  return true;
}
function momVisible(m){
  if(F.labels.size && !F.labels.has(m.label)) return false;
  const q=F.q.toLowerCase();
  if(q){ const hay=(m.headline+" "+m.thesis+" "+(m.exposures||[]).join(" ")+" "+(m.second_order||[]).join(" ")+" "+m.watch_next).toLowerCase();
    if(!hay.includes(q)) return false; }
  return true;
}

function render(){
  const host=$("#episodes");
  const eps=(BRIEF.episodes||[]).filter(epVisible).map(ep=>{
    const moments=ep.moments.filter(momVisible);
    if(F.labels.size && !moments.length) return "";
    const clips=ep.clips.filter(c=>!F.labels.size || F.labels.has(c.label));
    return `<div class="ep">
      <div class="ep-h"><span class="show">${esc(ep.show)}</span>
        <span class="ttl">${ep.url?`<a href="${esc(ep.url)}" target="_blank" rel="noopener">${esc(ep.title)}</a>`:esc(ep.title)}</span>
        <span class="theme">${esc(ep.theme)}</span></div>
      ${ep.summary?`<div class="ep-sum">${esc(ep.summary)}</div>`:""}
      ${chainHtml(ep.reasoning_chain)}
      <div class="sec-k">PM-relevant moments (${moments.length})</div>
      ${moments.map(momentHtml).join("")||'<div class="empty" style="padding:10px">No moments match the filter.</div>'}
      ${clipsHtmlBlock(clips)}
    </div>`;
  }).filter(Boolean).join("");
  host.innerHTML = eps || `<div class="empty">No episodes match these filters.</div>`;
}

function buildFilters(){
  const f=BRIEF.facets||{themes:[],shows:[],labels:[]};
  const mk=(arr,set,host)=>{ $(host).innerHTML=arr.map(v=>`<span class="fchip" data-v="${esc(v)}">${esc(v)}</span>`).join("");
    $(host).onclick=(e)=>{const c=e.target.closest(".fchip"); if(!c)return;
      const v=c.dataset.v; set.has(v)?set.delete(v):set.add(v); c.classList.toggle("on"); render(); }; };
  mk(f.themes,F.themes,"#f-theme"); mk(f.shows,F.shows,"#f-show"); mk(f.labels,F.labels,"#f-label");
}

(async function(){
  try{ BRIEF=await fetch("brief.json").then(r=>r.json()); }catch{ $("#exec").textContent="Couldn't load brief.json."; return; }
  $("#meta").textContent=`${(BRIEF.generated_at||"").slice(0,10)} · ${BRIEF.episodes_count||0} episodes · ${BRIEF.moments_count||0} moments · ${BRIEF.clips_count||0} clips`;
  if(BRIEF.sample) $("#sample-banner").classList.remove("hidden");
  $("#exec").textContent=BRIEF.exec_summary||"(no exec summary yet)";
  buildFilters();
  let t; $("#q").oninput=(e)=>{F.q=e.target.value.trim(); clearTimeout(t); t=setTimeout(render,180);};
  render();
})();
