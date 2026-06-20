#!/usr/bin/env python3
"""Stage 3 — extract PM-relevant moments from each transcript (the PM Attention Model).

Claude Opus reads the timestamped transcript and returns, per episode: an episode
summary, key_points, a knowledge-graph slice (entities + claims), and a list of
`moments` — each scored against the PM Attention Model and given ONE label that
decides delivery downstream:

    Thesis-changing / Catalyst-relevant  → clip candidate + full brief treatment
    Risk-relevant   / Consensus-variant  → short brief summary
    Background only                       → one light line
    Drop                                  → discarded

Writes work/extracts/<id>.json. Needs ANTHROPIC_API_KEY; without it, no-op (prints how
to enable).

    python extract.py [--limit N]
"""

from __future__ import annotations

import argparse

from briefs_common import EXTRACTS, OPUS, TRANSCRIPTS, claude_json, have, read_json, write_json

SYSTEM = (
    "You are a buy-side analyst extracting only what could change a portfolio manager's "
    "judgment, positioning, timing, sizing, or risk from a podcast transcript. Apply the PM "
    "Attention Model: a moment matters if it (1) confirms/weakens/reverses a thesis, (2) is "
    "non-obvious vs the market narrative, (3) maps to a tradable exposure, (4) carries a "
    "catalyst/timing, (5) changes risk or sizing, (6) is a variant perception / disagreement, "
    "(7) comes from a speaker credible for THAT specific claim, (8) implies second-order "
    "winners/losers, (9) is actionable, (10) has a clear thing to watch next (1-8 weeks). "
    "Be ruthless: most of a podcast is Background or Drop. Only label a moment Thesis-changing "
    "or Catalyst-relevant if it is genuinely sharp and tradable. Use the transcript's [mm:ss] "
    "markers for start/end (seconds); set them to the NATURAL span of that specific point so the "
    "clip is self-contained (typically 30-180s) — do not force a fixed length or pad with "
    "unrelated talk. Quote at most ~15 words verbatim. Ground every field in the transcript; "
    "never invent numbers, tickers, or positions.\n"
    "Also build a CONNECTED financial reasoning chain for THIS episode: 6-14 directed edges "
    "that link the key driver(s) → mechanism → first-order effect → second-order effects → "
    "exposed names → what to watch. Reuse the SAME node phrase across edges so the chain "
    "actually connects into a logic graph (not scattered fragments). Keep node phrases short "
    "(<=6 words)."
)

LABELS = ["Thesis-changing", "Catalyst-relevant", "Risk-relevant", "Consensus-variant",
          "Background only", "Drop"]

SCHEMA = {
    "type": "object",
    "properties": {
        "episode_summary": {"type": "string", "description": "2-3 sentences, PM-oriented"},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "moments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "number"}, "end": {"type": "number"},
                    "label": {"type": "string", "enum": LABELS},
                    "headline": {"type": "string", "description": "one line: what was said"},
                    "quote": {"type": "string", "description": "<=15 words verbatim"},
                    "thesis": {"type": "string", "description": "thesis it confirms/weakens/reverses, or ''"},
                    "exposures": {"type": "array", "items": {"type": "string"}},
                    "second_order": {"type": "array", "items": {"type": "string"}},
                    "catalyst": {"type": "string"},
                    "risk_direction": {"type": "string",
                                       "enum": ["long", "short", "uncertainty", "neutral"]},
                    "credibility": {"type": "string", "description": "speaker credibility for THIS claim"},
                    "variant_vs_consensus": {"type": "string"},
                    "action": {"type": "string", "description": "what a PM can do with it"},
                    "watch_next": {"type": "string", "description": "confirm/falsify in 1-8 weeks"},
                    "clip_worthy": {"type": "boolean"},
                },
                "required": ["start", "end", "label", "headline", "quote", "thesis", "exposures",
                             "second_order", "catalyst", "risk_direction", "credibility",
                             "variant_vs_consensus", "action", "watch_next", "clip_worthy"],
                "additionalProperties": False,
            },
        },
        "entities": {
            "type": "array",
            "items": {"type": "object", "properties": {
                "name": {"type": "string"},
                "type": {"type": "string", "enum": ["company", "person", "asset", "sector", "theme", "macro"]},
            }, "required": ["name", "type"], "additionalProperties": False},
        },
        "claims": {
            "type": "array",
            "items": {"type": "object", "properties": {
                "subject": {"type": "string"},
                "stance": {"type": "string", "enum": ["bullish", "bearish", "neutral", "disagrees", "exposed-to"]},
                "object": {"type": "string"},
                "by": {"type": "string", "description": "who said it"},
            }, "required": ["subject", "stance", "object", "by"], "additionalProperties": False},
        },
        "reasoning_chain": {
            "type": "array",
            "description": "the episode's financial logic as connected directed cause→effect edges",
            "items": {"type": "object", "properties": {
                "from": {"type": "string", "description": "<=6 words"},
                "relation": {"type": "string",
                             "enum": ["drives", "raises", "lowers", "pressures", "benefits",
                                      "erodes", "implies", "raises-risk-to", "watch"]},
                "to": {"type": "string", "description": "<=6 words"},
                "kind": {"type": "string",
                         "enum": ["driver", "mechanism", "first-order", "second-order",
                                  "risk", "catalyst", "watch", "exposure"]},
            }, "required": ["from", "relation", "to", "kind"], "additionalProperties": False},
        },
    },
    "required": ["episode_summary", "key_points", "moments", "entities", "claims", "reasoning_chain"],
    "additionalProperties": False,
}


