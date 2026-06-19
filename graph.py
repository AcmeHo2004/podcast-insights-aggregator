#!/usr/bin/env python3
"""Stage 6 — aggregate the extracted entities + claims into a knowledge graph.

Deterministic (the LLM already produced entities/claims in extract.py). Nodes are
companies / people / assets / sectors / themes / macro; edges encode bullish / bearish /
neutral / disagrees / exposed-to between them, attributed to the speaker. Writes
report/site/graph.json for the force-graph on the report page.

    python graph.py

With no extracts yet, writes a small SAMPLE graph so the page renders.
"""

from __future__ import annotations

import datetime as dt

from briefs_common import EXTRACTS, SITE, read_json, write_json

STANCE_COLOR = {"bullish": "#1e8e5a", "bearish": "#d8584e", "disagrees": "#b0894f",
                "exposed-to": "#6E59D9", "neutral": "#8A93A6"}
TYPE_COLOR = {"company": "#6E59D9", "person": "#3FB8C4", "asset": "#1e8e5a",
              "sector": "#B8733A", "theme": "#D8584E", "macro": "#B0894F"}


def _norm(name: str) -> str:
    return (name or "").strip()


def build() -> dict:
    nodes: dict[str, dict] = {}
    links = []

    def add_node(name, ntype="theme"):
        k = _norm(name)
        if not k:
            return None
        n = nodes.get(k)
        if n is None:
            nodes[k] = {"id": k, "type": ntype, "val": 1, "color": TYPE_COLOR.get(ntype, "#8A93A6")}
        else:
            n["val"] += 1
            if n["type"] == "theme" and ntype != "theme":   # upgrade a guessed type
                n["type"] = ntype; n["color"] = TYPE_COLOR.get(ntype, n["color"])
        return k

    for p in sorted(EXTRACTS.glob("*.json")):
        ex = read_json(p)
        for e in ex.get("entities", []):
            add_node(e.get("name"), e.get("type", "theme"))
        for c in ex.get("claims", []):
            s, o = add_node(c.get("subject")), add_node(c.get("object"))
            if not s or not o or s == o:
                continue
            stance = c.get("stance", "neutral")
            links.append({"source": s, "target": o, "stance": stance,
                          "color": STANCE_COLOR.get(stance, "#8A93A6"),
                          "by": c.get("by", ""), "show": ex.get("show", "")})

    return {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "sample": False,
            "nodes": list(nodes.values()), "links": links}


def sample() -> dict:
    nodes = [{"id": n, "type": t, "val": v, "color": TYPE_COLOR[t]} for n, t, v in [
        ("AI capex", "theme", 4), ("Nvidia", "company", 3), ("Power equipment", "sector", 2),
        ("Data-center REITs", "sector", 2), ("Jensen Huang", "person", 1), ("Rates", "macro", 2)]]
    links = [
        {"source": "AI capex", "target": "Nvidia", "stance": "exposed-to", "color": STANCE_COLOR["exposed-to"], "by": "(sample)", "show": "BG2"},
        {"source": "AI capex", "target": "Power equipment", "stance": "exposed-to", "color": STANCE_COLOR["exposed-to"], "by": "(sample)", "show": "Odd Lots"},
        {"source": "Jensen Huang", "target": "Nvidia", "stance": "bullish", "color": STANCE_COLOR["bullish"], "by": "(sample)", "show": "All-In"},
    ]
    return {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "sample": True,
            "nodes": nodes, "links": links}


def main() -> None:
    g = build() if any(EXTRACTS.glob("*.json")) else sample()
    write_json(SITE / "graph.json", g)
    tag = "SAMPLE" if g["sample"] else f"{len(g['nodes'])} nodes · {len(g['links'])} edges"
    print(f"  graph.json — {tag}")


if __name__ == "__main__":
    main()
