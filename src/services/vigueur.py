"""Page Vigueur : courbe de charge, pauses du système, phases du macro-cycle et leurs jalons."""

from __future__ import annotations

import datetime

from src.database.connection import db_session
from src.repositories import vigueur as repo


def statut_phase(debut: str, fin: str, aujourd_hui: datetime.date) -> str:
    """« À VENIR », « EN COURS » ou « PASSÉ » pour une phase datée (bornes incluses)."""
    if aujourd_hui < datetime.date.fromisoformat(debut):
        return "À VENIR"
    if aujourd_hui > datetime.date.fromisoformat(fin):
        return "PASSÉ"
    return "EN COURS"


def charge_quotidienne() -> list[dict]:
    """CTL/ATL/TSB/TSS quotidiens, du plus ancien au plus récent (liste vide si base non prête)."""
    try:
        with db_session() as conn:
            return repo.charge_quotidienne(conn)
    except Exception:
        return []


def pauses() -> list[dict]:
    """Périodes de gel du système (liste vide si la table n'existe pas encore)."""
    try:
        with db_session() as conn:
            return repo.pauses(conn)
    except Exception:
        return []


def bandes_pauses(
    freezes: list[dict], depuis: str, jusqu_a: str, max_label: int = 28
) -> list[dict]:
    """Pauses à tracer sur la courbe, rognées à la fenêtre [depuis, jusqu_a] (dates ISO).

    Une pause hors fenêtre est écartée. Le libellé est « PAUSE · raison » (raison tronquée)."""
    bandes = []
    for f in freezes:
        debut, fin = f["date_debut"][:10], f["date_fin"][:10]
        if fin < depuis or debut > jusqu_a:
            continue
        raison = (f.get("raison") or "").strip()
        if len(raison) > max_label:
            raison = raison[: max_label - 1].rstrip() + "…"
        bandes.append(
            {
                "x0": max(debut, depuis),
                "x1": min(fin, jusqu_a),
                "label": f"PAUSE · {raison}" if raison else "PAUSE",
            }
        )
    return bandes


def grouper_jalons(
    phases: list[dict], taches: list[dict]
) -> tuple[list[tuple[dict, list[dict]]], list[dict]]:
    """Rattache chaque tâche (jalon) à la phase du macro-cycle qui contient son échéance.

    Une phase couvre [Début, Début de la suivante[ (la dernière : jusqu'à sa Fin incluse), ce qui évite
    qu'une échéance tombant à la jointure de deux phases compte deux fois. Retourne
    ([(phase, jalons)], jalons sans échéance ou hors de toutes les phases), triés par échéance."""
    ordonnees = sorted(phases, key=lambda p: p["Début"])
    groupes: list[tuple[dict, list[dict]]] = [(p, []) for p in ordonnees]
    autres: list[dict] = []
    for tache in sorted(taches, key=lambda t: (t.get("date_echeance") or "9999", t["id"])):
        jour = (tache.get("date_echeance") or "")[:10]
        cible = None
        if jour:
            for i, p in enumerate(ordonnees):
                derniere = i == len(ordonnees) - 1
                fin_exclue = None if derniere else ordonnees[i + 1]["Début"]
                if p["Début"] <= jour and (jour <= p["Fin"] if derniere else jour < fin_exclue):
                    cible = groupes[i][1]
                    break
        (cible if cible is not None else autres).append(tache)
    return groupes, autres
