from __future__ import annotations

from datetime import timedelta

import requests

from src.config import get_secret
from src.core.tz import today_local

INTERVALS_API_BASE = "https://intervals.icu/api/v1"


class IntervalsAPIError(RuntimeError):
    pass


class IntervalsClient:
    def __init__(
        self,
        athlete_id: str | None = None,
        api_key: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.athlete_id = athlete_id or get_secret("intervals_icu", "athlete_id")
        resolved_key = api_key or get_secret("intervals_icu", "api_key")
        if not self.athlete_id:
            raise IntervalsAPIError("Missing secret: intervals_icu.athlete_id")
        if not resolved_key:
            raise IntervalsAPIError("Missing secret: intervals_icu.api_key")
        # Intervals.icu HTTP Basic auth: username="API_KEY", password=<key>
        self._auth = ("API_KEY", resolved_key)
        self.timeout = timeout

    def _get(self, path: str, params: dict | None = None) -> dict | list:
        try:
            response = requests.get(
                f"{INTERVALS_API_BASE}{path}",
                auth=self._auth,
                params=params,
                timeout=self.timeout,
            )
        except requests.ConnectionError as exc:
            raise IntervalsAPIError(f"Connection error reaching Intervals.icu: {exc}") from exc
        except requests.Timeout as exc:
            raise IntervalsAPIError(
                f"Timeout reaching Intervals.icu after {self.timeout}s"
            ) from exc
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            try:
                payload = response.json()
            except ValueError:
                payload = response.text
            raise IntervalsAPIError(
                f"Intervals.icu HTTP {response.status_code} on {path}: {payload}"
            ) from exc
        return response.json()

    def get_wellness(
        self,
        oldest: str | None = None,
        newest: str | None = None,
        lookback_days: int = 7,
    ) -> list[dict]:
        today = today_local()
        params = {
            "oldest": oldest or (today - timedelta(days=lookback_days)).isoformat(),
            "newest": newest or today.isoformat(),
        }
        result = self._get(f"/athlete/{self.athlete_id}/wellness", params=params)
        if not isinstance(result, list):
            raise IntervalsAPIError(f"Unexpected wellness response format: {type(result)}")
        return result

    def _get_athlete_vo2max(self) -> float | None:
        try:
            profile = self._get(f"/athlete/{self.athlete_id}")
            return profile.get("vo2max") if isinstance(profile, dict) else None
        except IntervalsAPIError:
            return None

    def get_latest_metrics(self) -> dict:
        """
        Return a clean dict with CTL, ATL, TSB, VO2max and CTL week-over-week delta.
        Fetches 21 days so we always have both the current and the J-7 reference.
        Raises IntervalsAPIError on connection or data issues.
        """
        from datetime import date as _date

        entries = self.get_wellness(lookback_days=21)

        # Index entries by date string, keep only those with CTL data
        by_date: dict[str, dict] = {e["id"]: e for e in entries if e.get("ctl") is not None}

        if not by_date:
            raise IntervalsAPIError("No wellness entries with CTL data found in the last 21 days.")

        latest_date_str = max(by_date)
        latest = by_date[latest_date_str]

        ctl_raw = latest.get("ctl")
        atl_raw = latest.get("atl")
        ctl = round(float(ctl_raw), 2) if ctl_raw is not None else None
        atl = round(float(atl_raw), 2) if atl_raw is not None else None
        tsb = round(ctl - atl, 2) if ctl is not None and atl is not None else None

        # CTL delta : current vs 7 days ago (closest available entry on or before J-7)
        ctl_delta: float | None = None
        if ctl is not None:
            prev_target = (_date.fromisoformat(latest_date_str) - timedelta(days=7)).isoformat()
            candidates = [d for d in by_date if d <= prev_target]
            if candidates:
                ctl_prev = round(float(by_date[max(candidates)]["ctl"]), 2)
                ctl_delta = round(ctl - ctl_prev, 2)

        vo2max_raw = latest.get("vo2max") or self._get_athlete_vo2max()
        vo2max = round(float(vo2max_raw), 2) if vo2max_raw is not None else None

        hrv_raw = latest.get("hrv")
        rhr_raw = latest.get("rhr")
        sleep_raw = latest.get("sleep")
        hrv = round(float(hrv_raw), 1) if hrv_raw is not None else None
        rhr = round(float(rhr_raw), 1) if rhr_raw is not None else None
        sleep_min = round(float(sleep_raw), 1) if sleep_raw is not None else None

        return {
            "ctl": ctl,
            "atl": atl,
            "tsb": tsb,
            "ctl_delta": ctl_delta,
            "vo2max": vo2max,
            "hrv": hrv,
            "rhr": rhr,
            "sleep_min": sleep_min,
            "source_date": latest_date_str,
        }

    def get_activities(
        self,
        oldest: str | None = None,
        newest: str | None = None,
        lookback_days: int = 180,
    ) -> list[dict]:
        """Return activities list with distance, moving_time and icu_training_load."""
        today = today_local()
        params = {
            "oldest": oldest or (today - timedelta(days=lookback_days)).isoformat(),
            "newest": newest or today.isoformat(),
        }
        result = self._get(f"/athlete/{self.athlete_id}/activities", params=params)
        if not isinstance(result, list):
            raise IntervalsAPIError(f"Unexpected activities response: {type(result)}")
        return result

    def get_activity_detail(self, activity_id: str) -> dict:
        """Return full detail for a single activity (type, name, start_date_local, icu_training_load, …)."""
        result = self._get(f"/athlete/{self.athlete_id}/activities/{activity_id}")
        if not isinstance(result, dict):
            raise IntervalsAPIError(f"Unexpected activity detail response: {type(result)}")
        return result

    def sync_personal_records(self, lookback_days: int = 365) -> None:
        """
        Parse l'historique des activités Run et extrait les meilleures performances
        sur 1 km, 5 km et 10 km via le champ best_intervals d'Intervals.icu.
        Persiste les résultats dans vigueur_personal_records (INSERT OR REPLACE).
        """
        from src.database.connection import db_session

        activities = self.get_activities(lookback_days=lookback_days)
        run_activities = [a for a in activities if a.get("type") == "Run"]

        target_distances: list[int] = [1000, 5000, 10000]
        best_records: dict[int, dict[str, object]] = {}

        for activity in run_activities:
            intervals = activity.get("best_intervals", [])
            for item in intervals:
                dist = item.get("distance")
                duration = item.get("time")
                if dist in target_distances and duration:
                    existing = best_records.get(dist)
                    if existing is None or duration < existing["duree_sec"]:
                        best_records[dist] = {
                            "duree_sec": int(duration),
                            "date": (activity.get("start_date_local") or "")[:10],
                        }

        with db_session() as conn:
            for dist, data in best_records.items():
                conn.execute(
                    """
                    INSERT OR REPLACE INTO vigueur_personal_records
                        (distance_m, duree_sec, date_realisation, source)
                    VALUES (?, ?, ?, 'intervals')
                    """,
                    (float(dist), data["duree_sec"], data["date"]),
                )

    def _post(self, path: str, data: dict | None = None) -> dict | list:
        try:
            response = requests.post(
                f"{INTERVALS_API_BASE}{path}",
                auth=self._auth,
                json=data,
                timeout=self.timeout,
            )
        except requests.ConnectionError as exc:
            raise IntervalsAPIError(f"Connection error: {exc}") from exc
        except requests.Timeout as exc:
            raise IntervalsAPIError(f"Timeout after {self.timeout}s") from exc
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            try:
                payload = response.json()
            except ValueError:
                payload = response.text
            raise IntervalsAPIError(f"HTTP {response.status_code} on {path}: {payload}") from exc
        return response.json() if response.content else {}

    def trigger_sync(self) -> dict:
        """Déclenche une synchronisation Intervals.icu depuis les sources connectées.

        Équivalent du bouton « Sync » dans l'interface Intervals.icu.
        """
        return self._post(f"/athlete/{self.athlete_id}/sync")

    def get_recovery_7d(self) -> list[dict]:
        """Last 7 days of HRV, RHR and sleep from wellness."""
        entries = self.get_wellness(lookback_days=7)
        result = []
        for e in entries:
            hrv_raw = e.get("hrv")
            rhr_raw = e.get("rhr")
            sleep_raw = e.get("sleep")
            result.append(
                {
                    "date": e.get("id"),
                    "hrv": round(float(hrv_raw), 1) if hrv_raw is not None else None,
                    "rhr": round(float(rhr_raw), 1) if rhr_raw is not None else None,
                    "sleep_min": round(float(sleep_raw), 1) if sleep_raw is not None else None,
                }
            )
        return sorted(result, key=lambda x: x["date"] or "")
