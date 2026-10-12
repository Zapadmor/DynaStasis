"""Audits (hebdomadaire, trimestriel, annuel) et métriques consolidées de la semaine."""

from __future__ import annotations

from src.core.focus_manager import (
    PILIERS,
    forge_tag_for_mode,
    get_week_pilier_breakdown,
    get_week_sessions,
    get_week_tag_breakdown,
)
from src.core.profile import get_profile
from src.core.tz import today_local
from src.database.connection import db_session
from src.repositories import audits as repo_audits
from src.repositories import semaines as repo_semaines
from src.repositories.audits import COLONNES_HEBDO
from src.repositories.schema import table_existe
from src.services.semaines import trigger_cascade_week

# Champs entiers de l'audit hebdo ; les autres champs texte vides sont enregistrés à NULL.
_CHAMPS_ENTIERS = (
    "alerte_rouge",
    "forge_jours_engagement_mois",
    "jours_engagement_semaine",
    "forge_pro_dependance_tiers",
)


# ── Calculs purs ────────────────────────────────────────────────────────────────────────────────


def fmt_min(v) -> str:
    return f"{float(v or 0):.0f} min"


def fmt_hm(v) -> str:
    """Minutes → « 7h05 » ; « — » si absent."""
    if v is None:
        return "—"
    h, m = divmod(int(round(float(v))), 60)
    return f"{h}h{m:02d}"


def arrondi(v, digits: int = 2) -> float | None:
    return round(float(v), digits) if v is not None else None


def delta_ctl(courant: float | None, precedent: float | None) -> float | None:
    if courant is None or precedent is None:
        return None
    return round(courant - precedent, 2)


def texte_top_apps(apps: list[dict]) -> str | None:
    if not apps:
        return None
    return ", ".join(f"{a['app_name']} ({round(a['fg_min'], 1)}min)" for a in apps)


def texte_volume(vig: dict | None) -> str:
    """Distance et allure moyenne de la semaine."""
    if vig and vig["moving_time_min"] and vig["distance_km"]:
        allure = vig["moving_time_min"] / vig["distance_km"]
        return f"{vig['distance_km']:.1f} km · {allure:.2f} min/km"
    return "—"


def texte_focus_total(total_focus: float, par_pilier: dict[str, float], piliers: list[str]) -> str:
    if not total_focus:
        return "Aucune session cette semaine"
    parts = [
        f"{p.capitalize()} {par_pilier[p] / total_focus * 100:.0f}%"
        for p in piliers
        if par_pilier[p] > 0
    ]
    repartition = " / ".join(parts) if parts else "—"
    return f"{total_focus:.0f} min ({total_focus / 60:.1f} h) — {repartition}"


def compter_jalons(taches: list[dict], aujourd_hui: str) -> tuple[int, int]:
    """(jalons en retard, jalons à venir) parmi les tâches ni faites ni annulées."""
    ouvertes = [t for t in taches if t["statut"] not in ("fait", "annule")]
    en_retard = sum(1 for t in ouvertes if t["date_echeance"] and t["date_echeance"] < aujourd_hui)
    return en_retard, len(ouvertes)


def score_module_annuel(ex: dict, module: dict) -> int | None:
    """Somme des notes des indicateurs d'un module de l'audit annuel (None si l'une manque)."""
    notes = [ex.get(field_key) for field_key, _label, _hint in module["indicators"]]
    if any(n is None for n in notes):
        return None
    return int(sum(notes))


def normaliser_audit_hebdo(valeurs: dict) -> dict:
    """Entiers pour les cases / compteurs, NULL pour les textes vides."""
    out = {}
    for col in COLONNES_HEBDO:
        v = valeurs[col]
        if col in _CHAMPS_ENTIERS:
            out[col] = int(v)
        elif col == "jauge_energie":
            out[col] = v
        else:
            out[col] = v or None
    return out


# ── Lecture ─────────────────────────────────────────────────────────────────────────────────────


def table_prete(nom: str) -> bool:
    with db_session() as conn:
        return table_existe(conn, nom)


def semaines_recentes(limite: int = 52) -> list[dict]:
    with db_session() as conn:
        return repo_audits.semaines_recentes(conn, limite)


def charger_audit(semaine_id: int) -> dict:
    """Audit narratif de la semaine ; `_source` vaut « db » ou « empty »."""
    with db_session() as conn:
        existant = repo_audits.narrative(conn, semaine_id)
    return {"_source": "db", **existant} if existant else {"_source": "empty"}


def meta_semaine(semaine_id: int) -> dict | None:
    with db_session() as conn:
        return repo_audits.meta_semaine(conn, semaine_id)


