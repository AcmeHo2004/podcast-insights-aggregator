#!/usr/bin/env python3
"""Export every theme's SQLite DB into a static site/ folder (data.json + facets
+ the front-end assets) that GitHub Pages can serve with no backend.

Buy-side podcast product: the top grouping is the THEME (the `firm` column in the
shared schema = a theme like "Macro & Rates"), each podcast is a `source_name`,
and `tier` (Core/Useful/Optional) becomes the business-line facet. Read/star state
is per-viewer (localStorage), so the export carries content only.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
import sqlite3
from collections import defaultdict
from pathlib import Path

from insights_core.models import TOPICS

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
SITE = ROOT / "site"

# First paint ships only the last RECENT_DAYS (all themes); older episodes lazy-load
# from data-archive.json on demand — keeps the first download small (full podcast
# back-catalogues run to thousands of episodes).
RECENT_DAYS = 180          # 6-month default view

# Theme brand metadata (display name + accent + order). The `firm` field in each
# DB holds the theme display name; add a line here when you add a theme.
THEME_META = {
    "Tech & AI":          {"short": "Tech", "color": "#6E59D9", "order": 1},
    "Companies":          {"short": "Co.",  "color": "#B8733A", "order": 2},
    "Macro & Rates":      {"short": "Macro","color": "#B0894F", "order": 3},
    "Investor Talks":     {"short": "Talks","color": "#3FB8C4", "order": 4},
    "Strategy & Markets": {"short": "Strat","color": "#D8584E", "order": 5},
    "Quant":              {"short": "Quant","color": "#1E8E5A", "order": 6},
    "Allocators":         {"short": "Alloc","color": "#5A6B8C", "order": 7},
}
DEFAULT = {"short": "", "color": "#8A93A6", "order": 99}
HIDDEN_FIRMS: set[str] = set()       # no hidden themes

# Top-level tabs. key -> display label, in display order.
CATEGORIES = [("markets", "Markets & Investors"), ("tech", "Tech & Companies")]
THEME_CATEGORY = {
    "Macro & Rates": "markets", "Investor Talks": "markets",
    "Strategy & Markets": "markets", "Quant": "markets", "Allocators": "markets",
    "Tech & AI": "tech", "Companies": "tech",
}

# tier (int) -> the "business line" facet label (curation priority).
TIER_LABEL = {1: "Core", 2: "Useful", 3: "Optional"}
BUSINESS_LINES = ["Core", "Useful", "Optional"]


def tier_label(tier) -> str:
    try:
        return TIER_LABEL.get(int(tier), "Optional")
    except (TypeError, ValueError):
        return "Optional"


def collapse_clusters(rows: list[dict]) -> list[dict]:
    """Collapse cross-channel near-duplicates the pipeline already clustered.
    The dedup step stamps every clustered item with `cluster_id` = the canonical
    (earliest-published) member's id; singletons point at themselves. Keep one card
    per cluster (the canonical), and borrow a readable/playable link from a dropped
    member if the canonical lacks one, so we don't lose the alternate feed."""
    present = {d["id"] for d in rows}
    groups: dict[str, list[dict]] = defaultdict(list)
    for d in rows:
        cid = d.get("cluster_id") or ""
        key = cid if (cid and cid in present) else d["id"]
        groups[key].append(d)

    kept: list[dict] = []
    for key, members in groups.items():
        if len(members) == 1:
            kept.append(members[0])
            continue
        canon = next((d for d in members if d["id"] == key), None)
        if canon is None:          # canonical not in this DB — keep members as-is
            kept.extend(members)
            continue
        for d in members:
            if d is canon:
                continue
            if not canon.get("url") and d.get("url"):
                canon["url"] = d["url"]
            if not canon.get("audio_url") and d.get("audio_url"):
                canon["audio_url"] = d["audio_url"]
        kept.append(canon)
    return kept


