#!/usr/bin/env python3
"""Stage 7 — deliver: build the public report page + send the weekly email.

Public page (report/site/, deployed to GitHub Pages): exec summary + knowledge graph +
the brief organized by PM decisions + timestamped deep-links to the source. **No audio.**
Email (Resend): the same brief plus the actual ≤90s audio clips for the thesis-changing /
catalyst moments, attached privately.

    python deliver.py                 # build site + write an email PREVIEW (no send)
    python deliver.py --send --to you@example.com   # also send (needs RESEND_API_KEY)
"""

from __future__ import annotations

import argparse
import datetime as dt
import shutil
from pathlib import Path

from briefs_common import CLIPS, REPORT, ROOT, SITE, TRANSCRIPTS, read_json, resend_send

WEB = ROOT / "report_web"


def build_site(public: bool = False) -> None:
    SITE.mkdir(parents=True, exist_ok=True)
    for f in WEB.iterdir():
        if f.is_file():
            shutil.copy(f, SITE / f.name)
    # cache-bust the CSS/JS so a normal refresh always loads the current build
    import time
    ver = int(time.time())
    idx = SITE / "index.html"
    if idx.exists():
        h = idx.read_text(encoding="utf-8")
        h = h.replace('href="report.css"', f'href="report.css?v={ver}"')
        h = h.replace('src="report.js"', f'src="report.js?v={ver}"')
        idx.write_text(h, encoding="utf-8")
    brief = read_json(REPORT / "brief-latest.json")
    if brief:
        (SITE / "brief.json").write_text(__import__("json").dumps(brief, ensure_ascii=False),
                                         encoding="utf-8")
    # Local builds embed the clips so they play in the page. The PUBLIC deploy
    # (--public) never hosts audio — copyright. The email always carries the clips.
    clips_dst = SITE / "clips"
    if clips_dst.exists():
        shutil.rmtree(clips_dst)
    n_local = 0
    if not public:
        mp3s = [m for m in CLIPS.glob("*.mp3") if m.name != "demo.mp3"]
        if mp3s:
            clips_dst.mkdir(parents=True, exist_ok=True)
            for m in mp3s:
                shutil.copy(m, clips_dst / m.name)
            n_local = len(mp3s)
    # Transcripts for the in-page viewer (local jump-to-timestamp; no external site).
    tx_dst = SITE / "transcripts"
    if tx_dst.exists():
        shutil.rmtree(tx_dst)
    n_tx = 0
    if brief and brief.get("episodes"):
        tx_dst.mkdir(parents=True, exist_ok=True)
        for ep in brief["episodes"]:
            src = TRANSCRIPTS / f"{ep['id']}.json"
            if src.exists():
                shutil.copy(src, tx_dst / f"{ep['id']}.json")
                n_tx += 1
    (SITE / ".nojekyll").write_text("", encoding="utf-8")
    print(f"  built report site → {SITE.relative_to(ROOT)} "
          f"({'sample' if (brief or {}).get('sample') else 'real'} brief · "
          f"{'public/no-audio' if public else f'{n_local} clips embedded (local)'})")


def email_html(brief: dict) -> str:
    def esc(s):
        return (str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    P = ['<div style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;max-width:640px;'
         'margin:auto;color:#1a1b1e">']
    P.append(f'<h2 style="margin:0 0 4px">Podcast Brief</h2>'
             f'<div style="color:#7b8090;font-size:12px">{esc(brief.get("generated_at","")[:10])}'
             f' · {brief.get("episodes_count",0)} episodes · {brief.get("moments_count",0)} moments'
             f' · {brief.get("clips_count",0)} clips</div>')
    if brief.get("sample"):
        P.append('<p style="color:#9a6b1f;font-size:13px">SAMPLE — set ANTHROPIC_API_KEY for real content.</p>')
    if brief.get("exec_summary"):
        P.append('<h3 style="margin:18px 0 6px">What changed this week</h3>'
                 f'<div style="white-space:pre-wrap;color:#3a3d44;font-size:14px">{esc(brief["exec_summary"])}</div>')
    for ep in brief.get("episodes", []):
        P.append(f'<h3 style="margin:20px 0 4px;border-top:1px solid #e6e4df;padding-top:12px">'
                 f'{esc(ep["show"])} — {esc(ep["title"])}</h3>'
                 f'<div style="color:#7b8090;font-size:11px;margin-bottom:6px">{esc(ep["theme"])}'
                 + (f' · <a href="{esc(ep["url"])}">listen</a>' if ep.get("url") else "") + '</div>')
        if ep.get("reasoning_chain"):
            steps = " &nbsp;·&nbsp; ".join(
                f'{esc(e["from"])} <span style="color:#9a93a6">—{esc(e["relation"])}→</span> {esc(e["to"])}'
                for e in ep["reasoning_chain"][:10])
            P.append(f'<div style="color:#3a3d44;font-size:12px;margin:0 0 8px">⛓ {steps}</div>')
        for m in ep["moments"]:
            tag = {"clip": "🎧 CLIP", "summary": "📝", "note": "·"}[m["delivery"]]
            P.append(f'<div style="margin:0 0 10px"><b>{tag} [{esc(m["label"])}] {esc(m["headline"])}</b>'
                     f'<div style="color:#3a3d44;font-size:13px">')
            if m.get("thesis"): P.append(f'Thesis: {esc(m["thesis"])}<br>')
            if m.get("exposures"): P.append(f'Exposed: {esc(", ".join(m["exposures"]))}<br>')
            if m.get("watch_next"): P.append(f'Watch next: {esc(m["watch_next"])}<br>')
            P.append('</div></div>')
    P.append('<div style="color:#7b8090;font-size:11px;margin-top:18px">Audio clips of the '
             'thesis-changing / catalyst moments are attached. Full brief on the report page.</div></div>')
    return "".join(P)


def collect_clips(brief: dict, cap: int = 8):
    paths = []
    for ep in brief.get("episodes", []):
        for c in ep.get("clips", []):
            p = ROOT / c["path"]
            if p.exists():
                paths.append(str(p))
    return paths[:cap]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--to", default=None, help="recipient (or set BRIEF_TO)")
    ap.add_argument("--public", action="store_true", help="build the site without audio (public deploy)")
    args = ap.parse_args()

    build_site(public=args.public)
    brief = read_json(REPORT / "brief-latest.json") or {}
    html = email_html(brief)
    clips = collect_clips(brief)
    import os
    to = args.to or os.environ.get("BRIEF_TO", "you@example.com")
    subject = f"Podcast Brief — {dt.date.today().isoformat()}"

    res = resend_send(to=to, subject=subject, html=html, attachments=clips,
                      dry_run=not args.send)
    if res.get("sent"):
        print(f"  email sent to {to} · {len(clips)} clip(s) attached · status {res.get('status')}")
    else:
        print(f"  email NOT sent ({res.get('reason','')}) — preview: report/email-preview.html"
              f" · would attach {len(clips)} clip(s)")


if __name__ == "__main__":
    main()
