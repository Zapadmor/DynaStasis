"""Système : pauses, synchronisations, thèmes, état de la base."""

from __future__ import annotations

from src.pillars.base import Pilier


def render(cw: dict | None) -> None:
    from src.app.views import systeme  # noqa: PLC0415

    systeme.render()


PILIER = Pilier(
    key="SYSTEME",
    label="Systeme",
    icon=":material/settings:",
    url_path="systeme",
    render=render,
)
