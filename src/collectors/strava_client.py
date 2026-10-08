from __future__ import annotations

import secrets
import threading
import time
import webbrowser
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from src.config import get_secret
from src.database.connection import db_session

STRAVA_API_BASE = "https://www.strava.com/api/v3"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
_REQUIRED_SCOPES = "read,activity:read_all"
_REDIRECT_HOST = "127.0.0.1"
_REDIRECT_PORT = 8080

_RUN_SPORT_TYPES = {"Run", "TrailRun", "VirtualRun"}

# Noms des best_efforts Strava → distance en mètres (Strava utilise la casse "1K", "5K", "10K")
_EFFORT_TARGETS: dict[str, float] = {
    "1K": 1000.0,
    "5K": 5000.0,
    "10K": 10000.0,
}


class StravaAPIError(RuntimeError):
    pass


class StravaClient:
    def __init__(self, timeout: float = 15.0) -> None:
        self.client_id = get_secret("strava", "client_id")
        self.client_secret = get_secret("strava", "client_secret")
        self.timeout = timeout

    # ── Token management ──────────────────────────────────────────

    def _load_cached_token(self) -> dict[str, Any] | None:
        """Retourne le token SQLite. access_token=None si expiré mais refresh_token disponible."""
        with db_session() as conn:
            row = conn.execute(
                "SELECT access_token, refresh_token, expires_at FROM strava_oauth_tokens WHERE id = 1"
            ).fetchone()
        if not row:
            return None
        still_valid = int(row["expires_at"]) > int(time.time()) + 60
        return {
            "access_token": row["access_token"] if still_valid else None,
            "refresh_token": row["refresh_token"],
        }

    def _persist_token(self, access_token: str, refresh_token: str, expires_at: int) -> None:
        with db_session() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO strava_oauth_tokens "
                "(id, access_token, refresh_token, expires_at) VALUES (1, ?, ?, ?)",
                (access_token, refresh_token, expires_at),
            )

    def _do_refresh(self, refresh_token: str) -> dict[str, Any]:
        resp = requests.post(
            STRAVA_TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=self.timeout,
        )
        try:
            resp.raise_for_status()
        except requests.HTTPError as exc:
            raise StravaAPIError(f"Token refresh failed: {resp.text[:300]}") from exc
        return resp.json()

    def _get_valid_token(self) -> str:
        cached = self._load_cached_token()

        if cached and cached["access_token"]:
            return cached["access_token"]

        # Refresh : SQLite d'abord, sinon secrets
        refresh_token = cached["refresh_token"] if cached else get_secret("strava", "refresh_token")
        data = self._do_refresh(refresh_token)
        new_access: str = data["access_token"]
        new_refresh: str = data.get("refresh_token", refresh_token)
        expires_at: int = data.get("expires_at", int(time.time()) + 21600)
        self._persist_token(new_access, new_refresh, expires_at)
        return new_access

    # ── OAuth re-authorization flow ───────────────────────────────

    def authorize(self, server_timeout: float = 180.0) -> None:
        """
        Lance le flux OAuth Strava avec serveur local de callback.
        Ouvre le navigateur sur l'URL d'autorisation et attend le retour.
        Persiste les nouveaux tokens (scope: read,activity:read_all) en SQLite.
        """
        state = secrets.token_urlsafe(16)
        redirect_uri = f"http://{_REDIRECT_HOST}:{_REDIRECT_PORT}/exchange_token"
        auth_url = f"{STRAVA_AUTHORIZE_URL}?" + urlencode(
            {
                "client_id": self.client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "approval_prompt": "force",
                "scope": _REQUIRED_SCOPES,
                "state": state,
            }
        )

        _result: dict[str, str] = {}
        _error: dict[str, str] = {}
        _expected_state = state

        class _CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path != "/exchange_token":
                    self.send_response(404)
                    self.end_headers()
                    return
                query = parse_qs(parsed.query)
                if query.get("state", [""])[0] != _expected_state:
                    _error["msg"] = "State mismatch"
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"State mismatch - fermez cet onglet.")
                    return
                if "error" in query:
                    _error["msg"] = query["error"][0]
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"Autorisation refusee.")
                    return
                _result["code"] = query.get("code", [""])[0]
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Autorisation Strava confirmee. Vous pouvez fermer cet onglet.")

            def log_message(self, *_: object) -> None:
                return

        server = HTTPServer((_REDIRECT_HOST, _REDIRECT_PORT), _CallbackHandler)
        server.timeout = 1

        def _serve() -> None:
            deadline = time.time() + server_timeout
            while time.time() < deadline and not _result and not _error:
                server.handle_request()

        thread = threading.Thread(target=_serve, daemon=True)
        thread.start()

        print(f"\nOuvrez ce lien dans votre navigateur :\n{auth_url}\n")
        try:
            webbrowser.open(auth_url)
        except Exception:
            pass

        thread.join(server_timeout + 1)
        server.server_close()

        if _error:
            raise StravaAPIError(f"Autorisation echouee : {_error.get('msg')}")
        code = _result.get("code", "")
        if not code:
            raise StravaAPIError("Aucun code d'autorisation recu (timeout ?).")

        resp = requests.post(
            STRAVA_TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "grant_type": "authorization_code",
            },
            timeout=self.timeout,
        )
        try:
            resp.raise_for_status()
        except requests.HTTPError as exc:
            raise StravaAPIError(f"Echange de code echoue : {resp.text[:300]}") from exc

        data = resp.json()
        self._persist_token(
            data["access_token"],
            data["refresh_token"],
            data.get("expires_at", int(time.time()) + 21600),
        )
        print(f"Tokens Strava sauvegardes. Scopes accordes : {data.get('scope', 'inconnu')}")

    # ── HTTP ──────────────────────────────────────────────────────

    @staticmethod
    def _seconds_to_next_strava_window() -> int:
        """Secondes jusqu'a la prochaine fenetre de 15 minutes (reset Strava)."""
        now = datetime.now(UTC)
        elapsed_in_window = (now.minute % 15) * 60 + now.second
        return max(10, (15 * 60) - elapsed_in_window + 5)

    def _get(self, path: str, params: dict | None = None, _retries: int = 12) -> Any:
        token = self._get_valid_token()
        try:
            resp = requests.get(
                f"{STRAVA_API_BASE}{path}",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
                timeout=self.timeout,
            )
        except requests.ConnectionError as exc:
            raise StravaAPIError(f"Connection error: {exc}") from exc
        except requests.Timeout as exc:
            raise StravaAPIError(f"Timeout after {self.timeout}s") from exc

        if resp.status_code == 401:
            # Distingue scope manquant (non-retryable) d'un token expire (retryable)
            try:
                body = resp.json()
            except ValueError:
                body = {}
            errors = body.get("errors", [])
            if any(e.get("code") == "missing" for e in errors):
                raise StravaAPIError("Scope insuffisant — lancez : python main.py strava-auth")
            if _retries > 0:
                refresh_token = get_secret("strava", "refresh_token")
                data = self._do_refresh(refresh_token)
                self._persist_token(
                    data["access_token"],
                    data.get("refresh_token", refresh_token),
                    data.get("expires_at", int(time.time()) + 21600),
                )
                return self._get(path, params=params, _retries=_retries - 1)

        if resp.status_code == 429:
            if _retries <= 0:
                raise StravaAPIError("Rate limit persistant apres plusieurs fenetres.")
            wait_sec = self._seconds_to_next_strava_window()
            usage = resp.headers.get("X-RateLimit-Usage", "?")
            print(
                f"  [Rate limit 429 — usage {usage}] Pause {wait_sec}s jusqu'a la prochaine fenetre...",
                flush=True,
            )
            time.sleep(wait_sec)
            return self._get(path, params=params, _retries=_retries - 1)

        try:
            resp.raise_for_status()
        except requests.HTTPError as exc:
            raise StravaAPIError(f"HTTP {resp.status_code} sur {path}: {resp.text[:200]}") from exc

        return resp.json()

    # ── Pagination ────────────────────────────────────────────────

    def _get_activities_page(
        self, after_epoch: int | None, page: int, per_page: int = 200
    ) -> list[dict]:
        params: dict[str, Any] = {"per_page": per_page, "page": page}
        if after_epoch is not None:
            params["after"] = after_epoch
        result = self._get("/athlete/activities", params=params)
        if not isinstance(result, list):
            raise StravaAPIError(f"Format activités inattendu: {type(result)}")
        return result

    def _get_all_run_summaries(self, after_epoch: int | None) -> list[dict]:
        """Collecte paginée de toutes les activités Run depuis after_epoch."""
        runs: list[dict] = []
        page = 1
        while True:
            batch = self._get_activities_page(after_epoch=after_epoch, page=page)
            if not batch:
                break
            for act in batch:
                if (act.get("sport_type") or act.get("type")) in _RUN_SPORT_TYPES:
                    runs.append(act)
            if len(batch) < 200:
                break
            page += 1
            time.sleep(0.2)
        return runs

    def _get_activity_detail(self, activity_id: int) -> dict:
        result = self._get(f"/activities/{activity_id}")
        if not isinstance(result, dict):
            raise StravaAPIError(f"Format détail inattendu: {type(result)}")
        return result

    # ── PR sync ───────────────────────────────────────────────────

    def _load_last_pr_sync_epoch(self) -> int | None:
        with db_session() as conn:
            row = conn.execute(
                "SELECT last_pr_sync_epoch FROM strava_oauth_tokens WHERE id = 1"
            ).fetchone()
        if row and row["last_pr_sync_epoch"]:
            return int(row["last_pr_sync_epoch"])
        return None

    def _save_last_pr_sync_epoch(self) -> None:
        with db_session() as conn:
            conn.execute(
                "UPDATE strava_oauth_tokens SET last_pr_sync_epoch = ? WHERE id = 1",
                (int(time.time()),),
            )

    def sync_personal_records(self, lookback_years: int = 3, incremental: bool = True) -> int:
        """
        Parcourt l'historique Run Strava et extrait les meilleurs chronos sur
        1 km, 5 km et 10 km (champ best_efforts des activités détaillées).

        Mode incrémental : ne traite que les nouvelles activités depuis le dernier sync.
        Premier sync : remonte sur lookback_years années (peut prendre quelques minutes).

        Retourne le nombre de distances mises à jour en DB.
        """
        last_epoch = self._load_last_pr_sync_epoch() if incremental else None
        if last_epoch is not None:
            after_epoch: int | None = last_epoch
            print(f"  Strava : sync incrémental depuis {datetime.fromtimestamp(last_epoch).date()}")
        else:
            after_epoch = int(
                (datetime.now(UTC) - timedelta(days=lookback_years * 365)).timestamp()
            )
            print(f"  Strava : scan initial ({lookback_years} ans)...")

        # 1. Collecte des sommaires Run (rapide)
        runs = self._get_all_run_summaries(after_epoch=after_epoch)
        print(f"  Strava : {len(runs)} runs à analyser.")

        if not runs:
            self._save_last_pr_sync_epoch()
            return 0

        # 2. Détails + best_efforts
        best: dict[float, dict[str, Any]] = {}

        for i, act in enumerate(runs, 1):
            # _get() gère le backoff 429 automatiquement — pas de try/except ici
            detail = self._get_activity_detail(act["id"])

            for effort in detail.get("best_efforts", []):
                name = effort.get("name", "")
                dist_m = _EFFORT_TARGETS.get(name)
                if dist_m is None:
                    continue
                duration = int(effort.get("elapsed_time") or 0)
                if duration <= 0:
                    continue
                if dist_m not in best or duration < best[dist_m]["duree_sec"]:
                    best[dist_m] = {
                        "duree_sec": duration,
                        "date": (act.get("start_date_local") or "")[:10],
                    }

            if i % 50 == 0:
                print(f"  Strava : {i}/{len(runs)} runs traites...")

        # 3. Persistance
        with db_session() as conn:
            for dist_m, data in best.items():
                conn.execute(
                    """
                    INSERT OR REPLACE INTO vigueur_personal_records
                        (distance_m, duree_sec, date_realisation, source)
                    VALUES (?, ?, ?, 'strava')
                    """,
                    (dist_m, data["duree_sec"], data["date"]),
                )

        self._save_last_pr_sync_epoch()
        return len(best)
