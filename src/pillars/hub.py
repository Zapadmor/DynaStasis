"""Journal de bord : page d'accueil, toujours affichée."""

from __future__ import annotations

from src.pillars.base import Pilier


def render(cw: dict | None) -> None:
    from src.app.views import dashboard  # noqa: PLC0415

    dashboard.render(cw)


PILIER = Pilier(
    key="HUB",
    label="Journal de Bord",
    icon=":material/home:",
    url_path="hub",
    render=render,
    toggleable=False,
)
