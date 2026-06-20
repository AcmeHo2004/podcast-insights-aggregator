"use strict";
const $=(s)=>document.querySelector(s);
const esc=(s)=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const fmt=(s)=>{s=Math.max(0,Math.round(s||0));return `${Math.floor(s/60)}:${String(s%60).padStart(2,"0")}`;};

function applyTheme(t){document.documentElement.dataset.theme=t;try{localStorage.setItem("brief.theme",t);}catch{}}
applyTheme((()=>{try{return localStorage.getItem("brief.theme")}catch{return null}})()||"light");
$("#theme-btn").onclick=()=>applyTheme(document.documentElement.dataset.theme==="dark"?"light":"dark");

let BRIEF=null;
const F={view:"moments",labels:new Set(),exposures:new Set(),themes:new Set(),shows:new Set(),q:""};
const ORDER=["Thesis-changing","Catalyst-relevant","Risk-relevant","Consensus-variant","Background only"];
const LBL={
 "Thesis-changing":{t:"t-thesis",l:"l-thesis",s:"Thesis-changing"},
 "Catalyst-relevant":{t:"t-catalyst",l:"l-catalyst",s:"Catalyst"},
 "Risk-relevant":{t:"t-risk",l:"l-risk",s:"Risk"},
 "Consensus-variant":{t:"t-variant",l:"l-variant",s:"Variant perception"},
 "Background only":{t:"t-bg",l:"l-bg",s:"Background"},
};

function mVisible(m){
  if(F.labels.size&&!F.labels.has(m.label))return false;
  if(F.themes.size&&!F.themes.has(m.theme))return false;
  if(F.shows.size&&!F.shows.has(m.show))return false;
  if(F.exposures.size){
    const es=(m.exposures||[]).concat(m.second_order||[]).map(x=>x.toLowerCase());
    if(![...F.exposures].some(x=>es.some(e=>e.includes(x)||x.includes(e))))return false;
  }
  if(F.q&&!JSON.stringify(m).toLowerCase().includes(F.q.toLowerCase()))return false;
  return true;
}

function expChips(m){
  return (m.exposures||[]).map(e=>`<span class="exp" data-exp="${esc(e)}">${esc(e)}</span>`).join("")
   + (m.second_order||[]).map(e=>`<span class="exp so" data-exp="${esc(e)}">${esc(e)}</span>`).join("");
}
function momentCard(m){
  const c=LBL[m.label]||LBL["Background only"];
  const risk=m.risk_direction&&m.risk_direction!=="neutral"?`<span class="risk-i ${esc(m.risk_direction)}">${esc(m.risk_direction)}</span>`:"";
  const ts=m.start?`@${fmt(m.start)}`:"";
  const src=`${esc(m.show)}${m.url?` · <a href="${esc(m.url)}" target="_blank" rel="noopener">listen ${ts}</a>`:` ${ts}`} · ${esc(m.theme)}`;
  const exps=expChips(m);
  const f=[];
  if(m.thesis)f.push(`<div><b>Thesis:</b> ${esc(m.thesis)}</div>`);
  if(exps)f.push(`<div><b>Exposed:</b> ${exps}</div>`);
  if(m.consensus_variant)f.push(`<div><b>Variant:</b> ${esc(m.consensus_variant)}</div>`);
  if(m.action)f.push(`<div><b>Do:</b> ${esc(m.action)}</div>`);
  if(m.watch_next)f.push(`<div><b>Watch:</b> ${esc(m.watch_next)}</div>`);
  const audio=m.clip_path?`<div class="audio"><div class="cap">🎧 clip · ${esc(m.headline).slice(0,60)}</div><audio controls preload="none" src="${esc(m.clip_path)}"></audio></div>`:"";
  return `<div class="m ${c.l}">
    <div class="m-h"><span class="tag ${c.t}">${c.s}</span>${risk}<span class="src">${src}</span></div>
    <div class="m-head">${esc(m.headline)}</div>
    <div class="f">${f.join("")}</div>${audio}</div>`;
}

function renderMoments(){
  const vis=(BRIEF.moments||[]).filter(mVisible);
  let h=`<div class="exec"><h2>What changed this week</h2><div>${esc(BRIEF.exec_summary||"—")}</div></div>`;
  for(const lab of ORDER){
    const g=vis.filter(m=>m.label===lab); if(!g.length)continue;
    h+=`<div class="sec-title">${LBL[lab].s} <span style="color:var(--muted)">· ${g.length}</span></div>`
      +`<div class="mgrid">`+g.map(momentCard).join("")+`</div>`;
  }
  if(!vis.length)h+=`<div class="empty">No moments match these filters.</div>`;
  return h;
}

function renderWatchlist(){
  const ms=(BRIEF.moments||[]).filter(m=>{
    if(F.themes.size&&!F.themes.has(m.theme))return false;
    if(F.shows.size&&!F.shows.has(m.show))return false;
    return true;});
  const exp={};
  for(const m of ms)for(const e of (m.exposures||[])){const k=e.trim();if(k)exp[k]=exp[k]||{n:0,labels:new Set()},exp[k].n++,exp[k].labels.add(m.label);}
  const ranked=Object.entries(exp).sort((a,b)=>b[1].n-a[1].n).slice(0,30);
  const expHtml=ranked.length?ranked.map(([k,v])=>`<div class="wl-row">
     <span class="wl-name" data-exp="${esc(k)}">${esc(k)}</span>
     <span class="wl-sub">${[...v.labels].includes("Thesis-changing")?"thesis ":""}${[...v.labels].includes("Catalyst-relevant")?"catalyst":""}</span>
     <span class="wl-n">${v.n}×</span></div>`).join(""):`<div class="wl-sub">No exposures.</div>`;
  const cats=ms.filter(m=>m.catalyst).map(m=>`<div class="wl-row"><span class="wl-sub"><b>${esc(m.catalyst)}</b> — ${esc(m.show)}: ${esc(m.headline).slice(0,70)}</span></div>`).join("")||`<div class="wl-sub">No catalysts flagged.</div>`;
  const watch=ms.filter(m=>m.watch_next).map(m=>`<div class="wl-row"><span class="wl-sub">${esc(m.watch_next)} <span style="color:var(--muted)">— ${esc(m.show)}</span></span></div>`).join("")||`<div class="wl-sub">Nothing to watch.</div>`;
  return `<div class="wl-grid">
    <div class="wl-card"><h3>Exposures mentioned (click to filter)</h3>${expHtml}</div>
    <div class="wl-card"><h3>Catalysts / timing</h3>${cats}</div>
    <div class="wl-card" style="grid-column:1/-1"><h3>What to watch (1–8 weeks)</h3>${watch}</div>
  </div>`;
}