def chunk_transcript(segments, *, window: float = 18.0, max_chars: int = 240) -> str:
    """Condense segments into ~window-second lines prefixed with [mm:ss] so the model can
    cite timestamps without paying for one line per ~3-second segment."""
    lines, buf, t0, last = [], [], None, None

    def flush():
        if buf and t0 is not None:
            mm, ss = divmod(int(t0), 60)
            lines.append(f"[{mm:02d}:{ss:02d}] " + " ".join(buf))

    for s in segments:
        if t0 is None:
            t0 = s["start"]
        buf.append(s["text"])
        last = s["end"]
        if (last - t0) >= window or sum(len(x) for x in buf) >= max_chars:
            flush(); buf, t0 = [], None
    flush()
    return "\n".join(lines)


def extract_one(tr: dict) -> dict | None:
    body = chunk_transcript(tr["segments"])
    user = (f"Show: {tr['show']}  ·  Theme: {tr['theme']}\nEpisode: {tr['title']}\n"
            f"Duration: {tr.get('duration', '?')}s\n\nTRANSCRIPT (timestamped):\n{body}")
    return claude_json(model=OPUS, system=SYSTEM, schema=SCHEMA, max_tokens=8000, user=user)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    if not have("ANTHROPIC_API_KEY"):
        print("  ANTHROPIC_API_KEY not set — extraction needs Claude. "
              "Set it (or add to .env) and re-run."); return

    trs = sorted(TRANSCRIPTS.glob("*.json"))
    trs = trs[: args.limit] if args.limit else trs
    n_ok = n_moments = 0
    for p in trs:
        out = EXTRACTS / p.name
        if out.exists():
            continue
        tr = read_json(p)
        res = extract_one(tr)
        if not res:
            print(f"    [fail] {tr['title'][:50]}"); continue
        keep = [m for m in res["moments"] if m["label"] != "Drop"]
        res["moments"] = keep
        res.update({"id": tr["id"], "show": tr["show"], "theme": tr["theme"],
                    "title": tr["title"], "audio_url": tr.get("audio_url", ""),
                    "url": tr.get("url", "")})
        write_json(out, res)
        n_ok += 1
        n_moments += len(keep)
        labels = {}
        for m in keep:
            labels[m["label"]] = labels.get(m["label"], 0) + 1
        tag = " ".join(f"{k.split()[0]}:{v}" for k, v in sorted(labels.items()))
        print(f"    [ok] {tr['show'][:18]:18} · {len(keep):>2} moments ({tag}) · {tr['title'][:40]}")
    print(f"  extracted {n_ok} episode(s) · {n_moments} kept moment(s)")


if __name__ == "__main__":
    main()
