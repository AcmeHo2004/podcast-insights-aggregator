#!/usr/bin/env python3
"""Stage 2 — get a timestamped transcript for each worklisted episode.

Prefers the feed's own Podcasting-2.0 `<podcast:transcript>` (VTT/SRT/JSON, free).
Falls back to downloading the audio enclosure and transcribing via a Whisper-class
API (Groq). Writes work/transcripts/<id>.json = {source, audio_url, segments:[{start,end,text}]}.

    python transcripts.py [--limit N]

No GROQ_API_KEY → feed-transcript episodes still process; the rest are marked
needs_transcription and skipped (re-run once a key is set).
"""

from __future__ import annotations

import argparse
import os
import re
import tempfile
from pathlib import Path

import httpx
import yaml

from briefs_common import ROOT, TRANSCRIPTS, groq_transcribe, have, read_json, write_json

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0"}


def show_feeds() -> dict:
    """show name -> RSS url, from every themes/*/sources.yaml."""
    out = {}
    for sy in sorted(ROOT.glob("themes/*/sources.yaml")):
        doc = yaml.safe_load(sy.read_text(encoding="utf-8")) or {}
        for s in doc.get("sources") or []:
            out[s["name"]] = s["url"]
    return out


def _ts(ts: str) -> float:
    ts = ts.replace(",", ".").strip().split()[0]
    parts = [float(p) for p in ts.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    h, m, s = parts[-3], parts[-2], parts[-1]
    return h * 3600 + m * 60 + s


def parse_vtt_srt(text: str):
    segs = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        tl = next((ln for ln in lines if "-->" in ln), None)
        if not tl:
            continue
        a, _, c = tl.partition("-->")
        try:
            start, end = _ts(a), _ts(c)
        except Exception:  # noqa: BLE001
            continue
        txt = " ".join(lines[lines.index(tl) + 1:]).strip()
        txt = re.sub(r"<[^>]+>", "", txt)  # strip inline cue tags
        if txt and txt.upper() != "WEBVTT":
            segs.append({"start": start, "end": end, "text": txt})
    return segs


def parse_json_transcript(text: str):
    import json
    try:
        j = json.loads(text)
    except Exception:  # noqa: BLE001
        return []
    segs = j.get("segments") if isinstance(j, dict) else (j if isinstance(j, list) else [])
    out = []
    for s in segs or []:
        st = s.get("startTime", s.get("start"))
        en = s.get("endTime", s.get("end"))
        body = s.get("body", s.get("text", ""))
        if st is None or not body:
            continue
        out.append({"start": float(st), "end": float(en) if en is not None else float(st) + 4,
                    "text": str(body).strip()})
    return out


def _item_matches(block: str, ep: dict) -> bool:
    """Identify THIS episode's <item> — GUID first (unique), then the full enclosure
    URL, then the title (raw or HTML-escaped). Filename-only matching is NOT unique
    across a show and grabs the wrong item."""
    import html
    guid = (ep.get("guid") or "").strip()
    if guid and guid in block:
        return True
    audio = (ep.get("audio_url") or "").split("?")[0]
    if audio and len(audio) > 20 and audio in block:
        return True
    title = (ep.get("title") or "")[:50]
    return bool(title) and (title in block or html.escape(title) in block)


def find_feed_transcript_url(feed_url: str, ep: dict):
    """Fetch the show's RSS, find the <item> matching this episode (by GUID/url/title),
    return its <podcast:transcript> href (preferring vtt/srt/json)."""
    try:
        xml = httpx.get(feed_url, headers=UA, timeout=40, follow_redirects=True).text
    except Exception:  # noqa: BLE001
        return None
    for it in re.split(r"<item[ >]", xml)[1:]:
        if not _item_matches(it, ep):
            continue
        trs = re.findall(r'<podcast:transcript\b[^>]*>', it)
        best = None
        for tag in trs:
            url = re.search(r'url="([^"]+)"', tag)
            typ = (re.search(r'type="([^"]+)"', tag) or [None, ""])[1].lower()
            if not url:
                continue
            cand = (url.group(1), typ)
            if any(x in typ for x in ("vtt", "srt", "json")):
                return cand
            best = best or cand
        return best
    return None


def from_feed(ep: dict):
    found = find_feed_transcript_url(ep["_feed"], ep)
    if not found:
        return None
    url, typ = found
    try:
        text = httpx.get(url, headers=UA, timeout=60, follow_redirects=True).text
    except Exception:  # noqa: BLE001
        return None
    segs = parse_json_transcript(text) if ("json" in typ or text.lstrip().startswith("{")) else parse_vtt_srt(text)
    return segs or None


def _download(ep, tmp) -> bool:
    try:
        with httpx.stream("GET", ep["audio_url"], headers=UA, timeout=600, follow_redirects=True) as r:
            r.raise_for_status()
            for chunk in r.iter_bytes(1 << 16):
                tmp.write(chunk)
        tmp.flush()
        return True
    except Exception as e:  # noqa: BLE001
        print(f"    download failed: {e}")
        return False


def from_whisper(ep: dict):
    if not have("GROQ_API_KEY") or not ep.get("audio_url"):
        return None
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=True) as tmp:
        if not _download(ep, tmp):
            return None
        return groq_transcribe(tmp.name)


