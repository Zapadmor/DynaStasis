"""Vigueur : entraînement, récupération, records. Sources : Intervals.icu et Strava."""

from __future__ import annotations

import sys

from src.pillars.base import Command, Pilier


def render(cw: dict | None) -> None:
    from src.app.views import vigueur  # noqa: PLC0415

    vigueur.render()


def _sync(argv: list[str]) -> int:
    from bots.vigueur_bot import main  # noqa: PLC0415

    sys.argv = [sys.argv[0], *argv]
    return main()


def _strava_auth(argv: list[str]) -> int:
    from src.collectors.strava_client import StravaAPIError, StravaClient  # noqa: PLC0415

    try:
        StravaClient().authorize()
    except StravaAPIError as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    return 0


def _intervals_ok() -> bool:
    from src.config import get_secret  # noqa: PLC0415

    return bool(
        get_secret("intervals_icu", "athlete_id") and get_secret("intervals_icu", "api_key")
    )


def _strava_ok() -> bool:
    from src.config import get_secret  # noqa: PLC0415

    return bool(get_secret("strava", "client_id") and get_secret("strava", "client_secret"))


def _sources():
    from src.core.sync_runner import Source, py  # noqa: PLC0415

    return [
        Source(
            "intervals",
            "vigueur",
            py("vigueur", "--only", "intervals"),
            _intervals_ok,
            "INTERVALS_ICU_ATHLETE_ID / INTERVALS_ICU_API_KEY absents",
        ),
        Source(
            "strava",
            "vigueur",
            py("vigueur", "--only", "strava"),
            _strava_ok,
            "STRAVA_CLIENT_ID / STRAVA_CLIENT_SECRET absents",
        ),
    ]


PILIER = Pilier(
    key="VIGUEUR",
    label="Vigueur",
    icon=":material/directions_run:",
    url_path="vigueur",
    render=render,
    sync=Command(
        "vigueur", "Sync Intervals.icu + Strava PRs → SQLite (--only intervals|strava)", _sync
    ),
    commands=(
        Command("strava-auth", "Autorisation OAuth Strava (scope activity:read_all)", _strava_auth),
    ),
    sources=_sources,
    sync_order=10,
)
