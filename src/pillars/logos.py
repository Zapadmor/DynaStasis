"""Logos : cursus, plan de carrière, temps d'écran. Source : ADB (Samsung)."""

from __future__ import annotations

import sys

from src.pillars.base import Command, Pilier


def render(cw: dict | None) -> None:
    from src.app.views import logos  # noqa: PLC0415

    logos.render(cw)


def _sync(argv: list[str]) -> int:
    from bots.logos_bot import main  # noqa: PLC0415

    sys.argv = [sys.argv[0], *argv]
    return main()


def _adb_ok() -> bool:
    from src.config import get_secret  # noqa: PLC0415

    return bool(get_secret("samsung", "adb_host"))


def _sources():
    from src.core.sync_runner import Source, py  # noqa: PLC0415

    return [
        Source(
            "logos",
            "screen_time",
            py("logos"),
            _adb_ok,
            "SAMSUNG_ADB_HOST absent",
            timeout=180,
        )
    ]


PILIER = Pilier(
    key="LOGOS",
    label="Logos",
    icon=":material/school:",
    url_path="logos",
    render=render,
    sync=Command(
        "logos", "Sync temps écran Samsung ADB → SQLite (--manual : saisie manuelle)", _sync
    ),
    sources=_sources,
    sync_order=20,
)
