from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.collectors.intervals_client import IntervalsAPIError, IntervalsClient
from src.collectors.strava_client import StravaAPIError, StravaClient
from src.core.tz import today_paris
from src.database.connection import db_session

_UPSERT_WELLNESS = """
INSERT INTO vigueur_entries
    (date_entry, ctl, atl, tsb, vo2max, hrv, rhr, sleep_min, steps, source, fetched_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'intervals.icu', datetime('now'))
ON CONFLICT(date_entry) DO UPDATE SET
    ctl=COALESCE(excluded.ctl, ctl),
    atl=COALESCE(excluded.atl, atl),
    tsb=COALESCE(excluded.tsb, tsb),
    vo2max=COALESCE(excluded.vo2max, vo2max),
    hrv=COALESCE(excluded.hrv, hrv),
    rhr=COALESCE(excluded.rhr, rhr),
    sleep_min=COALESCE(excluded.sleep_min, sleep_min),
    steps=COALESCE(excluded.steps, steps),
    fetched_at=excluded.fetched_at
"""

_UPSERT_ACTIVITIES = """
INSERT INTO vigueur_entries
    (date_entry, tss, distance_km, moving_time_min, source, fetched_at)
VALUES (?, ?, ?, ?, 'intervals.icu', datetime('now'))
ON CONFLICT(date_entry) DO UPDATE SET
    tss=excluded.tss,
    distance_km=excluded.distance_km,
    moving_time_min=excluded.moving_time_min,
    fetched_at=excluded.fetched_at
"""


def _wellness_to_row(entry: dict) -> tuple:
    def _f(v):
        return round(float(v), 2) if v is not None else None

    ctl = _f(entry.get("ctl"))
    atl = _f(entry.get("atl"))
    # Intervals.icu affiche Form = round(CTL) - round(ATL) — on reproduit ce calcul
    tsb = (
        (round(entry["ctl"]) - round(entry["atl"])) if ctl is not None and atl is not None else None
    )

    sleep_secs = entry.get("sleepSecs")
    steps_raw = entry.get("steps")
    return (
        entry.get("id"),
        ctl,
        atl,
        tsb,
        _f(entry.get("vo2max")),
        _f(entry.get("hrv")),
        _f(entry.get("restingHR")),
        round(float(sleep_secs) / 60, 1) if sleep_secs else None,
        int(steps_raw) if steps_raw is not None else None,
    )


def _aggregate_activities(activities: list[dict]) -> dict[str, tuple]:
    """Group activities by date, sum TSS / distance / moving_time."""
    daily: dict[str, dict] = {}
    for act in activities:
        date = (act.get("start_date_local") or "")[:10]
        if not date:
            continue
        d = daily.setdefault(date, {"tss": 0.0, "dist_m": 0.0, "time_s": 0.0})
        d["tss"] += act.get("icu_training_load") or 0
        d["dist_m"] += act.get("distance") or 0
        d["time_s"] += act.get("moving_time") or 0

    result = {}
    for date, vals in daily.items():
        result[date] = (
            date,
            round(vals["tss"], 1) if vals["tss"] else None,
            round(vals["dist_m"] / 1000, 2) if vals["dist_m"] else None,
            round(vals["time_s"] / 60, 1) if vals["time_s"] else None,
        )
    return result


def _incremental_oldest() -> str | None:
    """Return MAX(date_entry) - 1 day as ISO string, or None if DB is empty."""
    try:
        with db_session() as conn:
            row = conn.execute(
                "SELECT MAX(date_entry) FROM vigueur_entries WHERE source='intervals.icu'"
            ).fetchone()
        if row and row[0]:
            last = datetime.strptime(row[0], "%Y-%m-%d")
            return (last - timedelta(days=1)).strftime("%Y-%m-%d")
    except Exception:
        pass
    return None


def _cascade_current_weeks() -> None:
    """Recalcule semaines_audit pour la semaine en cours + la semaine précédente.

    Corrige le cas où habitude_logs (lecture, jeûne) a été mis à jour depuis
    l'interface mais trigger_cascade_week() n'avait pas encore tourné.
    """
    from src.core.system_engine import get_or_create_week_id, trigger_cascade_week

    today = today_paris()
    for offset in (0, 7):
        date_str = (today - timedelta(days=offset)).isoformat()
        try:
            week_id = get_or_create_week_id(date_str)
            trigger_cascade_week(week_id)
            print(f"[CASCADE] Semaine du {date_str} recalculée.")
        except Exception as exc:
            print(f"[WARN] Cascade {date_str} échouée : {exc}")


