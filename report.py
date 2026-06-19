#!/usr/bin/env python3
"""Stage 5 — assemble the analyst brief, organized around PM decisions (not podcasts).

The per-moment PM fields already come structured from extract.py, so the brief is mostly
*assembled* deterministically (grouped by theme, sorted by label priority). Claude Opus
adds only (a) the cross-theme "What changed this week" exec summary and (b) a per-theme
consensus/divergence synthesis. Writes report/brief-<date>.json + .md.

Each item's `delivery` (clip / summary / note) is derived from its label:
  Thesis-changing / Catalyst-relevant → clip (if a clip was cut) else summary
  Risk-relevant   / Consensus-variant → summary
  Background only                      → note

    python report.py

With no extracts yet, writes a clearly-labeled SAMPLE brief so the page renders.
"""

from __future__ import annotations

import datetime as dt

from briefs_common import EXTRACTS, OPUS, REPORT, claude_text, have, read_json, write_json

LABEL_RANK = {"Thesis-changing": 0, "Catalyst-relevant": 1, "Risk-relevant": 2,
              "Consensus-variant": 3, "Background only": 4}


def delivery_of(m: dict) -> str:
    if m["label"] in ("Thesis-changing", "Catalyst-relevant"):
        return "clip" if m.get("clip_path") else "summary"
    if m["label"] in ("Risk-relevant", "Consensus-variant"):
        return "summary"
    return "note"


def item_from_moment(ex: dict, m: dict) -> dict:
    return {
        "label": m["label"], "delivery": delivery_of(m),
        "headline": m["headline"], "quote": m.get("quote", ""),
        "thesis": m.get("thesis", ""), "credible": m.get("credibility", ""),
        "consensus_variant": m.get("variant_vs_consensus", ""),
        "exposures": m.get("exposures", []), "second_order": m.get("second_order", []),
        "catalyst": m.get("catalyst", ""), "risk_direction": m.get("risk_direction", ""),
        "action": m.get("action", ""), "watch_next": m.get("watch_next", ""),
        "show": ex["show"], "title": ex["title"], "url": ex.get("url", ""),
        "start": m.get("start", 0), "clip_path": m.get("clip_path", ""),
    }


def synth_theme(theme: str, items: list[dict]) -> str:
    if not have("ANTHROPIC_API_KEY") or not items:
        return ""
    ev = "\n".join(f"- [{it['show']}] {it['headline']} (thesis: {it['thesis'] or '—'}; "
                   f"variant: {it['consensus_variant'] or '—'})" for it in items[:18])
    txt = claude_text(
        model=OPUS, max_tokens=500,
        system=("You are a buy-side strategist. In 2-4 sentences, synthesize where these "
                "podcast moments AGREE and DISAGREE on this theme, and the single most "
                "important variant-vs-consensus read for a PM. Ground only in the moments."),
        user=f"Theme: {theme}\nMoments:\n{ev}")
    return (txt or "").strip()


def exec_summary(themes: list[dict]) -> str:
    if not have("ANTHROPIC_API_KEY") or not themes:
        return ""
    top = []
    for t in themes:
        for it in t["items"][:3]:
            if it["label"] in ("Thesis-changing", "Catalyst-relevant"):
                top.append(f"- [{t['theme']}/{it['show']}] {it['headline']}")
    txt = claude_text(
        model=OPUS, max_tokens=600,
        system=("You are briefing a buy-side PM. In 4-6 tight bullets, say WHAT CHANGED this "
                "week across these podcasts that could move a thesis, positioning, or risk — "
                "most important first. No fluff, no hedging. Ground only in the items."),
        user="This week's thesis/catalyst moments:\n" + "\n".join(top[:25]))
    return (txt or "").strip()


