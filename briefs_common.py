"""Shared config, paths, and API clients for the importance-driven brief pipeline.

All *intelligence* is Claude (Anthropic). Transcription is audio→text only and uses a
Whisper-class API (Groq by default). Email uses Resend. Every external dependency
degrades gracefully: a missing key means that stage is skipped or falls back — it never
crashes the run.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "work"
TRANSCRIPTS = WORK / "transcripts"
EXTRACTS = WORK / "extracts"
CLIPS = ROOT / "clips"
REPORT = ROOT / "report"
SITE = REPORT / "site"
for _d in (WORK, TRANSCRIPTS, EXTRACTS, CLIPS, REPORT, SITE):
    _d.mkdir(parents=True, exist_ok=True)

# Model IDs (current, per the claude-api skill).
OPUS = "claude-opus-4-8"
HAIKU = "claude-haiku-4-5"


def _load_env() -> None:
    """Minimal .env loader (project root + parent), only sets keys not already in env."""
    for p in (ROOT / ".env", ROOT.parent / ".env"):
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


_load_env()


def have(key: str) -> bool:
    return bool(os.environ.get(key))


# ── Claude ────────────────────────────────────────────────────────────────────
_anth = None


def claude():
    global _anth
    if _anth is None and have("ANTHROPIC_API_KEY"):
        import anthropic

        _anth = anthropic.Anthropic()
    return _anth


def _first_text(content) -> str:
    return next((b.text for b in content if getattr(b, "type", "") == "text"), "")


def claude_json(*, model: str, system: str, user: str, schema: dict, max_tokens: int = 3000):
    """One structured-JSON call (output_config.format). Returns a dict, or None if no key
    / on failure. Caller handles the None (degraded mode)."""
    c = claude()
    if c is None:
        return None
    try:
        resp = c.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        return json.loads(_first_text(resp.content))
    except Exception as e:  # noqa: BLE001 — degrade, never crash the pipeline
        print(f"    claude_json error: {e}")
        return None


def claude_text(*, model: str, system: str, user: str, max_tokens: int = 8000):
    """Long-form text via streaming (avoids HTTP timeouts on large max_tokens).
    Returns str, or None if no key / on failure."""
    c = claude()
    if c is None:
        return None
    try:
        with c.messages.stream(
            model=model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
        ) as s:
            return _first_text(s.get_final_message().content)
    except Exception as e:  # noqa: BLE001
        print(f"    claude_text error: {e}")
        return None


# ── Groq Whisper (transcription only; audio → text) ────────────────────────────
def groq_transcribe(audio_path, *, model: str = "whisper-large-v3-turbo"):
    """Transcribe a local audio file → list[{start,end,text}] via Groq's
    OpenAI-compatible endpoint. None if no key / on failure."""
    if not have("GROQ_API_KEY"):
        return None
    import httpx

    try:
        with open(audio_path, "rb") as f:
            r = httpx.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
                files={"file": (Path(audio_path).name, f, "audio/mpeg")},
                data={"model": model, "response_format": "verbose_json",
                      "timestamp_granularities[]": "segment"},
                timeout=600,
            )
        r.raise_for_status()
        segs = r.json().get("segments", [])
        return [{"start": float(s["start"]), "end": float(s["end"]),
                 "text": (s.get("text") or "").strip()} for s in segs]
    except Exception as e:  # noqa: BLE001
        print(f"    groq_transcribe error: {e}")
        return None


# ── Resend (weekly email; clips delivered privately here, never on the public site) ──
def resend_send(*, to, subject: str, html: str, attachments=None, sender: str | None = None,
                dry_run: bool = False) -> dict:
    sender = sender or os.environ.get("BRIEF_SENDER", "Podcast Briefs <onboarding@resend.dev>")
    to_list = [to] if isinstance(to, str) else list(to)
    if dry_run or not have("RESEND_API_KEY"):
        (REPORT / "email-preview.html").write_text(html, encoding="utf-8")
        return {"sent": False, "reason": "dry_run" if dry_run else "no RESEND_API_KEY",
                "preview": str(REPORT / "email-preview.html"),
                "attachments": [str(a) for a in (attachments or [])]}
    import base64
    import httpx

    payload = {"from": sender, "to": to_list, "subject": subject, "html": html}
    if attachments:
        payload["attachments"] = [
            {"filename": Path(a).name, "content": base64.b64encode(Path(a).read_bytes()).decode()}
            for a in attachments
        ]
    r = httpx.post("https://api.resend.com/emails",
                   headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}",
                            "Content-Type": "application/json"},
                   json=payload, timeout=90)
    return {"sent": r.status_code < 300, "status": r.status_code, "body": r.text[:300]}


# ── small shared helpers ───────────────────────────────────────────────────────
def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def write_json(path, obj) -> None:
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
