# Buy-Side Podcast Brief

An **importance-driven** engine over 34 curated buy-side podcasts. It doesn't make you
scroll a feed — it finds what could change a PM's **judgment, positioning, timing, sizing,
or risk**, then:

- **cuts a real audio clip** of the sharpest (thesis-changing / catalyst) moments,
- **summarizes the key points** for everything else,
- **aggregates the views** into an **analyst-style brief** + a **knowledge graph**,

and delivers a **report page** (text + graph) plus a **weekly email** (with the clips).

> Pivoted from a browse-dashboard (now in `legacy/`) after PM feedback: *a professional
> only spends time on useful content.* The report is organized around **PM decisions, not
> podcast structure.**

## The PM Attention Model (what counts as "important")

Each moment is scored on: thesis impact · novelty vs consensus · tradable exposure ·
catalyst/timing · risk & sizing · disagreement/variant perception · speaker credibility
*for that specific claim* · second-order implications · actionability · what to watch next
(1–8 weeks). It then gets **one label** that decides delivery:

| Label | Delivery |
|---|---|
| Thesis-changing / Catalyst-relevant | 🎧 audio clip + full brief treatment |
| Risk-relevant / Consensus-variant | short summary |
| Background only | one line |
| Drop | discarded |

The brief is written around: **What changed this week → which thesis → who said it & why
credible → consensus vs disagreement → companies/assets exposed (incl. second-order) →
what to watch next → clip / summary / no action.**

## Pipeline

```
curate.py      tier≤2, last N days, Haiku relevance gate              → work/worklist.json
transcripts.py feed podcast:transcript (free) else Whisper (Groq)     → work/transcripts/
extract.py     Claude Opus + PM Attention Model → labeled moments      → work/extracts/
clip.py        ffmpeg cuts clip-worthy moments (≤90s, private)         → clips/
report.py      Opus exec-summary + per-theme synthesis; assemble brief → report/brief-*.json/.md
graph.py       aggregate entities+claims → knowledge graph             → report/site/graph.json
deliver.py     build report page + send weekly email (clips attached)  → report/site/ + email
```

`insights_core/` + `themes/*/` (the 34-feed RSS ingestion) are reused unchanged. The
report page lives in `report_web/`.

## Setup — keys (Actions secrets / local `.env`)

| Secret | For | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | relevance gate, extraction, brief, graph | required for real output |
| `GROQ_API_KEY` | Whisper transcription for feeds without transcripts | Groq has a free tier; optional |
| `RESEND_API_KEY` + `BRIEF_TO` (+ `BRIEF_SENDER`) | the weekly email | verify a Resend sender |

**Transcription order (free-first):** feed `podcast:transcript` (free) → Groq Whisper (if
`GROQ_API_KEY`) → **local Whisper, fully free & offline** (`pip install faster-whisper`; set
`WHISPER_MODEL=tiny|base|small`, default `base`). Local Whisper needs no key and no money —
just CPU time — so the tech shows that don't publish transcripts (All-In, BG2, Sharp Tech)
still get in. Use Groq in CI for speed; local Whisper for free local runs.

Everything **degrades gracefully**: no key → that stage is skipped/sampled, never crashes.
Enable the weekly run: add the secrets, then `gh auth refresh -h github.com -s workflow`
and push `.github/workflows/brief.yml`; set **Pages → Source → `gh-pages`**.

## Copyright

The repo is public, so **cut audio is never committed or hosted** — `clips/` is gitignored;
the public page carries text + graph + **timestamped deep-links to the source** (which drive
listens back to the original). The ≤90s clips ship **privately in the weekly email** only.

## Run locally

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
# export ANTHROPIC_API_KEY=...  GROQ_API_KEY=...   # for real output
python curate.py --days 7 --max-tier 2
python transcripts.py
python extract.py        # needs ANTHROPIC_API_KEY
python clip.py           # or: python clip.py --demo   (cuts one real clip, no key)
python report.py && python graph.py && python deliver.py   # --send --to you@x.com to email
python -m http.server -d report/site 8000     # → the report page
```

No-key proof points: `transcripts.py` parses free feed transcripts; `clip.py --demo` cuts a
real ≤90s mp3 with ffmpeg. The Claude stages need `ANTHROPIC_API_KEY`.

Change cadence in `.github/workflows/brief.yml` (the `cron:` line). The old browse-dashboard
is preserved under `legacy/`.
