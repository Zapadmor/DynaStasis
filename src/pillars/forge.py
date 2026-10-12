"""Forge : objectifs, finances, projets. Source : exports bancaires déposés dans data/inbox/."""

from __future__ import annotations

import sys

from src.pillars.base import Command, Pilier


def render(cw: dict | None) -> None:
    from src.app.views import forge  # noqa: PLC0415

    forge.render(cw)


def _sync(argv: list[str]) -> int:
    from src.collectors.finance_collector import main  # noqa: PLC0415

    sys.argv = [sys.argv[0], *argv]
    return main()


def _finance_ok() -> bool:
    from src.core import sync_runner  # noqa: PLC0415

    inbox = sync_runner.INBOX
    return inbox.is_dir() and any(
        p.is_file() and not p.name.startswith(".") for p in inbox.rglob("*")
    )


def _sources():
    from src.core.sync_runner import Source, py  # noqa: PLC0415

    return [
        Source(
            "finance",
            "finance",
            py("finance"),
            _finance_ok,
            "aucun export dans data/inbox/",
            timeout=60,
        )
    ]


PILIER = Pilier(
    key="FORGE",
    label="Forge",
    icon=":material/construction:",
    url_path="forge",
    render=render,
    sync=Command("finance", "Résumé financier depuis les exports CSV/XLSX", _sync),
    sources=_sources,
    sync_order=30,
)
