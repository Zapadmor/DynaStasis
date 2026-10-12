"""Résonnance : audits hebdomadaire, trimestriel et annuel, notes sur les proches."""

from __future__ import annotations

from src.pillars.base import Pilier


def render(cw: dict | None) -> None:
    from src.app.views import resonance  # noqa: PLC0415

    resonance.render(cw)


PILIER = Pilier(
    key="RESONNANCE",
    label="Résonnance",
    icon=":material/edit_note:",
    url_path="resonance",
    render=render,
)
