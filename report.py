#!/usr/bin/env python3
"""Stage 5 — assemble the brief, episode-centric and organized around PM decisions.

Each episode carries: its labeled moments (PM Attention Model), its financial
**reasoning chain** (connected cause→effect edges), and its audio clips. Claude Opus
adds only the cross-episode "What changed this week" exec summary. The page filters by
theme / show / label and plays the clips locally. Writes report/brief-<date>.json + .md.

    python report.py

With no extracts yet, writes a clearly-labeled SAMPLE so the page renders.
"""

from __future__ import annotations

import datetime as dt

from briefs_common import CLIPS, EXTRACTS, OPUS, REPORT, claude_text, have, read_json, write_json

LABEL_RANK = {"Thesis-changing": 0, "Catalyst-relevant": 1, "Risk-relevant": 2,
              "Consensus-variant": 3, "Background only": 4}


def delivery_of(m: dict) -> str:
    if m["label"] in ("Thesis-changing", "Catalyst-relevant"):
        return "clip" if m.get("clip_path") else "summary"
    if m["label"] in ("Risk-relevant", "Consensus-variant"):
        return "summary"
    return "note"


def moment_view(m: dict) -> dict:
    return {
        "label": m["label"], "delivery": delivery_of(m),
        "headline": m["headline"], "quote": m.get("quote", ""),
        "thesis": m.get("thesis", ""), "credible": m.get("credibility", ""),
        "consensus_variant": m.get("variant_vs_consensus", ""),
        "exposures": m.get("exposures", []), "second_order": m.get("second_order", []),
        "catalyst": m.get("catalyst", ""), "risk_direction": m.get("risk_direction", ""),
        "action": m.get("action", ""), "watch_next": m.get("watch_next", ""),
        "start": m.get("start", 0), "clip_path": m.get("clip_path", ""),
    }


def exec_summary(episodes: list[dict]) -> str:
    if not have("ANTHROPIC_API_KEY") or not episodes:
        return ""
    top = []
    for ep in episodes:
        for m in ep["moments"]:
            if m["label"] in ("Thesis-changing", "Catalyst-relevant"):
                top.append(f"- [{ep['theme']}/{ep['show']}] {m['headline']}")
    txt = claude_text(
        model=OPUS, max_tokens=700,
        system=("You are briefing a buy-side PM. In 4-7 tight bullets, say WHAT CHANGED this "
                "week across these podcasts that could move a thesis, positioning, or risk — "
                "most important first. No fluff. Ground only in the items."),
        user="This week's thesis/catalyst moments:\n" + "\n".join(top[:30]))
    return (txt or "").strip()


def sample_brief() -> dict:
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "period_days": 7,
        "sample": True, "episodes_count": 0, "moments_count": 0, "clips_count": 0,
        "exec_summary": "SAMPLE — set ANTHROPIC_API_KEY and run curate→transcripts→extract→"
                        "clip→report to populate this with real episodes, reasoning chains, and clips.",
        "facets": {"themes": [], "shows": [], "labels": []},
        "episodes": [],
    }


def main() -> None:
    exs = [read_json(p) for p in sorted(EXTRACTS.glob("*.json"))]
    if not exs:
        write_json(REPORT / "brief-latest.json", sample_brief())
        print("  no extracts yet — wrote a SAMPLE brief (set ANTHROPIC_API_KEY for the real one)")
        return

    manifest = read_json(CLIPS / "manifest.json", {}) or {}
    episodes = []
    for ex in exs:
        moments = [moment_view(m) for m in ex["moments"]]
        moments.sort(key=lambda v: LABEL_RANK.get(v["label"], 9))
        clip_durs = {c["n"]: c["dur"] for c in (manifest.get(ex["id"], {}).get("clips", []))}
        clips = []
        for i, m in enumerate(ex["moments"]):
            if m.get("clip_path"):
                clips.append({"path": m["clip_path"], "label": m["label"],
                              "headline": m["headline"], "start": m.get("start", 0),
                              "dur": clip_durs.get(i)})
        episodes.append({
            "id": ex["id"], "show": ex["show"], "theme": ex["theme"], "title": ex["title"],
            "url": ex.get("url", ""), "published_at": ex.get("published_at", ""),
            "summary": ex.get("episode_summary", ""),
            "reasoning_chain": ex.get("reasoning_chain", []),
            "moments": moments, "clips": clips,
            "n_clip": sum(1 for m in moments if m["delivery"] == "clip"),
        })

    # episodes with the most thesis/catalyst moments first
    def weight(ep):
        return sum(2 if m["label"] == "Thesis-changing" else 1
                   for m in ep["moments"] if m["label"] in ("Thesis-changing", "Catalyst-relevant"))
    episodes.sort(key=weight, reverse=True)

    facets = {
        "themes": sorted({e["theme"] for e in episodes}),
        "shows": sorted({e["show"] for e in episodes}),
        "labels": [l for l in LABEL_RANK if any(m["label"] == l for e in episodes for m in e["moments"])],
    }
    brief = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "period_days": 7,
        "sample": False, "episodes_count": len(episodes),
        "moments_count": sum(len(e["moments"]) for e in episodes),
        "clips_count": sum(e["n_clip"] for e in episodes),
        "exec_summary": exec_summary(episodes), "facets": facets, "episodes": episodes,
    }
    stamp = dt.date.today().isoformat()
    write_json(REPORT / f"brief-{stamp}.json", brief)
    write_json(REPORT / "brief-latest.json", brief)
    _write_markdown(brief, REPORT / f"brief-{stamp}.md")
    print(f"  brief: {brief['episodes_count']} episode(s) · {brief['moments_count']} moments · "
          f"{brief['clips_count']} clip(s) → report/brief-{stamp}.json")


def _write_markdown(brief: dict, path) -> None:
    L = [f"# Buy-Side Podcast Brief — {brief['generated_at'][:10]}", ""]
    if brief.get("exec_summary"):
        L += ["## What changed this week", "", brief["exec_summary"], ""]
    for ep in brief["episodes"]:
        L += [f"## {ep['show']} — {ep['title']}", f"*{ep['theme']}*", ""]
        if ep.get("reasoning_chain"):
            L.append("**Reasoning chain:**")
            for e in ep["reasoning_chain"]:
                L.append(f"- {e['from']} —{e['relation']}→ {e['to']}  _({e['kind']})_")
            L.append("")
        for m in ep["moments"]:
            tag = {"clip": "🎧 CLIP", "summary": "📝", "note": "·"}[m["delivery"]]
            L.append(f"- **{tag} [{m['label']}] {m['headline']}**")
            if m["thesis"]:
                L.append(f"  - Thesis: {m['thesis']}")
            if m["exposures"]:
                L.append(f"  - Exposed: {', '.join(m['exposures'])}"
                         + (f" → 2nd-order: {', '.join(m['second_order'])}" if m["second_order"] else ""))
            if m["watch_next"]:
                L.append(f"  - Watch next: {m['watch_next']}")
        L.append("")
    path.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
