"""Données de profil et helpers partagés par les onglets Vigueur."""

from __future__ import annotations

from src.core.profile import get_profile
from src.core.tz import today_local
from src.services import vigueur


def _macro_cycle() -> list[dict]:
    """Phases d'entraînement (clé `vigueur.macro_cycle` : liste de {Phase, Début, Fin, Focus})."""
    return get_profile("vigueur.macro_cycle", []) or []


def _macro_cycle_objectif() -> int | None:
    """Identifiant de l'objectif Forge dont les tâches sont les jalons du macro-cycle."""
    valeur = get_profile("vigueur.macro_cycle_objectif")
    return int(valeur) if valeur is not None else None


def _phase_status(start: str, end: str) -> str:
    return vigueur.statut_phase(start, end, today_local())
