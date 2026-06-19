#!/usr/bin/env python3
"""Per-show publishing freshness → site/freshness.json  ("is this podcast still
updating?").

For every show across every theme DB, derive its natural cadence from recent
inter-episode gaps, then flag it active / slipping / dormant based on how long it
has been since the last episode relative to that cadence. Pure computation — no
LLM, no network — so it's cheap to run on every daily build. Run AFTER the scans
(reads each theme's DB); writes into the existing site/.

    active   — last episode within ~1.5× its usual gap (and ≤ 45d)
    slipping — overdue but < ~3× the usual gap (and ≤ 90d)
    dormant  — > 3× the usual gap, or no episode in 90+ days  → likely 停更
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"

RECENT_EPISODES = 10      # episodes used to estimate cadence
ACTIVE_MULT = 1.5         # within this × median gap → active
SLIP_MULT = 3.0           # within this × median gap → slipping; beyond → dormant
ACTIVE_CAP_DAYS = 45      # hard ceiling for "active" regardless of a long cadence
DORMANT_DAYS = 90         # no episode in this many days → dormant outright
MIN_BUFFER_DAYS = 12      # don't flag a weekly show that's a few days late


def _parse(iso: str):
    if not iso:
        return None
    try:
        d = dt.datetime.fromisoformat(iso)
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except (ValueError, TypeError):
        return None


def _status(days_since: float, cadence: float | None):
    if days_since >= DORMANT_DAYS:
        return "dormant"
    if cadence is None:                      # too few episodes to know cadence
        return "active" if days_since < 45 else "slipping"
    active_thresh = min(max(cadence * ACTIVE_MULT, MIN_BUFFER_DAYS), ACTIVE_CAP_DAYS)
    slip_thresh = min(max(cadence * SLIP_MULT, 30), DORMANT_DAYS)
    if days_since <= active_thresh:
        return "active"
    if days_since <= slip_thresh:
        return "slipping"
    return "dormant"


def collect() -> dict:
    now = dt.datetime.now(dt.timezone.utc)
    since_180 = (now - dt.timedelta(days=180)).isoformat()
    shows: list[dict] = []

    for db in sorted(ROOT.glob("themes/*/data/insights.db")):
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        theme_row = conn.execute("SELECT firm FROM items WHERE firm != '' LIMIT 1").fetchone()
        theme = theme_row[0] if theme_row else db.parts[-3]
        names = [r[0] for r in conn.execute(
            "SELECT DISTINCT source_name FROM items WHERE source_name != ''")]
        for name in names:
            rows = conn.execute(
                "SELECT published_at, tier FROM items WHERE source_name = ? "
                "AND published_at IS NOT NULL AND published_at != '' "
                "ORDER BY published_at DESC", (name,)).fetchall()
            dates = [d for d in (_parse(r[0]) for r in rows) if d]
            tier = rows[0]["tier"] if rows else 3
            ep180 = conn.execute(
                "SELECT COUNT(*) FROM items WHERE source_name = ? AND published_at >= ?",
                (name, since_180)).fetchone()[0]
            if not dates:
                shows.append({"show": name, "theme": theme, "tier": tier,
                              "last_episode_at": None, "days_since": None,
                              "cadence_days": None, "status": "unknown",
                              "episodes_180d": ep180})
                continue
            last = dates[0]
            days_since = round((now - last).total_seconds() / 86400, 1)
            recent = dates[:RECENT_EPISODES]
            gaps = [(recent[i] - recent[i + 1]).total_seconds() / 86400
                    for i in range(len(recent) - 1)]
            cadence = round(statistics.median(gaps), 1) if len(gaps) >= 2 else None
            shows.append({
                "show": name, "theme": theme, "tier": tier,
                "last_episode_at": last.date().isoformat(),
                "days_since": days_since,
                "cadence_days": cadence,
                "status": _status(days_since, cadence),
                "episodes_180d": ep180,
            })
        conn.close()

    order = {"dormant": 0, "slipping": 1, "unknown": 2, "active": 3}
    shows.sort(key=lambda s: (order.get(s["status"], 9), -(s["days_since"] or 0)))
    summary = {
        "shows": len(shows),
        "active": sum(1 for s in shows if s["status"] == "active"),
        "slipping": sum(1 for s in shows if s["status"] == "slipping"),
        "dormant": sum(1 for s in shows if s["status"] == "dormant"),
        "unknown": sum(1 for s in shows if s["status"] == "unknown"),
    }
    return {"generated_at": now.isoformat(), "summary": summary, "shows": shows}


def main() -> None:
    payload = collect()
    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / "freshness.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    s = payload["summary"]
    print(f"freshness.json — {s['shows']} shows · {s['active']} active · "
          f"{s['slipping']} slipping · {s['dormant']} dormant"
          + (f" · {s['unknown']} unknown" if s["unknown"] else ""))


if __name__ == "__main__":
    main()
