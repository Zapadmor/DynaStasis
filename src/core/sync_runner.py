"""Orchestration des synchronisations : une source par sous-processus, isolées les unes des autres.

Chaque source tourne dans son propre processus avec un délai maximal ; son échec (exception,
délai dépassé, code de retour non nul) est consigné puis le suivant démarre. Le statut est stocké
dans `sync_checkpoints` (dernier état) et `logs_systeme` (historique) et affiché dans la page Système.
Le code de retour agrégé vaut 1 dès qu'une source configurée a échoué.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.config import get_secret
from src.core.tz import now_local, today_local
from src.database.connection import db_session

ROOT_DIR = Path(__file__).resolve().parents[2]
INBOX = ROOT_DIR / "data" / "inbox"
_MAIN = ROOT_DIR / "main.py"
_MESSAGE_MAX = 1500

OK, ERREUR, DELAI, IGNOREE = "ok", "erreur", "delai", "non_configure"


@dataclass(frozen=True)
class Source:
    key: str  # identifiant stable affiché dans la page Système
    type_sync: str  # valeur de `logs_systeme.type_sync`
    argv: tuple[str, ...]  # commande complète
    configured: Callable[[], bool]
    reason: str  # pourquoi la source est ignorée quand elle n'est pas configurée
    timeout: int = 120


@dataclass
class Result:
    key: str
    status: str
    duration_s: float = 0.0
    returncode: int | None = None
    message: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def failed(self) -> bool:
        return self.status in (ERREUR, DELAI)


def _py(*args: str) -> tuple[str, ...]:
    return (sys.executable, str(_MAIN), *args)


def _intervals_ok() -> bool:
    return bool(
        get_secret("intervals_icu", "athlete_id") and get_secret("intervals_icu", "api_key")
    )


def _strava_ok() -> bool:
    return bool(get_secret("strava", "client_id") and get_secret("strava", "client_secret"))


def _adb_ok() -> bool:
    return bool(get_secret("samsung", "adb_host"))


def _finance_ok() -> bool:
    return INBOX.is_dir() and any(
        p.is_file() and not p.name.startswith(".") for p in INBOX.rglob("*")
    )


def default_sources() -> list[Source]:
    return [
        Source(
            "intervals",
            "vigueur",
            _py("vigueur", "--only", "intervals"),
            _intervals_ok,
            "INTERVALS_ICU_ATHLETE_ID / INTERVALS_ICU_API_KEY absents",
        ),
        Source(
            "strava",
            "vigueur",
            _py("vigueur", "--only", "strava"),
            _strava_ok,
            "STRAVA_CLIENT_ID / STRAVA_CLIENT_SECRET absents",
        ),
        Source(
            "logos",
            "screen_time",
            _py("logos"),
            _adb_ok,
            "SAMSUNG_ADB_HOST absent",
            timeout=180,
        ),
        Source(
            "finance",
            "finance",
            _py("finance"),
            _finance_ok,
            "aucun export dans data/inbox/",
            timeout=60,
        ),
    ]


# ── Journal structuré : une ligne JSON par évènement (stdout + data/logs/sync.log) ──────────────


def _logger() -> logging.Logger:
    log = logging.getLogger("dynastasis.sync")
    if any(getattr(h, "_dynastasis", False) for h in log.handlers):
        return log
    log.setLevel(logging.INFO)
    log.propagate = False
    log.addHandler(_mark(_stdout_handler()))
    log_dir = Path(os.environ.get("DYNASTASIS_LOG_DIR") or ROOT_DIR / "data" / "logs")
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        fichier = RotatingFileHandler(log_dir / "sync.log", maxBytes=1_000_000, backupCount=3)
        fichier.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(_mark(fichier))
    except OSError as exc:  # dossier non inscriptible : on garde stdout seul
        log.warning(json.dumps({"event": "log_file_unavailable", "error": str(exc)}))
    return log


def _mark(handler: logging.Handler) -> logging.Handler:
    handler._dynastasis = True  # distingue nos handlers de ceux ajoutés par un tiers
    return handler


def _stdout_handler() -> logging.Handler:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    return handler


def _emit(level: int, event: str, **fields) -> None:
    record = {"ts": now_local().isoformat(timespec="seconds"), "event": event, **fields}
    _logger().log(level, json.dumps(record, ensure_ascii=False))


# ── Exécution ───────────────────────────────────────────────────────────────────────────────────


def _tail(text: str) -> str:
    text = text.strip()
    return text[-_MESSAGE_MAX:]


def run_source(source: Source, timeout: int | None = None) -> Result:
    """Exécute une source dans un sous-processus ; ne lève jamais."""
    limit = timeout or source.timeout
    start = time.monotonic()
    try:
        proc = subprocess.run(
            list(source.argv),
            capture_output=True,
            text=True,
            timeout=limit,
            cwd=str(ROOT_DIR),
        )
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        return Result(
            source.key,
            DELAI,
            round(time.monotonic() - start, 2),
            None,
            _tail(f"Délai de {limit} s dépassé. {out}"),
        )
    except OSError as exc:
        return Result(source.key, ERREUR, round(time.monotonic() - start, 2), None, str(exc))
    duration = round(time.monotonic() - start, 2)
    output = _tail(proc.stdout + proc.stderr)
    status = OK if proc.returncode == 0 else ERREUR
    return Result(source.key, status, duration, proc.returncode, output)


def _record(source: Source, result: Result) -> None:
    """Écrit le statut en base ; un échec d'écriture est journalisé mais jamais bloquant."""
    now = now_local().strftime("%Y-%m-%d %H:%M:%S")
    ok = result.status == OK
    try:
        with db_session() as conn:
            conn.execute(
                """INSERT INTO sync_checkpoints
                       (source, last_date, updated_at, statut, last_success_at,
                        last_error_at, last_error, last_duration_s)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source) DO UPDATE SET
                       last_date       = COALESCE(excluded.last_date, last_date),
                       updated_at      = excluded.updated_at,
                       statut          = excluded.statut,
                       last_success_at = COALESCE(excluded.last_success_at, last_success_at),
                       last_error_at   = COALESCE(excluded.last_error_at, last_error_at),
                       last_error      = COALESCE(excluded.last_error, last_error),
                       last_duration_s = excluded.last_duration_s""",
                (
                    source.key,
                    today_local().isoformat() if ok else None,
                    now,
                    result.status,
                    now if ok else None,
                    None if ok or result.status == IGNOREE else now,
                    None if ok or result.status == IGNOREE else result.message,
                    result.duration_s,
                ),
            )
            if result.status != IGNOREE:
                conn.execute(
                    """INSERT INTO logs_systeme (type_sync, source, statut, message, payload_json)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        source.type_sync,
                        source.key,
                        "ok" if ok else "erreur",
                        result.message[:500] or None,
                        json.dumps(
                            {
                                "duration_s": result.duration_s,
                                "returncode": result.returncode,
                                "status": result.status,
                            }
                        ),
                    ),
                )
    except Exception as exc:
        _emit(logging.WARNING, "statut_non_enregistre", source=source.key, error=str(exc))


def run_all(
    sources: list[Source] | None = None,
    only: list[str] | None = None,
    timeout: int | None = None,
) -> list[Result]:
    """Lance les sources configurées l'une après l'autre ; l'échec de l'une ne bloque pas les autres."""
    selected = sources if sources is not None else default_sources()
    if only:
        selected = [s for s in selected if s.key in only]
    results: list[Result] = []
    for source in selected:
        if not source.configured():
            result = Result(source.key, IGNOREE, message=source.reason)
            _emit(logging.INFO, "source_ignoree", source=source.key, reason=source.reason)
        else:
            _emit(logging.INFO, "source_debut", source=source.key)
            result = run_source(source, timeout)
            _emit(
                logging.INFO if not result.failed else logging.ERROR,
                "source_fin",
                source=source.key,
                status=result.status,
                duration_s=result.duration_s,
                returncode=result.returncode,
                message=result.message[-300:],
            )
        _record(source, result)
        results.append(result)
    if not any(r.status != IGNOREE for r in results):
        _emit(logging.INFO, "aucune_source_configuree", sources=[s.key for s in selected])
    _emit(
        logging.INFO,
        "sync_fin",
        ok=sum(r.status == OK for r in results),
        erreurs=sum(r.failed for r in results),
        ignorees=sum(r.status == IGNOREE for r in results),
    )
    return results


def exit_code(results: list[Result]) -> int:
    """0 si aucune source configurée n'a échoué (y compris quand aucune n'est configurée)."""
    return 1 if any(r.failed for r in results) else 0