def _save_checkpoint(source: str) -> None:
    try:
        with db_session() as conn:
            conn.execute(
                """INSERT INTO sync_checkpoints (source, last_date, updated_at)
                   VALUES (?, ?, datetime('now'))
                   ON CONFLICT(source) DO UPDATE SET
                       last_date  = excluded.last_date,
                       updated_at = excluded.updated_at""",
                (source, today_paris().isoformat()),
            )
    except Exception as exc:
        print(f"[WARN] Checkpoint {source} non sauvegardé : {exc}")


def run(lookback_days: int = 180, incremental: bool = True) -> dict:
    client = IntervalsClient()

    # ── Résolution de la fenêtre temporelle ──────────────────────
    oldest: str | None = None
    if incremental:
        oldest = _incremental_oldest()
        if oldest:
            print(f"[SYNC] Mode incrémental — depuis {oldest}")
        else:
            print(f"[SYNC] Mode incrémental — DB vide, full sync ({lookback_days} j)")

    # ── 1. Wellness → CTL / ATL / TSB / HRV / RHR / Sleep ────────
    entries = client.get_wellness(lookback_days=lookback_days, oldest=oldest)
    wellness_rows = [_wellness_to_row(e) for e in entries if e.get("id")]

    with db_session() as conn:
        conn.executemany(_UPSERT_WELLNESS, wellness_rows)
    print(f"[DB] {len(wellness_rows)} entrées wellness insérées/mises à jour.")

    # ── 2. Activities → TSS / Distance / Durée ───────────────────
    try:
        activities = client.get_activities(lookback_days=lookback_days, oldest=oldest)
        act_rows = list(_aggregate_activities(activities).values())
        with db_session() as conn:
            conn.executemany(_UPSERT_ACTIVITIES, act_rows)
        print(
            f"[DB] {len(act_rows)} jours d'activités insérés/mis à jour ({len(activities)} activités)."
        )
    except IntervalsAPIError as exc:
        print(f"[WARN] Activities sync échoué : {exc}")

    # ── 3. Strava Personal Records → SQLite ─────────────────────
    try:
        print("Syncing Strava Personal Records (best_efforts)...")
        strava = StravaClient()
        n = strava.sync_personal_records(lookback_years=3, incremental=True)
        print(f"[DB] {n} record(s) Strava mis à jour.")
    except StravaAPIError as exc:
        print(f"[WARN] Strava PR sync échoué : {exc}")
    except Exception as exc:
        print(f"[WARN] Strava PR sync erreur inattendue : {exc}")

    # ── 4. Résumé complet de la dernière entrée ──────────────────
    metrics = client.get_latest_metrics()

    with db_session() as conn:
        latest_row = conn.execute(
            """SELECT date_entry, ctl, atl, tsb, vo2max, hrv, rhr,
                      sleep_min, steps, tss, distance_km, moving_time_min
               FROM vigueur_entries
               WHERE source = 'intervals.icu'
               ORDER BY date_entry DESC LIMIT 1"""
        ).fetchone()

    if latest_row:
        r = dict(latest_row)
        ctl_delta = metrics.get("ctl_delta")
        delta_str = f" (Δ7j {ctl_delta:+.1f})" if ctl_delta is not None else ""
        print(f"\nIntervals.icu — {r['date_entry']}")
        print(f"  Forme     CTL={r['ctl']}  ATL={r['atl']}  TSB={r['tsb']}{delta_str}")
        print(f"  Santé     VO2max={r['vo2max']}  HRV={r['hrv']}  RHR={r['rhr']}")
        print(f"  Récup     Sommeil={r['sleep_min']} min  Pas={r['steps']}")
        print(
            f"  Sport     TSS={r['tss']}  Distance={r['distance_km']} km  Durée={r['moving_time_min']} min"
        )

    # ── 5. Cascade rollups + checkpoint ─────────────────────────
    _cascade_current_weeks()
    _save_checkpoint("intervals.icu")

    return {"metrics": metrics, "synced_rows": len(wellness_rows)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync Intervals.icu (wellness + activities) → SQLite."
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Force un sync complet sur --lookback jours (désactive le mode incrémental).",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=180,
        help="Jours d'historique pour un sync complet (défaut : 180). Ignoré en mode incrémental.",
    )
    args = parser.parse_args()

    try:
        run(
            lookback_days=args.lookback,
            incremental=not args.full,
        )
    except IntervalsAPIError as exc:
        print(f"Erreur Intervals.icu : {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
