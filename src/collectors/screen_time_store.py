from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from src.core.tz import now_paris

ROOT_DIR = Path(__file__).resolve().parents[1]
STORE_PATH = ROOT_DIR / "data" / "screen_time_sessions.json"


def load_store() -> dict:
    if not STORE_PATH.exists():
        return {"last_fetched": None, "sessions": []}
    try:
        return json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, KeyError):
        return {"last_fetched": None, "sessions": []}


def save_store(store: dict) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps(store, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def merge_sessions(existing: list[dict], new_sessions: list[dict]) -> tuple[list[dict], int]:
    """
    Merge new sessions into existing ones.
    Deduplication key: (package, start) — two sessions for the same app
    cannot start at the exact same timestamp.
    Returns (merged_list, number_of_new_sessions_added).
    """
    seen = {(s["package"], s["start"]) for s in existing}
    result = list(existing)
    added = 0
    for s in new_sessions:
        key = (s["package"], s["start"])
        if key not in seen:
            seen.add(key)
            result.append(s)
            added += 1
    return result, added


def week_start_dt() -> datetime:
    now = now_paris()
    return (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


def aggregate_week(sessions: list[dict], week_start: datetime | None = None) -> list[dict]:
    """
    Aggregate all sessions that start on or after week_start.
    Returns per-package summary sorted by foreground_minutes descending.
    """
    ws = week_start or week_start_dt()
    # ISO string comparison works correctly for "YYYY-MM-DDTHH:MM:SS" format
    ws_str = ws.strftime("%Y-%m-%dT%H:%M:%S")

    totals: dict[str, dict] = {}
    for s in sessions:
        if s["start"] < ws_str:
            continue
        pkg = s["package"]
        if pkg not in totals:
            totals[pkg] = {
                "package": pkg,
                "name": s["name"],
                "foreground_minutes": 0.0,
                "session_count": 0,
            }
        totals[pkg]["foreground_minutes"] += s["duration_seconds"] / 60
        totals[pkg]["session_count"] += 1

    for pkg in totals:
        totals[pkg]["foreground_minutes"] = round(totals[pkg]["foreground_minutes"], 1)

    return sorted(totals.values(), key=lambda x: x["foreground_minutes"], reverse=True)


def purge_old_sessions(sessions: list[dict], keep_weeks: int = 4) -> list[dict]:
    """Remove sessions older than keep_weeks weeks to keep the store lean."""
    cutoff = week_start_dt() - timedelta(weeks=keep_weeks)
    cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%S")
    return [s for s in sessions if s["start"] >= cutoff_str]
