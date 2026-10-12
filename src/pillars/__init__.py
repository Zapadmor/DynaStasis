"""Registre des piliers : seule source de vérité de la navigation, des commandes et des sources.

Ajouter un pilier : créer `src/pillars/<nom>.py` qui expose `PILIER`, puis l'ajouter à `_MODULES`
(l'ordre est celui de la navigation). Ni `main.py` ni `ui_main.py` ne sont à modifier.
"""

from __future__ import annotations

from importlib import import_module

from src.pillars.base import Command, Pilier

_MODULES = ("hub", "forge", "logos", "vigueur", "resonance", "systeme")


def all_piliers() -> tuple[Pilier, ...]:
    """Tous les piliers déclarés, dans l'ordre de navigation."""
    return tuple(import_module(f"{__name__}.{name}").PILIER for name in _MODULES)


def keys() -> list[str]:
    """Codes des piliers activables dans `config/user.toml` (la page d'accueil n'en fait pas partie)."""
    return [p.key for p in all_piliers() if p.toggleable]


def actifs() -> list[Pilier]:
    """Piliers affichés : la page d'accueil, plus ceux listés dans `[piliers] actifs`."""
    from src.core import user_config  # noqa: PLC0415

    return [p for p in all_piliers() if not p.toggleable or user_config.pilier_actif(p.key)]


def commands() -> dict[str, Command]:
    """Commandes CLI déclarées par les piliers (actifs ou non : une commande reste utilisable)."""
    found: dict[str, Command] = {}
    for pilier in all_piliers():
        for cmd in pilier.cli_commands():
            if cmd.name in found:
                raise ValueError(f"Commande en double : {cmd.name!r} (pilier {pilier.key})")
            found[cmd.name] = cmd
    return found


def sources() -> list:
    """Sources de synchronisation des piliers actifs, par rang puis ordre de navigation."""
    ordered = sorted(actifs(), key=lambda p: p.sync_order)
    return [src for p in ordered for src in p.sources()]