# Lazy-loaded local model (free, no API/key). `pip install faster-whisper`.
_WHISPER = None


def _whisper_model():
    global _WHISPER
    if _WHISPER is None:
        from faster_whisper import WhisperModel
        name = os.environ.get("WHISPER_MODEL", "base")   # tiny|base|small|medium|large-v3
        _WHISPER = WhisperModel(name, device="cpu", compute_type="int8")
    return _WHISPER


def from_local_whisper(ep: dict):
    """Free, fully local transcription via faster-whisper. No key, no cost (just CPU
    time). Returns timestamped segments, or None if the package isn't installed."""
    if not ep.get("audio_url"):
        return None
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return None
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=True) as tmp:
        if not _download(ep, tmp):
            return None
        try:
            segs, _ = _whisper_model().transcribe(tmp.name)
            return [{"start": float(s.start), "end": float(s.end), "text": (s.text or "").strip()}
                    for s in segs]
        except Exception as e:  # noqa: BLE001
            print(f"    local whisper failed: {e}")
            return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    ptr = read_json(ROOT / "work/worklist-latest.json")
    wl = read_json(ptr["path"]) if ptr else None
    if not wl:
        print("  no worklist — run select.py first"); return
    feeds = show_feeds()
    eps = wl["episodes"][: args.limit] if args.limit else wl["episodes"]

    have_local = False
    try:
        import faster_whisper  # noqa: F401
        have_local = True
    except ImportError:
        pass

    done = skipped = 0
    counts = {"feed": 0, "groq": 0, "local-whisper": 0}
    for ep in eps:
        out = TRANSCRIPTS / f"{ep['id']}.json"
        if out.exists():
            done += 1; continue
        ep["_feed"] = feeds.get(ep["show"], "")
        segs, src = from_feed(ep), "feed"
        if not segs:
            segs, src = from_whisper(ep), "groq"
        if not segs and os.environ.get("NO_LOCAL_WHISPER") != "1":
            segs, src = from_local_whisper(ep), "local-whisper"
        if not segs:
            skipped += 1
            why = "no GROQ key & faster-whisper not installed" if not (have("GROQ_API_KEY") or have_local) else "transcription failed"
            print(f"    [skip] {ep['show'][:22]:22} · {ep['title'][:42]}  (no feed transcript; {why})")
            continue
        write_json(out, {"id": ep["id"], "show": ep["show"], "theme": ep["theme"],
                         "title": ep["title"], "audio_url": ep.get("audio_url", ""),
                         "source": src, "duration": round(segs[-1]["end"], 1),
                         "segments": segs})
        counts[src] = counts.get(src, 0) + 1
        print(f"    [{src:13}] {ep['show'][:22]:22} · {len(segs):>4} segs · {ep['title'][:40]}")

    print(f"  done: {counts['feed']} feed · {counts['groq']} groq · {counts['local-whisper']} local-whisper · "
          f"{skipped} skipped · {done} cached")


if __name__ == "__main__":
    main()