def load():
    items, themes = [], {}
    collapsed = 0
    for db in sorted(ROOT.glob("themes/*/data/insights.db")):
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        fr = conn.execute("SELECT firm FROM items WHERE firm != '' LIMIT 1").fetchone()
        if not fr:
            conn.close()
            continue
        theme = fr[0]
        if theme in HIDDEN_FIRMS:
            conn.close()
            continue
        meta = THEME_META.get(theme, DEFAULT)
        category = THEME_CATEGORY.get(theme, "markets")
        themes[theme] = {"firm": theme, "short": meta["short"] or theme[:4],
                         "color": meta["color"], "order": meta["order"], "category": category}
        rows = [dict(r) for r in conn.execute("SELECT * FROM items")]
        kept = collapse_clusters(rows)
        collapsed += len(rows) - len(kept)
        for d in kept:
            items.append({
                "id": d["id"], "firm": theme, "firm_short": themes[theme]["short"], "color": meta["color"],
                "category": category,
                "business_unit": tier_label(d["tier"]),
                "source_name": d["source_name"],
                "content_type": d["content_type"], "title": d["title"],
                "url": d["url"] or "", "audio_url": d["audio_url"] or "",
                "published_at": d["published_at"], "ingested_at": d["ingested_at"],
                "summary": d["llm_summary"] or d["raw_summary"] or "",
                "is_llm": bool(d["llm_summary"]), "why_it_matters": d["why_it_matters"] or "",
                "topics": json.loads(d["topics"]) if d["topics"] else [],
                "asset_class": json.loads(d["asset_class"]) if d["asset_class"] else [],
                "tier": d["tier"],
            })
        conn.close()
    items.sort(key=lambda it: (it["published_at"] or it["ingested_at"] or ""), reverse=True)
    themes_list = sorted(themes.values(), key=lambda f: (f["order"], f["firm"]))
    return items, themes_list, collapsed


def collect_health(stale_hours: int = 30) -> dict:
    """Aggregate every theme's `data/last_run.json` (written by the core pipeline)
    into a single scan-health view: which themes reported, which had failed feeds,
    which returned zero items, which are stale. (Per-SHOW publishing freshness —
    "is this podcast still updating?" — is a separate view written by freshness.py.)"""
    now = dt.datetime.now(dt.timezone.utc)
    firms_health = []
    for rep_path in sorted(ROOT.glob("themes/*/data/last_run.json")):
        try:
            r = json.loads(rep_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — a missing/corrupt report shouldn't break the build
            continue
        ended = r.get("ended_at")
        age_h = None
        if ended:
            try:
                age_h = round((now - dt.datetime.fromisoformat(ended)).total_seconds() / 3600, 1)
            except ValueError:
                pass
        firms_health.append({
            "firm": r.get("firm", rep_path.parts[-3]),
            "ended_at": ended,
            "age_hours": age_h,
            "duration_s": r.get("duration_s"),
            "sources_total": r.get("sources_total", 0),
            "sources_ok": r.get("sources_ok", 0),
            "sources_failed": r.get("sources_failed", 0),
            "failed_sources": [{"name": s["name"], "error": s["error"]}
                               for s in r.get("sources", []) if not s.get("ok")],
            "new_items": r.get("new_items", 0),
            "total": r.get("total", 0),
            "enriched_total": r.get("enriched_total", 0),
            "enrich_llm_ok": r.get("enrich_llm_ok", 0),
            "llm_available": r.get("llm_available", False),
            "stale": (age_h is not None and age_h > stale_hours),
        })
    firms_health.sort(key=lambda h: (-h["sources_failed"], -(h["total"] or 0)))
    summary = {
        "firms_reporting": len(firms_health),
        "firms_with_failures": sum(1 for h in firms_health if h["sources_failed"]),
        "firms_zero_items": sum(1 for h in firms_health if not h["total"]),
        "firms_stale": sum(1 for h in firms_health if h["stale"]),
        "failed_sources": sum(h["sources_failed"] for h in firms_health),
    }
    return {"generated_at": now.isoformat(), "summary": summary, "firms": firms_health}


def write_feed(items: list[dict], site: Path, limit: int = 50) -> int:
    """RSS 2.0 of the latest episodes — a backend-free subscribe/digest channel
    (point any reader at site/feed.xml). The daily workflow regenerates it."""
    from email.utils import format_datetime
    from xml.sax.saxutils import escape

    def rfc822(iso):
        try:
            return format_datetime(dt.datetime.fromisoformat(iso))
        except (ValueError, TypeError):
            return ""

    entries = []
    for it in items[:limit]:
        link = it["url"] or it["audio_url"]
        if not link:
            continue
        when = rfc822(it["published_at"] or it["ingested_at"])
        desc = f'{it["firm"]} · {it["source_name"]} — {it.get("summary", "")}'
        entries.append(
            "<item>"
            f"<title>{escape(it['title'])}</title>"
            f"<link>{escape(link)}</link>"
            f"<guid isPermaLink=\"false\">{escape(it['id'])}</guid>"
            f"<dc:creator>{escape(it['source_name'])}</dc:creator>"
            f"<description>{escape(desc)}</description>"
            + (f"<pubDate>{when}</pubDate>" if when else "")
            + "</item>"
        )
    now = format_datetime(dt.datetime.now(dt.timezone.utc))
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        "<channel>"
        "<title>Buy-Side Podcast Radar</title>"
        "<link>./index.html</link>"
        "<description>Curated buy-side podcasts, by theme — episode summaries with a why-it-matters-for-a-PM line.</description>"
        f"<lastBuildDate>{now}</lastBuildDate>"
        + "".join(entries)
        + "</channel></rss>\n"
    )
    (site / "feed.xml").write_text(xml, encoding="utf-8")
    return len(entries)


