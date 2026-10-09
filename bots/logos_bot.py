from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.collectors.screen_time_client import get_screen_time_summary
from src.collectors.screen_time_store import load_store, week_start_dt
from src.database.connection import db_session

_UPSERT_SESSION = """
INSERT INTO screen_sessions (package, app_name, session_start, session_end, duration_seconds)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(package, session_start) DO UPDATE SET
    session_end      = excluded.session_end,
    duration_seconds = excluded.duration_seconds
"""


def _run_manual() -> dict:
    """Saisie manuelle du temps d'écran pour la semaine en cours (audit hebdomadaire)."""
    from src.core.system_engine import get_or_create_week_id, trigger_cascade_week
    from src.core.tz import today_local as _today

    print("── Saisie manuelle du temps d'écran ──")
    total_raw = input("Temps d'écran total (minutes) : ").strip()
    total = round(float(total_raw), 1)

    apps_raw = input("Top apps (ex: YouTube 120, Instagram 45) [Entrée pour passer] : ").strip()
    top_apps_text = apps_raw or None

    week_id = get_or_create_week_id(_today().isoformat())
    with db_session() as conn:
        conn.execute(
            """UPDATE semaines_audit
               SET screen_time_min = ?, top_apps_text = ?, updated_at = datetime('now')
               WHERE id = ?""",
            (total, top_apps_text, week_id),
        )
    print(f"[DB] Temps d'écran mis à jour : {total} min")
    if top_apps_text:
        print(f"[DB] Top apps : {top_apps_text}")

    trigger_cascade_week(week_id)
    print("[CASCADE] Rollups semaine recalculés.")

    return {"screen_time_min": total, "top_apps_text": top_apps_text}


def run(host: str | None = None, top_n: int = 5) -> dict:
    """Fetch Samsung screen time via ADB and merge into the persistent store."""
    summary = get_screen_time_summary(host=host, top_n=top_n)
    total = summary["total_screen_time_minutes"]
    top_apps = summary["top_apps"]
    added = summary["new_sessions_added"]

    print(
        f"Temps d'écran semaine : {total} min ({round(total / 60, 1)} h) "
        f"— {added} nouvelles sessions ajoutées au store."
    )
    for app in top_apps:
        print(f"  {app['name']:<30} {app['foreground_minutes']} min")

    # Sync current-week sessions from JSON store → SQLite
    store = load_store()
    ws_str = week_start_dt().strftime("%Y-%m-%dT%H:%M:%S")
    week_rows = [
        (s["package"], s["name"], s["start"], s["end"], s["duration_seconds"])
        for s in store["sessions"]
        if s["start"] >= ws_str
    ]
    if week_rows:
        with db_session() as conn:
            conn.executemany(_UPSERT_SESSION, week_rows)
        print(f"[DB] {len(week_rows)} sessions écran insérées/mises à jour.")

    # ── Cascade rollups ──────────────────────────────────────────
    # Recalcule sessions_lecture / sessions_jeune dans semaines_audit
    # pour que l'UI reflète immédiatement les habitudes saisies ce jour.
    try:
        from src.core.system_engine import get_or_create_week_id, trigger_cascade_week
        from src.core.tz import today_local as _today

        week_id = get_or_create_week_id(_today().isoformat())
        trigger_cascade_week(week_id)
        print("[CASCADE] Rollups semaine recalculés.")
    except Exception as exc:
        print(f"[WARN] Cascade échouée : {exc}")

    return {"summary": summary}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Récupère les stats Samsung via ADB WiFi et les stocke en base."
    )
    parser.add_argument(
        "--host",
        default=None,
        help="IP du Samsung (ex: 192.168.1.42). Remplace SAMSUNG_ADB_HOST (secrets.env).",
    )
    parser.add_argument("--top-n", type=int, default=5, help="Nombre d'apps à lister.")
    parser.add_argument(
        "--manual",
        action="store_true",
        help="Saisie manuelle du temps d'écran pour la semaine en cours (sans ADB).",
    )
    args = parser.parse_args()
    if args.manual:
        _run_manual()
    else:
        run(host=args.host, top_n=args.top_n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
