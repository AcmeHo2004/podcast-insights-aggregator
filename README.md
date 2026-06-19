# Buy-Side Podcast Radar

A self-updating, theme-grouped dashboard of **34 curated buy-side podcasts** — each
episode gets a 2–3 sentence Claude summary and a **"why it matters for a PM"** line,
plus per-show **feed-freshness (停更) monitoring** so you can see at a glance which
shows are still publishing.

Built for a professional buy-side audience (portfolio manager), with a deliberate
tilt toward **tech / AI verticals** alongside macro, markets, quant and allocators.
It mirrors the architecture of a sibling "investment-firm insights" aggregator but is
a **separate product with a different function** (firm house-views vs. a curated
podcast library).

**Live site:** _(GitHub Pages — see repo Settings → Pages)_

## What it does

- **Single-episode intelligence feed**, grouped into **7 themes** (the columns):

  | Theme (column)       | 中文            | Shows |
  |----------------------|-----------------|------:|
  | Tech & AI            | 科技与行业洞察   | 8 |
  | Companies            | 公司深扒         | 1 |
  | Macro & Rates        | 宏观/利率        | 8 |
  | Investor Talks       | 投资人访谈       | 6 |
  | Strategy & Markets   | 投资策略/市场    | 6 |
  | Quant                | 因子/量化        | 4 |
  | Allocators           | 配置/机构        | 1 |

  Filter by **Tier** (Core / Useful / Optional — the buy-side curation priority),
  **Topic** (macro, rates, ai, tech, crypto, quant, company, …), search, star, and
  copy a Markdown digest. "For You", a cross-theme **Synthesis** rollup, and a
  **Consensus map** are in the Group menu.

- **Feed health (停更监测)** — the "Feed health" link (bottom bar) shows each show's
  last-episode date, inferred cadence, and a status: 🟢 active · 🟡 slipping ·
  🔴 dormant. Recomputed on every daily build by `freshness.py`.

## How it works

- `themes/<slug>/` — independent scanner units (RSS feeds → normalize → dedup →
  enrich with Claude Haiku → SQLite). Each `sources.yaml` lists that theme's
  podcasts. Add a theme by adding a folder; it's auto-discovered.
- `insights_core/` — the shared pipeline engine (config-driven; podcast-native RSS).
- `build_static.py` — exports every theme DB into `site/` (`data.json` + facets +
  the front-end). No backend: the page filters/groups entirely client-side.
- `freshness.py` → `site/freshness.json` (per-show 停更 status).
- `synthesize.py` → `site/synthesis.json` (per-theme "what buy-side podcasts are
  saying about X" rollup; Opus when a key is set, deterministic otherwise).
- `.github/workflows/update.yml` — **daily**: restores the DBs, scans for new
  episodes, rebuilds `site/`, deploys to GitHub Pages, and persists the DBs back to
  a single-commit `data` branch. No always-on machine needed.

**Copyright-safe:** only the episode title + the feed's own show-notes are sent to
the model; we store the *generated* summary, never transcripts or large excerpts.

## Setup — two manual steps (one-time)

1. **`ANTHROPIC_API_KEY`** → repo **Settings → Secrets and variables → Actions →
   New repository secret**. Without it the site still builds (show-notes + keyword
   tags); with it you get the real Claude summaries + PM takeaways.
2. **Pages source** → repo **Settings → Pages → Build and deployment → Source:
   Deploy from a branch → `gh-pages` / root**. (The first workflow run creates the
   `gh-pages` branch.)

Then trigger the first run: **Actions → Update & deploy → Run workflow**.

## Run locally

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
# (optional) export ANTHROPIC_API_KEY=...   # for real summaries; otherwise degraded
for d in themes/*/; do f=$(basename "$d"); ( cd "$d" && python -m "${f}_insights" scan ); done
python build_static.py && python freshness.py && python synthesize.py
python -m http.server -d site 8000      # → http://127.0.0.1:8000
```

For a full 6-month backfill of summaries (uses the Batches API, ~50% cheaper):
`cd themes/<slug> && python -m <slug>_insights backfill --days 180`.

## Notes

- Source of truth for the feed list: `podcasts-buyside-feeds.csv` in the parent
  `Podcast-aggregator/` folder. `enrich_window_days: 180` = the 6-month window.
- Known dormant feed surfaced by the freshness check on first build: **AI Business
  Podcast** (last episode 2024-04 — its matched RSS appears to have stopped). Swap
  its `url` in `themes/tech/sources.yaml` or drop it if undesired.

Change cadence in `.github/workflows/update.yml` (the `cron:` line).