function chainHtml(edges){
  if(!edges||!edges.length)return "";
  return `<div class="chain">`+edges.map(e=>`<div class="step">
     <span class="node">${esc(e.from)}</span><span class="rel">${esc(e.relation)}</span>→
     <span class="node k-${esc(e.kind)}">${esc(e.to)}</span></div>`).join("")+`</div>`;
}
function renderEpisodes(){
  const q=F.q.toLowerCase();
  const eps=(BRIEF.episodes||[]).filter(ep=>{
    if(F.themes.size&&!F.themes.has(ep.theme))return false;
    if(F.shows.size&&!F.shows.has(ep.show))return false;
    if(q&&!JSON.stringify(ep).toLowerCase().includes(q))return false;
    return true;
  }).map(ep=>{
    const moments=ep.moments.filter(m=>(!F.labels.size||F.labels.has(m.label)));
    return `<div class="ep">
      <div class="ep-h"><span class="show">${esc(ep.show)}</span>
        <span class="ttl">${ep.url?`<a href="${esc(ep.url)}" target="_blank" rel="noopener">${esc(ep.title)}</a>`:esc(ep.title)}</span>
        <span class="theme">${esc(ep.theme)}</span></div>
      <div class="sec-title">Reasoning chain</div>${chainHtml(ep.reasoning_chain)}
      <div class="sec-title">Moments · ${moments.length}</div>
      ${moments.map(m=>momentCard({...m,show:ep.show,title:ep.title,url:ep.url,theme:ep.theme})).join("")}
    </div>`;
  }).join("");
  return eps||`<div class="empty">No episodes match.</div>`;
}

function render(){
  const n=F.labels.size+F.exposures.size+F.themes.size+F.shows.size;
  const b=$("#filt-n"); b.textContent=n||""; b.classList.toggle("hidden",!n);
  $("#view").innerHTML = F.view==="watchlist"?renderWatchlist():F.view==="episodes"?renderEpisodes():renderMoments();
}

function buildFilters(){
  const f=BRIEF.facets||{};
  const mk=(arr,set,host)=>{$(host).innerHTML=(arr||[]).map(v=>`<span class="fchip${set.has(v)?" on":""}" data-v="${esc(v)}">${esc(v)}</span>`).join("");};
  mk((f.labels||[]).map(l=>l),F.labels,"#f-label");
  $("#f-label").innerHTML=(f.labels||[]).map(v=>`<span class="fchip${F.labels.has(v)?" on":""}" data-v="${esc(v)}">${esc(LBL[v]?LBL[v].s:v)}</span>`).join("");
  mk(f.exposures,F.exposures,"#f-exp"); mk(f.themes,F.themes,"#f-theme"); mk(f.shows,F.shows,"#f-show");
}
function toggle(set,v){set.has(v)?set.delete(v):set.add(v);}

(async function(){
  try{BRIEF=await fetch("brief.json").then(r=>r.json());}catch{$("#view").innerHTML='<div class="empty">Couldn\'t load brief.json.</div>';return;}
  $("#meta").textContent=`${(BRIEF.generated_at||"").slice(0,10)} · ${BRIEF.episodes_count||0} eps · ${BRIEF.moments_count||0} moments · ${BRIEF.clips_count||0} clips`;
  if(BRIEF.sample)$("#sample-banner").classList.remove("hidden");
  buildFilters(); render();

  $("#viewseg").onclick=(e)=>{const b=e.target.closest(".segbtn");if(!b)return;
    F.view=b.dataset.view; [...$("#viewseg").children].forEach(x=>x.classList.toggle("on",x===b)); render();};
  $("#filt-btn").onclick=()=>$("#filters").classList.toggle("hidden");
  // filter chips
  const wire=(host,set)=>{$(host).onclick=(e)=>{const c=e.target.closest(".fchip");if(!c)return;
    toggle(set,c.dataset.v); c.classList.toggle("on"); render();};};
  wire("#f-label",F.labels); wire("#f-exp",F.exposures); wire("#f-theme",F.themes); wire("#f-show",F.shows);
  $("#fclear").onclick=()=>{F.labels.clear();F.exposures.clear();F.themes.clear();F.shows.clear();F.q="";$("#q").value="";buildFilters();render();};
  // click an exposure anywhere → filter by it
  $("#view").addEventListener("click",(e)=>{const x=e.target.closest("[data-exp]");if(!x)return;
    const v=x.dataset.exp; F.exposures.add(v); F.view="moments";
    [...$("#viewseg").children].forEach(b=>b.classList.toggle("on",b.dataset.view==="moments"));
    buildFilters(); render(); window.scrollTo({top:0,behavior:"smooth"});});
  let t;$("#q").oninput=(e)=>{F.q=e.target.value.trim();clearTimeout(t);t=setTimeout(render,160);};
})();
