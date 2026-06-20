#!/usr/bin/env python3
"""Stage 4 — cut a real audio clip for each clip-worthy moment.

Only Thesis-changing / Catalyst-relevant moments flagged clip_worthy get a clip.
ffmpeg seeks into the episode's audio enclosure (range requests — no full download),
loudness-normalizes, and writes a ≤90s mp3 to clips/ (gitignored / private — never
committed or hosted publicly; clips ship in the weekly email). Records clips/manifest.json
and stamps clip_path back into each extract.

    python clip.py [--limit N]
    python clip.py --demo        # no key needed: cut one 60s clip from a real transcript

Needs ffmpeg (present). Needs the audio enclosure to be reachable.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from briefs_common import CLIPS, EXTRACTS, ROOT, TRANSCRIPTS, read_json, write_json

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0"
CLIP_LABELS = {"Thesis-changing", "Catalyst-relevant"}
PRE_ROLL = 3.0
MAX_LEN = 210.0   # up to ~3.5 min; the moment's own span drives the actual length
MIN_LEN = 15.0


def _ffprobe_dur(path) -> float:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=30).stdout.strip()
        return float(out)
    except Exception:  # noqa: BLE001
        return 0.0


def cut(audio_url: str, start: float, end: float, out: Path) -> float:
    """Cut [start-PRE_ROLL, +duration] from audio_url → out (mp3). Returns the clip
    duration in seconds (0.0 on failure)."""
    start = max(0.0, float(start) - PRE_ROLL)
    dur = min(MAX_LEN, max(MIN_LEN, float(end) - float(start)))
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-user_agent", UA,
        "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
        "-ss", f"{start:.2f}", "-i", audio_url, "-t", f"{dur:.2f}",
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-ac", "1", "-c:a", "libmp3lame", "-b:a", "96k",
        str(out),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except Exception as e:  # noqa: BLE001
        print(f"      ffmpeg error: {e}"); return 0.0
    if r.returncode != 0 or not out.exists():
        print(f"      ffmpeg failed: {r.stderr.strip()[:160]}"); return 0.0
    return round(_ffprobe_dur(out), 1)


def demo() -> int:
    trs = sorted(TRANSCRIPTS.glob("*.json"))
    if not trs:
        print("  no transcripts — run curate.py + transcripts.py first"); return 1
    tr = read_json(trs[0])
    segs = tr["segments"]
    mid = segs[len(segs) // 3]            # a real moment ~1/3 into the episode
    out = CLIPS / "demo.mp3"
    print(f"  demo clip from: {tr['show']} — {tr['title']}")
    print(f"  audio: {tr['audio_url'][:80]}")
    print(f"  window: {mid['start']:.0f}s → {mid['start']+60:.0f}s")
    d = cut(tr["audio_url"], mid["start"], mid["start"] + 60, out)
    if d:
        print(f"  ✓ wrote {out.relative_to(ROOT)} · {d}s · {out.stat().st_size//1024} KB")
        print(f"    segment text: “{mid['text'][:90]}”")
        return 0
    print("  ✗ clip failed"); return 1


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()
    if args.demo:
        raise SystemExit(demo())

    exs = sorted(EXTRACTS.glob("*.json"))
    exs = exs[: args.limit] if args.limit else exs
    if not exs:
        print("  no extracts — run extract.py first (needs ANTHROPIC_API_KEY). "
              "Try `python clip.py --demo` to verify the cut mechanism with no key."); return

    manifest, n_clips = {}, 0
    for p in exs:
        ex = read_json(p)
        if not ex.get("audio_url"):
            continue
        clips = []
        for i, m in enumerate(ex["moments"]):
            if not (m.get("clip_worthy") and m["label"] in CLIP_LABELS):
                continue
            out = CLIPS / f"{ex['id']}-{i}.mp3"
            d = cut(ex["audio_url"], m["start"], m["end"], out)
            if not d:
                continue
            m["clip_path"] = str(out.relative_to(ROOT))
            clips.append({"n": i, "label": m["label"], "headline": m["headline"],
                          "start": m["start"], "end": m["end"], "dur": d,
                          "path": str(out.relative_to(ROOT))})
            n_clips += 1
            print(f"    ✓ {ex['show'][:18]:18} · {d:>4}s · {m['headline'][:50]}")
        if clips:
            manifest[ex["id"]] = {"show": ex["show"], "title": ex["title"], "clips": clips}
            write_json(p, ex)  # persist clip_path back
    write_json(CLIPS / "manifest.json", manifest)
    print(f"  cut {n_clips} clip(s) across {len(manifest)} episode(s) → clips/ (private)")


if __name__ == "__main__":
    main()
