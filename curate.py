#!/usr/bin/env python3
"""Stage 1 — build the worklist of episodes worth processing this period.

Reads the existing theme DBs (built by the scanners), keeps `tier <= max-tier`
episodes published in the last `--days` that have audio + aren't already processed,
then runs a cheap **Claude Haiku** relevance gate on title + show-notes ("could this
materially change a buy-side PM's judgment, positioning, timing, sizing or risk?") to
drop fluff *before* we pay for transcription. Without ANTHROPIC_API_KEY it keeps all
candidates (ungated). Writes work/worklist-<date>.json.

    python curate.py --days 7 --max-tier 2 [--limit N]

(Named curate.py, not select.py — a module named `select` shadows the stdlib `select`
and breaks httpx/asyncio for every script in this directory.)
"""

from __future__ import annotations

import argparse
import datetime as dt
import sqlite3

from briefs_common import EXTRACTS, HAIKU, ROOT, WORK, claude_json, have, write_json

GATE_SYSTEM = (
    "You are screening a podcast episode for a buy-side portfolio manager. Using ONLY the "
    "title and show-notes, decide whether it is likely to contain anything that could change "
    "a PM's investment judgment, positioning, timing, sizing, or risk — a thesis-relevant "
    "claim, a catalyst, a tradable exposure, a non-consensus view, or a credible operator/"
    "investor data point. Generic chit-chat, pure life advice, or recycled consensus with no "
    "new mechanism should be dropped. Be selective; false positives waste transcription."
)
GATE_SCHEMA = {
    "type": "object",
    "properties": {
        "keep": {"type": "boolean"},
        "reason": {"type": "string", "description": "one line: why keep or drop, for a PM"},
        "angle": {"type": "string", "description": "the single most PM-relevant angle, or empty"},
    },
    "required": ["keep", "reason", "angle"],
    "additionalProperties": False,
}


def candidates(days: int, max_tier: int):
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat()
    rows = []
    for db in sorted(ROOT.glob("themes/*/data/insights.db")):
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        for r in conn.execute(
            """SELECT id, firm, source_name, title, url, audio_url, published_at, tier, raw_summary, guid
               FROM items
               WHERE tier <= ? AND audio_url != '' AND published_at >= ?
               ORDER BY published_at DESC""",
            (max_tier, cutoff),
        ):
            rows.append(dict(r))
        conn.close()
    return rows


def gate(ep: dict) -> dict:
    res = claude_json(
        model=HAIKU, schema=GATE_SCHEMA, max_tokens=300, system=GATE_SYSTEM,
        user=f"Show: {ep['source_name']} (theme: {ep['firm']})\nTitle: {ep['title']}\n"
             f"Show-notes: {(ep['raw_summary'] or '(none)')[:1500]}",
    )
    if res is None:  # no key / failure → keep ungated
        return {"keep": True, "reason": "(ungated — no ANTHROPIC_API_KEY)", "angle": ""}
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--max-tier", type=int, default=2)
    ap.add_argument("--limit", type=int, default=None, help="cap candidates (cost control)")
    args = ap.parse_args()

    cands = candidates(args.days, args.max_tier)
    cands = [c for c in cands if not (EXTRACTS / f"{c['id']}.json").exists()]
    if args.limit:
        cands = cands[: args.limit]
    print(f"  {len(cands)} candidate episode(s) (tier<={args.max_tier}, last {args.days}d, with audio)")

    gated = "LLM (Haiku)" if have("ANTHROPIC_API_KEY") else "ungated (no key)"
    print(f"  relevance gate: {gated}")
    kept = []
    for ep in cands:
        g = gate(ep)
        mark = "keep" if g["keep"] else "drop"
        print(f"    [{mark}] {ep['source_name'][:22]:22} · {ep['title'][:52]}")
        if g["keep"]:
            kept.append({
                "id": ep["id"], "theme": ep["firm"], "show": ep["source_name"],
                "title": ep["title"], "url": ep["url"], "audio_url": ep["audio_url"],
                "guid": ep.get("guid", ""),
                "published_at": ep["published_at"], "tier": ep["tier"],
                "shownotes": (ep["raw_summary"] or "")[:4000],
                "angle": g.get("angle", ""), "gate_reason": g["reason"],
            })

    stamp = dt.date.today().isoformat()
    out = WORK / f"worklist-{stamp}.json"
    write_json(out, {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                     "days": args.days, "max_tier": args.max_tier,
                     "candidates": len(cands), "kept": len(kept), "episodes": kept})
    write_json(WORK / "worklist-latest.json", {"path": str(out), "stamp": stamp})
    print(f"  → kept {len(kept)}/{len(cands)} · wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