def main():
    items, themes, collapsed = load()
    present_units = {it["business_unit"] for it in items if it["business_unit"]}
    units = [b for b in BUSINESS_LINES if b in present_units]
    types = sorted({it["content_type"] for it in items if it["content_type"]})
    present_cats = {it["category"] for it in items}
    categories = [{"key": k, "label": lbl} for k, lbl in CATEGORIES if k in present_cats]

    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir(parents=True)
    for f in WEB.iterdir():
        if f.is_file():
            shutil.copy(f, SITE / f.name)

    # "Recent" = episodes with a REAL publish date inside the window; undated items
    # go to the archive instead of flooding the default view stamped "today".
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=RECENT_DAYS)).isoformat()
    recent, archive = [], []
    for it in items:
        (recent if (it["published_at"] or "") >= cutoff else archive).append(it)
    (SITE / "data.json").write_text(
        json.dumps(recent, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (SITE / "data-archive.json").write_text(
        json.dumps(archive, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (SITE / "facets.json").write_text(
        json.dumps({"firms": themes, "categories": categories, "business_units": units,
                    "content_types": types, "topics": TOPICS},
                   ensure_ascii=False), encoding="utf-8")
    feed_n = write_feed(items, SITE)
    health = collect_health()
    (SITE / "health.json").write_text(
        json.dumps(health, ensure_ascii=False), encoding="utf-8")
    (SITE / "meta.json").write_text(
        json.dumps({"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "count": len(items), "recent_count": len(recent),
                    "archive_count": len(archive), "window_days": RECENT_DAYS,
                    "health": health["summary"]}),
        encoding="utf-8")
    (SITE / ".nojekyll").write_text("", encoding="utf-8")
    h = health["summary"]
    print(f"built site/ — {len(items)} episodes across {len(themes)} themes"
          + (f" ({collapsed} collapsed)" if collapsed else "")
          + f" · {len(recent)} recent + {len(archive)} archive · feed.xml {feed_n}")
    if h["firms_reporting"]:
        print(f"  scan health: {h['firms_reporting']} themes reported · "
              f"{h['firms_with_failures']} with failed feeds · "
              f"{h['firms_zero_items']} zero-item · {h['firms_stale']} stale · "
              f"{h['failed_sources']} failed feed(s)")


if __name__ == "__main__":
    main()