def lecture_audit(week_id: int, week_start: str, mode_actif: str | None) -> dict:
    """Lignes en lecture seule du formulaire d'audit : tout ce qui est mesuré automatiquement
    (focus par tag, HRV/sommeil, écran) n'est jamais ressaisi à la main."""
    with db_session() as conn:
        vig = repo_semaines.vigueur_agregat(conn, week_start)
        ecran = repo_semaines.ecran_distraction_min(conn, week_id)
        jalons_txt = None
        if forge_tag_for_mode(mode_actif) == "FORGE_PRO":
            objectif = repo_semaines.objectif_actif_id(
                conn, get_profile("forge.objectif_pro_titre", "")
            )
            if objectif is None:
                jalons_txt = "Objectif pro introuvable en base"
            else:
                en_retard, a_venir = compter_jalons(
                    repo_semaines.taches_objectif(conn, objectif), today_local().isoformat()
                )
                jalons_txt = f"{en_retard} jalon(s) en retard / {a_venir} à venir"

    hrv_txt = f"{vig['hrv_moy']:.0f} ms" if vig and vig["hrv_moy"] else "—"
    sleep_txt = fmt_hm(vig["sleep_moy"]) if vig and vig["sleep_moy"] else "—"
    tags = get_week_tag_breakdown(week_id)
    total_focus = sum(s["duree_min"] or 0 for s in get_week_sessions(week_id))

    return {
        "vigueur_volume_txt": texte_volume(vig),
        "vigueur_hrv_sommeil_txt": f"HRV {hrv_txt} · Sommeil {sleep_txt} · Poids —",
        "forge_engagement_txt": fmt_min(tags["FORGE_ENGAGEMENT"]),
        "forge_hardskills_txt": fmt_min(tags["FORGE_HARDSKILLS"]),
        "forge_pro_txt": fmt_min(tags["FORGE_PRO"]),
        "forge_pro_jalons_txt": jalons_txt,
        "logos_txt": fmt_min(tags["LOGOS"]),
        "system_focus_txt": texte_focus_total(
            total_focus, get_week_pilier_breakdown(week_id), PILIERS
        ),
        "system_ecran_txt": f"{ecran:.0f} min" if ecran is not None else "—",
    }


# ── Écriture ────────────────────────────────────────────────────────────────────────────────────


def synchroniser_metriques(week_id: int) -> dict:
    """Agrège vigueur_entries + screen_sessions → semaines_audit, puis déclenche la cascade
    habitudes/focus/score. Retourne les métriques consolidées."""
    with db_session() as conn:
        week_start = repo_semaines.debut(conn, week_id)
        vh = repo_semaines.vigueur_hebdo(conn, week_id)

        precedent = repo_semaines.ctl_moyen_precedent(conn, week_start) if week_start else None
        ctl = vh["ctl_moy"] if vh else None

        screen_total, top_apps = None, None
        if week_start:
            total = repo_semaines.ecran_total_min(conn, week_start)
            if total:
                screen_total = round(float(total), 1)
            top_apps = texte_top_apps(repo_semaines.top_apps(conn, week_start))

        repo_semaines.maj_metriques(
            conn,
            week_id,
            {
                "ctl": arrondi(ctl),
                "atl": arrondi(vh["atl_moy"]) if vh else None,
                "tsb": arrondi(vh["tsb_moy"]) if vh else None,
                "tss": arrondi(vh["tss_total"]) if vh else None,
                "ctl_delta": delta_ctl(ctl, precedent),
                "vo2max": arrondi(vh["vo2max"]) if vh else None,
                "distance_km": arrondi(vh["distance_km"]) if vh else None,
                "temps_sport_min": (
                    round(float(vh["moving_time_min"]), 1) if vh and vh["moving_time_min"] else None
                ),
                "screen_time_min": screen_total,
                "top_apps_text": top_apps,
            },
        )

    trigger_cascade_week(week_id)

    with db_session() as conn:
        return {
            "score": repo_semaines.score_vue(conn, week_id) or {},
            "semaine": repo_semaines.metriques(conn, week_id) or {},
        }


def sauvegarder_audit_hebdo(week_id: int, valeurs: dict, social: str) -> None:
    """Enregistre l'audit et le statut social, puis recalcule la semaine."""
    with db_session() as conn:
        repo_audits.enregistrer_narrative(conn, week_id, normaliser_audit_hebdo(valeurs))
        repo_audits.maj_social(conn, week_id, social)
    trigger_cascade_week(week_id)


def trimestriel(saison: str, annee: int) -> dict:
    with db_session() as conn:
        return repo_audits.trimestriel(conn, saison, annee) or {}


def sauvegarder_trimestriel(saison: str, annee: int, valeurs: dict[str, str]) -> None:
    with db_session() as conn:
        repo_audits.enregistrer_trimestriel(conn, saison, annee, valeurs)


def historique_trimestriel() -> list[dict]:
    with db_session() as conn:
        if not table_existe(conn, "audit_trimestriel"):
            return []
        return repo_audits.trimestriels(conn)


def annuel(annee: int) -> dict:
    with db_session() as conn:
        return repo_audits.annuel(conn, annee) or {}


def sauvegarder_annuel(annee: int, valeurs: dict) -> None:
    with db_session() as conn:
        repo_audits.enregistrer_annuel(conn, annee, valeurs)


def historique_annuel() -> list[dict]:
    with db_session() as conn:
        if not table_existe(conn, "audit_annuel"):
            return []
        return repo_audits.annuels(conn)
