"use strict";
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;" }[c]));
const chips = (arr) => (arr || []).map(x => `<span class="chip">${esc(x)}</span>`).join("");

function applyTheme(t){ document.documentElement.dataset.theme = t; try{ localStorage.setItem("brief.theme", t);}catch{} }
applyTheme((()=>{try{return localStorage.getItem("brief.theme")}catch{return null}})() || "light");
$("#theme-btn").onclick = () => applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");

function fmtTime(s){ s=Math.max(0,Math.round(s||0)); const m=Math.floor(s/60), ss=String(s%60).padStart(2,"0"); return `${m}:${ss}`; }

function renderItem(it){
  const badge = it.delivery === "clip" ? `<span class="badge b-clip">🎧 clip</span>`
              : it.delivery === "summary" ? `<span class="badge b-summary">summary</span>`
              : `<span class="badge b-note">note</span>`;
  const risk = it.risk_direction && it.risk_direction !== "neutral"
    ? `<span class="risk ${esc(it.risk_direction)}">${esc(it.risk_direction)}</span>` : "";
  const f = [];
  if (it.thesis) f.push(`<div><b>Thesis:</b> ${esc(it.thesis)}</div>`);
  if ((it.exposures||[]).length) f.push(`<div><b>Exposed:</b> ${chips(it.exposures)}${(it.second_order||[]).length?` <b>· 2nd-order:</b> ${chips(it.second_order)}`:""}</div>`);
  if (it.consensus_variant) f.push(`<div><b>Variant vs consensus:</b> ${esc(it.consensus_variant)}</div>`);
  if (it.credible) f.push(`<div><b>Who / credibility:</b> ${esc(it.credible)}</div>`);
  if (it.catalyst) f.push(`<div><b>Catalyst:</b> ${esc(it.catalyst)}</div>`);
  if (it.action) f.push(`<div><b>Action:</b> ${esc(it.action)}</div>`);
  if (it.watch_next) f.push(`<div><b>Watch next:</b> ${esc(it.watch_next)}</div>`);
  const ts = it.start ? ` · ${fmtTime(it.start)}` : "";
  const link = it.url ? `<a href="${esc(it.url)}" target="_blank" rel="noopener">${esc(it.show)} — listen${ts}</a>`
                      : `${esc(it.show)}${ts}`;
  const clipNote = it.delivery === "clip" ? ` · <span title="Clips ship privately in the weekly email">clip in email</span>` : "";
  return `<div class="item">
    <div class="item-h">${badge}<span class="lbl">${esc(it.label)}</span>${risk}</div>
    <div class="headline">${esc(it.headline)}</div>
    ${it.quote ? `<div class="fields" style="font-style:italic;color:var(--muted)">“${esc(it.quote)}”</div>`:""}
    <div class="fields">${f.join("")}</div>
    <div class="src">${link}${clipNote}</div>
  </div>`;
}

function renderBrief(b){
  $("#meta").textContent = `${b.generated_at ? b.generated_at.slice(0,10) : ""}`
    + (b.episodes != null ? ` · ${b.episodes} episodes · ${b.moments} moments` : "");
  if (b.sample) $("#sample-banner").classList.remove("hidden");
  $("#exec").textContent = b.exec_summary || "(no exec summary yet)";
  const host = $("#themes");
  host.innerHTML = (b.themes || []).map(t => {
    const clips = t.items.filter(i => i.delivery === "clip").length;
    return `<div class="theme-h"><h3>${esc(t.theme)}</h3>
        <span class="n">${t.items.length} moment${t.items.length!==1?"s":""}${clips?` · ${clips} clip${clips!==1?"s":""}`:""}</span></div>
      ${t.synthesis ? `<div class="synth">${esc(t.synthesis)}</div>`:""}
      ${t.items.map(renderItem).join("")}`;
  }).join("");
}

const GTYPES = [["company","#6E59D9"],["person","#3FB8C4"],["asset","#1e8e5a"],["sector","#B8733A"],["theme","#D8584E"],["macro","#B0894F"]];
const GSTANCE = [["bullish","#1e8e5a"],["bearish","#d8584e"],["disagrees","#b0894f"],["exposed-to","#6E59D9"]];

function renderGraph(g){
  $("#legend").innerHTML =
    GTYPES.map(([k,c])=>`<span><i class="dot" style="background:${c}"></i>${k}</span>`).join("")
    + ` &nbsp;|&nbsp; `
    + GSTANCE.map(([k,c])=>`<span><i class="dot" style="background:${c}"></i>${k}</span>`).join("");
  const el = $("#graph");
  if (!g || !g.nodes || !g.nodes.length){ $("#graph-hint").textContent = "No graph data yet."; return; }
  $("#graph-hint").textContent = `${g.nodes.length} nodes · ${g.links.length} edges`
    + (g.sample ? " (sample)" : "") + " — drag to explore; hover an edge for who said it.";
  if (typeof ForceGraph !== "function"){ el.innerHTML = `<p class="hint" style="padding:16px">Graph library didn't load (offline?). Data is in graph.json.</p>`; return; }
  const G = ForceGraph()(el)
    .width(el.clientWidth).height(el.clientHeight)
    .backgroundColor("rgba(0,0,0,0)")
    .nodeId("id").nodeVal(n => 2 + (n.val||1))
    .nodeColor(n => n.color || "#8A93A6")
    .nodeLabel(n => `${n.id} (${n.type})`)
    .nodeCanvasObjectMode(()=> "after")
    .nodeCanvasObject((n,ctx,scale)=>{ if (scale < 1.3) return;
      const dark = document.documentElement.dataset.theme === "dark";
      ctx.font = `${10/scale}px sans-serif`; ctx.fillStyle = dark ? "#c4c8d0" : "#3a3d44";
      ctx.textAlign="center"; ctx.fillText(n.id, n.x, n.y + 8/scale); })
    .linkColor(l => l.color || "#8A93A6").linkWidth(1).linkDirectionalArrowLength(3)
    .linkLabel(l => `${l.source.id||l.source} —${l.stance}→ ${l.target.id||l.target}${l.by?` (${l.by})`:""}`)
    .graphData({ nodes: g.nodes, links: g.links });
  setTimeout(()=>G.zoomToFit(400, 30), 500);
  window.addEventListener("resize", ()=> G.width(el.clientWidth).height(el.clientHeight));
}

(async function(){
  let brief=null, graph=null;
  try { brief = await fetch("brief.json").then(r=>r.json()); } catch {}
  try { graph = await fetch("graph.json").then(r=>r.json()); } catch {}
  if (!brief){ $("#exec").textContent = "Couldn't load brief.json."; }
  else renderBrief(brief);
  renderGraph(graph);
})();