def sample_brief() -> dict:
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "period_days": 7,
        "sample": True,
        "exec_summary": "SAMPLE — set ANTHROPIC_API_KEY and run curate→transcripts→extract→"
                        "report to populate this with real, PM-relevant moments.",
        "themes": [{
            "theme": "Macro & Rates", "synthesis": "(sample) where speakers agree / disagree appears here.",
            "items": [{
                "label": "Thesis-changing", "delivery": "clip",
                "headline": "(sample) A credible operator flags an inflection that cuts against consensus",
                "quote": "", "thesis": "(sample) affects the long thesis on X",
                "credible": "(sample) speaker is credible for this specific claim because…",
                "consensus_variant": "(sample) differs from sell-side by…",
                "exposures": ["(sample) NVDA", "(sample) power equipment"],
                "second_order": ["(sample) utilities", "(sample) data-center REITs"],
                "catalyst": "(sample) next earnings", "risk_direction": "long",
                "action": "(sample) revisit model assumption / check positioning",
                "watch_next": "(sample) the KPI/print that confirms or falsifies it in 1-8 weeks",
                "show": "Odd Lots", "title": "(sample episode)", "url": "", "start": 0, "clip_path": "",
            }],
        }],
    }


def main() -> None:
    exs = [read_json(p) for p in sorted(EXTRACTS.glob("*.json"))]
    if not exs:
        brief = sample_brief()
        write_json(REPORT / "brief-latest.json", brief)
        print("  no extracts yet — wrote a SAMPLE brief (set ANTHROPIC_API_KEY for the real one)")
        return

    by_theme: dict[str, list[dict]] = {}
    for ex in exs:
        for m in ex["moments"]:
            by_theme.setdefault(ex["theme"], []).append(item_from_moment(ex, m))

    themes = []
    for theme, items in by_theme.items():
        items.sort(key=lambda it: LABEL_RANK.get(it["label"], 9))
        themes.append({"theme": theme, "items": items, "synthesis": synth_theme(theme, items)})
    # themes with the most thesis/catalyst items first
    themes.sort(key=lambda t: sum(1 for it in t["items"]
                                  if it["label"] in ("Thesis-changing", "Catalyst-relevant")),
                reverse=True)

    brief = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "period_days": 7,
        "sample": False, "episodes": len(exs),
        "moments": sum(len(t["items"]) for t in themes),
        "exec_summary": exec_summary(themes), "themes": themes,
    }
    stamp = dt.date.today().isoformat()
    write_json(REPORT / f"brief-{stamp}.json", brief)
    write_json(REPORT / "brief-latest.json", brief)
    _write_markdown(brief, REPORT / f"brief-{stamp}.md")
    clips = sum(1 for t in themes for it in t["items"] if it["delivery"] == "clip")
    print(f"  brief: {len(exs)} episode(s) · {brief['moments']} moments · {clips} clip(s) · "
          f"{len(themes)} theme(s) → report/brief-{stamp}.json")


def _write_markdown(brief: dict, path) -> None:
    L = [f"# Buy-Side Podcast Brief — {brief['generated_at'][:10]}", ""]
    if brief.get("exec_summary"):
        L += ["## What changed this week", "", brief["exec_summary"], ""]
    for t in brief["themes"]:
        L += [f"## {t['theme']}", ""]
        if t.get("synthesis"):
            L += [f"*{t['synthesis']}*", ""]
        for it in t["items"]:
            tag = {"clip": "🎧 CLIP", "summary": "📝", "note": "·"}[it["delivery"]]
            L.append(f"- **{tag} [{it['label']}] {it['headline']}** — {it['show']}")
            if it["thesis"]:
                L.append(f"  - Thesis: {it['thesis']}")
            if it["exposures"]:
                L.append(f"  - Exposed: {', '.join(it['exposures'])}"
                         + (f" → 2nd-order: {', '.join(it['second_order'])}" if it["second_order"] else ""))
            if it["consensus_variant"]:
                L.append(f"  - Variant vs consensus: {it['consensus_variant']}")
            if it["credible"]:
                L.append(f"  - Who/credibility: {it['credible']}")
            if it["watch_next"]:
                L.append(f"  - Watch next: {it['watch_next']}")
        L.append("")
    path.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
