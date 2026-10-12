"""Déclaration d'un pilier : ce que le noyau (navigation, CLI, synchronisation) a besoin d'en savoir.

Ce module reste léger (ni Streamlit ni client réseau à l'import) : `main.py` le charge pour
dispatcher les commandes sans payer le coût de l'interface. Les imports lourds se font dans les
fonctions `render` / `run` de chaque pilier.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.sync_runner import Source


@dataclass(frozen=True)
class Command:
    """Sous-commande de `main.py` ; `run` reçoit les arguments qui suivent le nom."""

    name: str
    help: str
    run: Callable[[list[str]], int]


@dataclass(frozen=True)
class Pilier:
    key: str  # code technique stable (config/user.toml, tags de focus)
    label: str  # libellé de la page dans la navigation
    icon: str
    url_path: str
    render: Callable[[dict | None], None]  # reçoit la semaine courante (ou None)
    sync: Command | None = None  # commande de synchronisation propre au pilier
    commands: tuple[Command, ...] = ()  # autres commandes CLI (ex. autorisation OAuth)
    sources: Callable[[], list[Source]] = list  # sources lancées par `main.py sync`
    sync_order: int = 100  # rang dans `main.py sync` (le plus petit d'abord)
    toggleable: bool = True  # False : toujours affiché (page d'accueil)

    def cli_commands(self) -> tuple[Command, ...]:
        return ((self.sync,) if self.sync else ()) + self.commands
