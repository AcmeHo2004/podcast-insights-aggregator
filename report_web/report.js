"use strict";
const $=(s)=>document.querySelector(s);
const esc=(s)=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const fmt=(s)=>{s=Math.max(0,Math.round(s||0));return `${Math.floor(s/60)}:${String(s%60).padStart(2,"0")}`;};
const dshort=(iso)=>{if(!iso)return"";const d=new Date(iso);return isNaN(d)?"":`${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;};

function applyTheme(t){document.documentElement.dataset.theme=t;try{localStorage.setItem("brief.theme",t);}catch{}}
applyTheme((()=>{try{return localStorage.getItem("brief.theme")}catch{return null}})()||"light");
$("#theme-btn").onclick=()=>applyTheme(document.documentElement.dataset.theme==="dark"?"light":"dark");

/* resizable columns (Snowflake-style drag handles), persisted */
(function(){
  try{const c=JSON.parse(localStorage.getItem("brief.cols"));if(c){if(c.l)document.documentElement.style.setProperty("--w-left",c.l);if(c.r)document.documentElement.style.setProperty("--w-right",c.r);}}catch{}
  let drag=null;
  document.addEventListener("mousedown",(e)=>{const s=e.target.closest(".splitter");if(!s)return;drag=s.dataset.edge;s.classList.add("drag");document.body.classList.add("resizing");e.preventDefault();});
  document.addEventListener("mousemove",(e)=>{if(!drag)return;const app=document.querySelector(".app").getBoundingClientRect();
    if(drag==="left"){const w=Math.max(170,Math.min(460,e.clientX-app.left));document.documentElement.style.setProperty("--w-left",w+"px");}
    else{const w=Math.max(280,Math.min(680,app.right-e.clientX));document.documentElement.style.setProperty("--w-right",w+"px");}});
  document.addEventListener("mouseup",()=>{if(!drag)return;document.querySelectorAll(".splitter").forEach(s=>s.classList.remove("drag"));document.body.classList.remove("resizing");
    const cs=getComputedStyle(document.documentElement);
    try{localStorage.setItem("brief.cols",JSON.stringify({l:cs.getPropertyValue("--w-left").trim(),r:cs.getPropertyValue("--w-right").trim()}));}catch{}
    drag=null;});
})();

let BRIEF=null, EP={}, MOMS=[];
const S={layout:"triage",mode:"show",date:"all",scope:null,labels:new Set(),q:"",sel:null,open:new Set()};
const ORDER=["Thesis-changing","Catalyst-relevant","Risk-relevant","Consensus-variant","Background only"];
const LBL={
 "Thesis-changing":{c:"l-thesis",t:"t-thesis",s:"Thesis"},
 "Catalyst-relevant":{c:"l-catalyst",t:"t-catalyst",s:"Catalyst"},
 "Risk-relevant":{c:"l-risk",t:"t-risk",s:"Risk"},
 "Consensus-variant":{c:"l-variant",t:"t-variant",s:"Variant"},
 "Background only":{c:"l-bg",t:"t-bg",s:"Background"},
};
const lc=(m)=>LBL[m.label]||LBL["Background only"];

function dateOK(m){
  if(S.date==="all")return true;
  const t=m._date?Date.parse(m._date):NaN; if(isNaN(t))return true;
  return (Date.now()-t)<=(S.date==="week"?7:30)*864e5;
}
const expMatch=(m,v)=>{v=v.toLowerCase();return (m.exposures||[]).concat(m.second_order||[]).some(e=>{const x=e.toLowerCase();return x.includes(v)||v.includes(x);});};
function scopeOK(m){const sc=S.scope;if(!sc)return true;
  if(sc.type==="show")return m.show===sc.value;
  if(sc.type==="episode")return m.ep_id===sc.value;
  if(sc.type==="theme")return m.theme===sc.value;
  if(sc.type==="exposure")return expMatch(m,sc.value);
  return true;}
const labelOK=(m)=>!S.labels.size||S.labels.has(m.label);
const qOK=(m)=>!S.q||JSON.stringify(m).toLowerCase().includes(S.q.toLowerCase());
const dateScoped=()=>MOMS.filter(dateOK);
const baseFilter=(m)=>dateOK(m)&&labelOK(m)&&qOK(m);          // date+label+search (no scope) — for board/reader
const visible=()=>MOMS.filter(m=>baseFilter(m)&&scopeOK(m));  // + scope — for triage list

function renderTree(){
  const host=$("#ltree"), base=dateScoped();
  if(S.mode==="show"){
    const by={};
    base.forEach(m=>{(by[m.show]=by[m.show]||{n:0,eps:{}});by[m.show].n++;by[m.show].eps[m.ep_id]=(by[m.show].eps[m.ep_id]||0)+1;});
    const shows=Object.keys(by).sort((a,b)=>by[b].n-by[a].n);
    host.innerHTML=shows.map(sh=>{
      const open=S.open.has(sh), selShow=S.scope&&S.scope.type==="show"&&S.scope.value===sh;
      const eps=Object.keys(by[sh].eps).map(id=>({id,n:by[sh].eps[id],ep:EP[id]}))
        .sort((a,b)=>((b.ep&&b.ep.published_at)||"").localeCompare((a.ep&&a.ep.published_at)||""));
      return `<div class="tnode ${open?"open":""}">
        <div class="trow ${selShow?"sel":""}" data-show="${esc(sh)}"><span class="caret">▸</span><span class="tname">${esc(sh)}</span><span class="tn">${by[sh].n}</span></div>
        <div class="tchildren">${eps.map(e=>{
          const selE=S.scope&&S.scope.type==="episode"&&S.scope.value===e.id, tt=e.ep?e.ep.title:e.id;
          return `<div class="tleaf ${selE?"sel":""}" data-ep="${esc(e.id)}"><span class="td">${dshort(e.ep&&e.ep.published_at)}</span><span class="tt" title="${esc(tt)}">${esc(tt)}</span><span class="tn">${e.n}</span></div>`;
        }).join("")}</div></div>`;
    }).join("")||`<div class="tn" style="padding:8px">No shows in range.</div>`;
  } else if(S.mode==="exposure"){
    const cnt={}; base.forEach(m=>(m.exposures||[]).forEach(e=>{const k=e.trim();if(k)cnt[k]=(cnt[k]||0)+1;}));
    const ranked=Object.entries(cnt).sort((a,b)=>b[1]-a[1]).slice(0,60);
    host.innerHTML=ranked.map(([k,n])=>{const sel=S.scope&&S.scope.type==="exposure"&&S.scope.value===k;
      return `<div class="tleaf ${sel?"sel":""}" data-exp="${esc(k)}"><span class="tt">${esc(k)}</span><span class="tn">${n}</span></div>`;}).join("")||`<div class="tn" style="padding:8px">No exposures.</div>`;
  } else {
    const cnt={}; base.forEach(m=>cnt[m.theme]=(cnt[m.theme]||0)+1);
    host.innerHTML=Object.keys(cnt).sort((a,b)=>cnt[b]-cnt[a]).map(t=>{const sel=S.scope&&S.scope.type==="theme"&&S.scope.value===t;
      return `<div class="tleaf ${sel?"sel":""}" data-theme="${esc(t)}"><span class="tt">${esc(t)}</span><span class="tn">${cnt[t]}</span></div>`;}).join("");
  }
}

function rowHtml(m){
  const c=lc(m);
  const ticks=(m.exposures||[]).slice(0,2).map(e=>`<span class="rtick">${esc(e)}</span>`).join("");
  const icons=(m.clip_path?'<span class="ricon">🎧</span>':'')+'<span class="ricon">📄</span>';
  return `<div class="row ${c.c} ${S.sel===m._id?"sel":""}" data-id="${m._id}"><span class="rdot ${c.c}"></span>
    <span class="rhead">${esc(m.headline)}</span>
    <span class="rmeta">${ticks}<span>${esc(m.show)}·${dshort(m._date)}</span>${icons}</span></div>`;
}
function renderList(){
  const vis=visible(), host=$("#list"), strip=$("#scope-strip");
  if(S.scope){const lbl={show:"Show",episode:"Episode",exposure:"Exposure",theme:"Theme"}[S.scope.type];
    let val=S.scope.value; if(S.scope.type==="episode"&&EP[val])val=EP[val].title;
    strip.innerHTML=`${lbl}: <b>${esc(val)}</b> <span class="x" id="scope-x">✕ clear</span>`; strip.classList.remove("hidden");
  } else strip.classList.add("hidden");
  if(!vis.length){host.innerHTML=`<div class="empty">No moments match these filters.</div>`;}
  else{let h="";for(const lab of ORDER){const g=vis.filter(m=>m.label===lab);if(!g.length)continue;
    h+=`<div class="grp">${LBL[lab].s} · ${g.length}</div>`+g.map(rowHtml).join("");}host.innerHTML=h;}
  const sx=$("#scope-x"); if(sx)sx.onclick=()=>{S.scope=null;renderAll();};
}

function expChips(m){return (m.exposures||[]).map(e=>`<span class="exp" data-exp="${esc(e)}">${esc(e)}</span>`).join("")
   +(m.second_order||[]).map(e=>`<span class="exp so" data-exp="${esc(e)}">${esc(e)}</span>`).join("");}
function momentDetailHtml(m){
  const c=lc(m);
  const risk=m.risk_direction&&m.risk_direction!=="neutral"?`<span class="d-tag t-bg">${esc(m.risk_direction)}</span>`:"";
  const f=(k,v)=>v?`<div class="d-f"><b>${k}</b>${esc(v)}</div>`:"";
  return `<div style="display:flex;gap:8px;align-items:center"><span class="d-tag ${c.t}">${c.s}</span>${risk}</div>
    <div class="d-src">${esc(m.show)} · ${esc(m.theme)} · ${dshort(m._date)}${m.url?` · <a href="${esc(m.url)}" target="_blank" rel="noopener">source</a>`:""} · <span class="txlink" data-tx data-ep="${esc(m.ep_id)}" data-t="${m.start||0}">📄 transcript @${fmt(m.start)}</span></div>
    <div class="d-head">${esc(m.headline)}</div>
    ${m.quote?`<div class="d-f" style="font-style:italic;color:var(--muted)">“${esc(m.quote)}”</div>`:""}
    ${f("Thesis",m.thesis)}
    ${(m.exposures||[]).length?`<div class="d-f"><b>Exposed</b>${expChips(m)}</div>`:""}
    ${f("Variant vs consensus",m.consensus_variant)}
    ${f("Who / credibility",m.credible)}
    ${f("Catalyst",m.catalyst)}
    ${f("Do",m.action)}
    ${f("Watch next",m.watch_next)}
    ${m.clip_path?`<audio class="d-audio" controls preload="none" src="${esc(m.clip_path)}"></audio>`:""}`;
}
function renderDetail(){
  const body=$("#detail-body");
  if(S.sel===null){
    const filtered=S.scope||S.labels.size||S.q||S.date!=="all";
    if(!filtered){
      body.innerHTML=`<div class="d-empty"><h3>What changed · last ~30 days · all shows</h3><div class="ex">${esc(BRIEF.exec_summary||"Select a moment for detail.")}</div></div>`;
    }else{
      const vis=visible(), top=vis.filter(m=>m.label==="Thesis-changing"||m.label==="Catalyst-relevant").slice(0,14);
      const lbl=S.scope?(S.scope.type==="episode"&&EP[S.scope.value]?EP[S.scope.value].title:S.scope.value):"current filter";
      body.innerHTML=`<div class="d-empty"><h3>Now showing · ${esc(lbl)}</h3>
        <div class="ex" style="font-size:12px;color:var(--muted);margin-bottom:6px">${vis.length} moments · click any for detail. Top thesis/catalyst:</div>`
        +(top.length?top.map(m=>`<div class="row ${lc(m).c}" data-id="${m._id}" style="margin-top:7px"><span class="rdot ${lc(m).c}"></span><span class="rhead">${esc(m.headline)}</span></div>`).join("")
          :`<div class="ex" style="color:var(--muted)">No thesis/catalyst in this view.</div>`)+`</div>`;
    }
    document.body.classList.remove("has-sel");return;
  }
  const m=MOMS[S.sel]; if(!m){body.innerHTML="";return;}
  body.innerHTML=momentDetailHtml(m); document.body.classList.add("has-sel");
}

function renderBoard(){
  const ms=MOMS.filter(baseFilter);
  const grp=(keyf)=>{const map={};ms.forEach(m=>keyf(m).forEach(k=>{if(k)(map[k]=map[k]||[]).push(m);}));return Object.entries(map).sort((a,b)=>b[1].length-a[1].length);};
  let cols = S.mode==="exposure"?grp(m=>(m.exposures||[]).map(e=>e.trim())).slice(0,16)
           : S.mode==="theme"?grp(m=>[m.theme]) : grp(m=>[m.show]);
  $("#list").innerHTML=`<div class="board">`+cols.map(([name,list])=>{
    const sorted=list.slice().sort((a,b)=>ORDER.indexOf(a.label)-ORDER.indexOf(b.label));
    return `<div class="bcol"><div class="bch">${esc(name)} <span class="tn">${list.length}</span></div>`+
      sorted.slice(0,50).map(m=>`<div class="brow row ${lc(m).c}" data-id="${m._id}"><span class="rdot ${lc(m).c}"></span><span class="rhead">${esc(m.headline)}</span></div>`).join("")+`</div>`;
  }).join("")+`</div>`;
}
function renderReader(){
  const ms=MOMS.filter(baseFilter), map={};
  ms.forEach(m=>(map[m.theme]=map[m.theme]||[]).push(m));
  let h=`<div class="reader"><div class="exec"><h2>What changed this week</h2><div>${esc(BRIEF.exec_summary||"")}</div></div>`;
  Object.keys(map).sort((a,b)=>map[b].length-map[a].length).forEach(th=>{
    const list=map[th].slice().sort((a,b)=>ORDER.indexOf(a.label)-ORDER.indexOf(b.label));
    h+=`<div class="rsec">${esc(th)} · ${list.length}</div>`+list.map(m=>`<div class="rcard ${lc(m).c}">${momentDetailHtml(m)}</div>`).join("");
  });
  $("#list").innerHTML=h+`</div>`;
}
function renderCenter(){
  if(S.layout==="board")renderBoard();
  else if(S.layout==="reader")renderReader();
  else renderList();
}

async function openTranscript(epId,atTime){
  let tx; try{tx=await fetch(`transcripts/${epId}.json`).then(r=>r.json());}catch{return;}
  $("#tx-title").textContent=`${tx.show} — ${tx.title}`;
  const a=$("#tx-audio"); a.src=tx.audio_url||"";
  const segs=tx.segments||[]; let tgt=segs.findIndex(s=>s.end>=atTime); if(tgt<0)tgt=0;
  $("#tx-body").innerHTML=segs.map((s,i)=>`<div class="tx-line${i===tgt?" hl":""}" data-t="${s.start}"><span class="tx-ts">${fmt(s.start)}</span><span>${esc(s.text)}</span></div>`).join("");
  $("#tx").classList.remove("hidden");
  const el=$("#tx-body").children[tgt]; if(el)el.scrollIntoView({block:"center"});
  if(a.src&&atTime){const seek=()=>{try{a.currentTime=Math.max(0,atTime);}catch{}};a.onloadedmetadata=seek;seek();}
}

function renderLblbar(){
  const present=ORDER.filter(l=>MOMS.some(m=>m.label===l));
  $("#lblbar").innerHTML=present.map(l=>`<span class="lchip ${LBL[l].c} ${S.labels.has(l)?"on":""}" data-lab="${esc(l)}">${LBL[l].s}</span>`).join("");
}
function renderAll(){
  document.body.classList.toggle("lay-board",S.layout==="board");
  document.body.classList.toggle("lay-reader",S.layout==="reader");
  if(S.layout!=="triage")$("#scope-strip").classList.add("hidden");
  renderTree(); renderCenter();
  if(S.layout==="triage")renderDetail(); else document.body.classList.remove("has-sel");
}

(async function(){
  try{BRIEF=await fetch("brief.json").then(r=>r.json());}catch{$("#list").innerHTML='<div class="empty">Couldn\'t load brief.json.</div>';return;}
  (BRIEF.episodes||[]).forEach(e=>EP[e.id]=e);
  MOMS=(BRIEF.moments||[]).map((m,i)=>({...m,_id:i,_date:(EP[m.ep_id]||{}).published_at||""}));
  $("#meta").textContent=`${(BRIEF.generated_at||"").slice(0,10)} · ${BRIEF.episodes_count||0} eps · ${BRIEF.moments_count||0} moments · ${BRIEF.clips_count||0} clips`;
  if(BRIEF.sample)$("#sample-banner").classList.remove("hidden");
  renderLblbar(); renderAll();

  $("#dateseg").onclick=(e)=>{const b=e.target.closest(".segbtn");if(!b)return;S.date=b.dataset.date;[...$("#dateseg").children].forEach(x=>x.classList.toggle("on",x===b));renderAll();};
  $("#modeseg").onclick=(e)=>{const b=e.target.closest(".segbtn");if(!b)return;S.mode=b.dataset.mode;S.scope=null;[...$("#modeseg").children].forEach(x=>x.classList.toggle("on",x===b));renderAll();};
  $("#layoutseg").onclick=(e)=>{const b=e.target.closest(".segbtn");if(!b)return;S.layout=b.dataset.layout;[...$("#layoutseg").children].forEach(x=>x.classList.toggle("on",x===b));renderAll();};
  $("#ltree").onclick=(e)=>{
    const sh=e.target.closest("[data-show]"); if(sh){const n=sh.dataset.show;S.open.has(n)?S.open.delete(n):S.open.add(n);S.scope={type:"show",value:n};S.sel=null;renderAll();return;}
    const ep=e.target.closest("[data-ep]"); if(ep){S.scope={type:"episode",value:ep.dataset.ep};S.sel=null;renderAll();return;}
    const ex=e.target.closest("[data-exp]"); if(ex){S.scope={type:"exposure",value:ex.dataset.exp};S.sel=null;renderAll();return;}
    const th=e.target.closest("[data-theme]"); if(th){S.scope={type:"theme",value:th.dataset.theme};S.sel=null;renderAll();return;}
  };
  $("#lblbar").onclick=(e)=>{const c=e.target.closest(".lchip");if(!c)return;const l=c.dataset.lab;S.labels.has(l)?S.labels.delete(l):S.labels.add(l);c.classList.toggle("on");renderList();};
  $("#list").onclick=(e)=>{
    if(e.target.closest("#scope-x"))return;
    const tx=e.target.closest("[data-tx]"); if(tx){openTranscript(tx.dataset.ep,parseFloat(tx.dataset.t)||0);return;}
    const ex=e.target.closest("[data-exp]"); if(ex){S.layout="triage";S.mode="exposure";S.scope={type:"exposure",value:ex.dataset.exp};
      [...$("#layoutseg").children].forEach(x=>x.classList.toggle("on",x.dataset.layout==="triage"));
      [...$("#modeseg").children].forEach(x=>x.classList.toggle("on",x.dataset.mode==="exposure"));renderAll();return;}
    const r=e.target.closest(".row"); if(!r)return;
    S.sel=Number(r.dataset.id);
    if(S.layout!=="triage"){S.layout="triage";[...$("#layoutseg").children].forEach(x=>x.classList.toggle("on",x.dataset.layout==="triage"));renderAll();}
    else{renderList();renderDetail();}};
  $("#detail").addEventListener("click",(e)=>{
    const tx=e.target.closest("[data-tx]");if(tx){openTranscript(tx.dataset.ep,parseFloat(tx.dataset.t)||0);return;}
    const r=e.target.closest(".row[data-id]");if(r){S.sel=Number(r.dataset.id);renderDetail();renderList();return;}
    const ex=e.target.closest("[data-exp]");if(ex){S.mode="exposure";S.scope={type:"exposure",value:ex.dataset.exp};[...$("#modeseg").children].forEach(x=>x.classList.toggle("on",x.dataset.mode==="exposure"));renderAll();return;}
  });
  $("#detail-close").onclick=()=>{S.sel=null;renderDetail();renderList();};
  let t;$("#q").oninput=(e)=>{S.q=e.target.value.trim();clearTimeout(t);t=setTimeout(()=>{renderTree();renderList();},160);};
  $("#tx-x").onclick=()=>$("#tx").classList.add("hidden");
  $("#tx").onclick=(e)=>{if(e.target.id==="tx")$("#tx").classList.add("hidden");};
  document.addEventListener("keydown",(e)=>{if(e.key==="Escape")$("#tx").classList.add("hidden");});
  $("#tx-body").addEventListener("click",(e)=>{const ln=e.target.closest(".tx-line");if(!ln)return;const a=$("#tx-audio"),tt=parseFloat(ln.dataset.t)||0;[...$("#tx-body").children].forEach(c=>c.classList.remove("hl"));ln.classList.add("hl");if(a.src){try{a.currentTime=tt;a.play();}catch{}}});
})();
