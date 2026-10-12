"""Requêtes sur les audits : hebdomadaire (`audit_narrative`), trimestriel et annuel."""

from __future__ import annotations

import sqlite3

# Colonnes éditables de `audit_narrative`, dans l'ordre d'écriture.
COLONNES_HEBDO = (
    "jauge_energie",
    "alerte_rouge",
    "correction_immediate",
    "pentagone_resonance",
    "ombre_mediocrite",
    "ombre_consommateur",
    "ombre_menteur",
    "forge_jours_engagement_mois",
    "jours_engagement_semaine",
    "forge_drill_engagement",
    "forge_hardskills_sujet",
    "forge_pro_champ_1",
    "forge_pro_champ_2",
    "forge_pro_champ_3",
    "forge_pro_blocage",
    "forge_pro_dependance_tiers",
    "logos_avancement_uvs",
    "logos_projet_tx",
    "logos_article_analyse",
    "alignement_prerequis",
    "alignement_stage",
    "alignement_friction_semaine",
    "plan_priorite_unique",
    "plan_drill_engagement",
)


def semaines_recentes(conn: sqlite3.Connection, limite: int = 52) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT id, week_label, week_start FROM semaines_audit "
            "ORDER BY week_start DESC LIMIT ?",
            (limite,),
        )
    ]


def meta_semaine(conn: sqlite3.Connection, semaine_id: int) -> dict | None:
    """Statut social et mode actif (absents de `audit_narrative`)."""
    row = conn.execute(
        "SELECT social, mode_actif FROM semaines_audit WHERE id = ?", (semaine_id,)
    ).fetchone()
    return dict(row) if row else None


def maj_social(conn: sqlite3.Connection, semaine_id: int, social: str) -> None:
    conn.execute(
        "UPDATE semaines_audit SET social = ?, updated_at = datetime('now') WHERE id = ?",
        (social, semaine_id),
    )


def narrative(conn: sqlite3.Connection, semaine_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM audit_narrative WHERE semaine_id = ?", (semaine_id,)
    ).fetchone()
    return dict(row) if row else None


def enregistrer_narrative(conn: sqlite3.Connection, semaine_id: int, valeurs: dict) -> None:
    """Crée ou met à jour l'audit de la semaine ; `valeurs` porte toutes les `COLONNES_HEBDO`."""
    params = [valeurs[c] for c in COLONNES_HEBDO]
    if narrative(conn, semaine_id) is not None:
        set_clause = ", ".join(f"{c}=?" for c in COLONNES_HEBDO)
        conn.execute(
            f"UPDATE audit_narrative SET {set_clause}, updated_at=datetime('now') "
            "WHERE semaine_id=?",
            (*params, semaine_id),
        )
        return
    colonnes = ", ".join(("semaine_id", *COLONNES_HEBDO))
    marques = ", ".join("?" * (1 + len(COLONNES_HEBDO)))
    conn.execute(
        f"INSERT INTO audit_narrative ({colonnes}) VALUES ({marques})", (semaine_id, *params)
    )


def trimestriel(conn: sqlite3.Connection, saison: str, annee: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM audit_trimestriel WHERE saison=? AND annee=?", (saison, annee)
    ).fetchone()
    return dict(row) if row else None


def enregistrer_trimestriel(
    conn: sqlite3.Connection, saison: str, annee: int, valeurs: dict[str, str]
) -> None:
    if trimestriel(conn, saison, annee) is not None:
        set_clause = ", ".join(f"{k}=?" for k in valeurs) + ", updated_at=datetime('now')"
        conn.execute(
            f"UPDATE audit_trimestriel SET {set_clause} WHERE saison=? AND annee=?",
            (*valeurs.values(), saison, annee),
        )
        return
    colonnes = ", ".join(["saison", "annee", *valeurs])
    marques = ", ".join("?" * (2 + len(valeurs)))
    conn.execute(
        f"INSERT INTO audit_trimestriel ({colonnes}) VALUES ({marques})",
        (saison, annee, *valeurs.values()),
    )


def trimestriels(conn: sqlite3.Connection) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT saison, annee, created_at FROM audit_trimestriel "
            "ORDER BY annee DESC, created_at DESC"
        )
    ]


def annuel(conn: sqlite3.Connection, annee: int) -> dict | None:
    row = conn.execute("SELECT * FROM audit_annuel WHERE annee=?", (annee,)).fetchone()
    return dict(row) if row else None


def enregistrer_annuel(conn: sqlite3.Connection, annee: int, valeurs: dict) -> None:
    if annuel(conn, annee) is not None:
        set_clause = ", ".join(f"{k}=?" for k in valeurs) + ", updated_at=datetime('now')"
        conn.execute(
            f"UPDATE audit_annuel SET {set_clause} WHERE annee=?", (*valeurs.values(), annee)
        )
        return
    colonnes = ", ".join(["annee", *valeurs])
    marques = ", ".join("?" * (1 + len(valeurs)))
    conn.execute(
        f"INSERT INTO audit_annuel ({colonnes}) VALUES ({marques})", (annee, *valeurs.values())
    )


def annuels(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM audit_annuel ORDER BY annee DESC")]
