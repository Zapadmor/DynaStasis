from __future__ import annotations

import streamlit as st

from src.app.components import GRAY, PALETTE
from src.app.theme import contrast_text as _contrast_text
from src.app.theme import is_dark as _is_dark
from src.core import user_config
from src.core.focus_manager import forge_tag_for_mode
from src.core.profile import get_profile
from src.core.tz import today_local
from src.database.connection import db_session

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────────────────────────────────────

_SAISONS = ["Hiver", "Printemps", "Été", "Automne"]
_SAISON_PAR_MOIS = {
    12: "Hiver",
    1: "Hiver",
    2: "Hiver",
    3: "Printemps",
    4: "Printemps",
    5: "Printemps",
    6: "Été",
    7: "Été",
    8: "Été",
    9: "Automne",
    10: "Automne",
    11: "Automne",
}

# ─────────────────────────────────────────────────────────────────────────────
# TEMPLATE AUDIT TRIMESTRIEL
# ─────────────────────────────────────────────────────────────────────────────

_TRIM_PARTIES = [
    {
        "key": "p1",
        "title": "Partie 1 — Bilan & Prise de Conscience",
        "color": PALETTE["amber"],
        "champs": [
            (
                "p1_accomplissements",
                "1.1 Les accomplissements récents",
                "Qu'as-tu accompli ces derniers mois ? Liste tout ce qui te vient à l'esprit "
                "(projets, examens, compétences, réalisations). Comment te sens-tu après ?",
            ),
            (
                "p1_burnout",
                "1.2 Le Burnout et les Écueils",
                "Qu'est-ce qui t'a le plus épuisé mentalement ou physiquement ? "
                "Quelles tâches as-tu commencé à éviter ou à procrastiner ?",
            ),
            (
                "p1_energie",
                "1.3 Énergie et Motivation",
                "Quand as-tu eu l'impression d'être dans ton élément pour la dernière fois ? "
                "Quelle activité te fait oublier le temps et te recharge ?",
            ),
        ],
    },
    {
        "key": "p2",
        "title": "Partie 2 — Vision & Intentions",
        "color": PALETTE["blue_green"],
        "champs": [
            (
                "p2_direction",
                "2.1 La Direction",
                "Imagine-toi dans 2 ans et demi, à la fin de ton diplôme. "
                "Que veux-tu avoir appris (au-delà des cours) ? Expérimenté ? "
                "Quel type de personne veux-tu être devenu ?",
            ),
            (
                "p2_piliers",
                "2.2 Les Piliers",
                "Quels sont les 3 à 5 domaines les plus importants pour ton équilibre "
                "et ton épanouissement actuels ? (Santé physique, mentale, réseau social, "
                "projet professionnel, compétences techniques, soft skills, famille, etc.)",
            ),
            (
                "p2_intentions",
                "2.3 Les Intentions pour la saison",
                "Pour chaque pilier identifié, écris une intention simple et positive "
                "pour les 3 prochains mois.\n"
                "Exemple : « Mon intention est de retrouver de l'énergie et une meilleure récupération. »",
            ),
        ],
    },
    {
        "key": "p3",
        "title": "Partie 3 — Concrétisation & Obstacles",
        "color": PALETTE["sky_blue"],
        "champs": [
            (
                "p3_concretisation",
                "3.1 Définition de Succès",
                "Pour chaque intention, que pourrais-tu concrètement faire, même de manière très petite, "
                "pour la réaliser ? Liste des actions tangibles.",
            ),
            (
                "p3_frictions",
                "3.2 Analyse des Frictions — Le Pire Jour",
                "Prends 2-3 actions concrètes. Imagine une journée horrible : tu es fatigué, "
                "il pleut, tu n'as aucune motivation, 3 cours obligatoires + projet de groupe. "
                "Qu'est-ce qui t'empêcherait, ce jour-là, de faire chaque action ?",
            ),
            (
                "p3_echelle",
                "3.3 Échelle de Pénibilité (1–10)",
                "Sur une échelle de 1 (très facile) à 10 (insurmontable), évalue la pénibilité "
                "pour démarrer chaque action dans ton pire jour. "
                "L'objectif du système sera de faire tomber ces scores en dessous de 3.",
            ),
        ],
    },
    {
        "key": "p4",
        "title": "Partie 4 — Règles du Système",
        "color": GRAY,
        "champs": [
            (
                "p4_solutions",
                "4.1 Solutions Temporaires vs Définitives",
                "As-tu des rustines actuelles pour pallier tes problèmes ? "
                "(Comme la sieste pour le manque de sommeil.) "
                "Quelle serait la solution idéale et durable pour chacune ?",
            ),
            (
                "p4_non_negotiable",
                "4.2 Le Non-Négociable",
                "Quelle est la seule habitude que tu pourrais t'engager à tenir, "
                "peu importe les circonstances, parce qu'elle a un effet "
                "démesurément positif sur ton état ?",
            ),
        ],
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# TEMPLATE AUDIT ANNUEL
# ─────────────────────────────────────────────────────────────────────────────

_ANNUEL_MODULES = [
    {
        "key": "m1",
        "title": "Module 1 — Socle Somatique & Régulation Nerveuse",
        "objectif": (
            "Évaluer la disponibilité physiologique, la capacité de récupération et les "
            "mécanismes d'adaptation face au stress chronique (charge allostatique)."
        ),
        "color": PALETTE["blue_green"],
        "indicators": [
            (
                "m1_note_recuperation",
                "Qualité de la récupération",
                "Sommeil réparateur, énergie constante le matin sans dépendance excessive "
                "aux stimulants. Ex : réveils nocturnes fréquents en Q2, 3 cafés/jour.",
            ),
            (
                "m1_note_signaux",
                "Écoute des signaux d'alarme",
                "Capacité à détecter et ralentir face aux tensions musculaires, céphalées, "
                "inconforts digestifs. Ex : tendance à ignorer les maux de tête jusqu'à l'arrêt forcé.",
            ),
            (
                "m1_note_soupapes",
                "Sobriété des soupapes de décompression",
                "Capacité à réguler le stress sans recourir systématiquement aux écrans, "
                "sucre, alcool ou achats. Ex : scroller 45 min chaque soir après les réunions tendues.",
            ),
            (
                "m1_note_respiration",
                "Respiration & présence",
                "Fréquence des pauses réelles dans la journée (déconnexion sensorielle, "
                "silence, marche). Ex : cohérence cardiaque 3x/semaine en moyenne.",
            ),
        ],
        "questions": [
            (
                "m1_cout_allostasie",
                "Le coût de l'allostasie",
                "À quel moment de l'année ai-je fonctionné « à découvert » sur mes réserves "
                "physiques, et quel en a été le prix direct sur mon humeur et ma lucidité ?",
            ),
            (
                "m1_sources_ressourcement",
                "Les véritables sources de ressourcement",
                "Quelles sont les 2 seules activités qui m'ont redonné une énergie durable "
                "cette année (vs divertissement passif qui engourdit sans réparer) ?",
            ),
        ],
    },
    {
        "key": "m2",
        "title": "Module 2 — Clarté Intrinsèque & Dynamique du Flow",
        "objectif": (
            "Distinguer les accomplissements motivés par la recherche de statut externe "
            "(désir mimétique) de ceux portés par vos moteurs intrinsèques profonds."
        ),
        "color": PALETTE["amber"],
        "indicators": [
            (
                "m2_note_flow",
                "Fréquence du Flow",
                "Immersion totale dans des tâches exigeantes où le temps s'efface au profit "
                "de la concentration. Ex : présent sur la conception, absent sur l'admin.",
            ),
            (
                "m2_note_fierte",
                "Fierté authentique",
                "Sentiment de fierté lié à la maîtrise et au chemin parcouru, indépendant du "
                "regard et des likes extérieurs. Ex : un projet réussi dans l'ombre a plus comblé qu'un prix visible.",
            ),
            (
                "m2_note_effort",
                "Justesse de l'effort",
                "Alignement entre la dépense d'énergie et la valeur perçue (peu de résistance "
                "stérile). Ex : forte friction sur les réunions sans ordre du jour clair.",
            ),
            (
                "m2_note_priorites",
                "Cohérence des priorités",
                "Mes 3 priorités déclarées correspondent aux 3 postes de dépenses de temps "
                "réels. Ex : famille déclarée n°1, mais seulement 30 min dispo/jour.",
            ),
        ],
        "questions": [
            (
                "m2_flow_moment1",
                "Moment d'absorption & vitalité élevée (1)",
                "Moment / projet, et compétences mobilisées.",
            ),
            (
                "m2_flow_moment2",
                "Moment d'absorption & vitalité élevée (2)",
                "Moment / projet, et compétences mobilisées.",
            ),
            (
                "m2_friction_tache1",
                "Friction disproportionnée / procrastination lourde (1)",
                "Tâche / projet, et cause racine (manque de sens ou déficit de compétence ?).",
            ),
            (
                "m2_friction_tache2",
                "Friction disproportionnée / procrastination lourde (2)",
                "Tâche / projet, et cause racine.",
            ),
        ],
    },
    {
        "key": "m3",
        "title": "Module 3 — Écologie Relationnelle & Frontières Psychologiques",
        "objectif": (
            "Évaluer la qualité du cercle d'influence, le niveau de sécurité psychologique "
            "et la netteté des limites personnelles (boundaries)."
        ),
        "color": PALETTE["sky_blue"],
        "indicators": [
            (
                "m3_note_securite",
                "Sécurité psychologique",
                "Présence de relations où l'on peut exprimer vulnérabilité, erreurs ou "
                "désaccords sans risque de rétorsion. Ex : deux amis proches et un mentor en transparence totale.",
            ),
            (
                "m3_note_limites",
                "Fermeté des limites",
                "Capacité à refuser des demandes inopportunes sans se justifier excessivement "
                "ni culpabiliser. Ex : tendance à accepter des urgences de collègues en soirée.",
            ),
            (
                "m3_note_etancheite",
                "Étanchéité émotionnelle",
                "Capacité à faire preuve d'empathie sans absorber la détresse ou l'amertume "
                "d'autrui. Ex : facilement contaminé par le pessimisme des réunions d'équipe.",
            ),
            (
                "m3_note_mutualite",
                "Mutualité & équilibre",
                "Réciprocité dans l'investissement relationnel (temps, soutien, écoute, "
                "générosité). Ex : relation à sens unique depuis plusieurs mois.",
            ),
        ],
        "questions": [
            (
                "m3_oui_complaisance1",
                "« Oui » par complaisance (1)",
                "Situation précise où j'ai dit « oui » par peur du conflit ou besoin d'approbation.",
            ),
            (
                "m3_oui_complaisance2",
                "« Oui » par complaisance (2)",
                "Situation précise où j'ai dit « oui » par peur du conflit ou besoin d'approbation.",
            ),
            (
                "m3_arbitrage_nourrir",
                "Arbitrage relationnel — à nourrir",
                "Quelles sont les 2 relations à nourrir en priorité absolue cette année ?",
            ),
            (
                "m3_arbitrage_reguler",
                "Arbitrage relationnel — à réguler",
                "Quelle relation faut-il réguler drastiquement l'exposition ?",
            ),
        ],
    },
    {
        "key": "m4",
        "title": "Module 4 — Flexibilité Cognitive & Traitement de l'Échec",
        "objectif": (
            "Mesurer la capacité à transformer les erreurs en apprentissages structurés "
            "sans basculer dans le déni externe ou la dévalorisation personnelle."
        ),
        "color": GRAY,
        "indicators": [
            (
                "m4_note_locus",
                "Locus de contrôle interne",
                "Focalisation sur les variables maîtrisables (actions, attitudes) plutôt que "
                "sur la météo ou la faute des autres. Ex : rares plaintes passives, solutions rapides.",
            ),
            (
                "m4_note_autocompassion",
                "Autocompassion pragmatique",
                "Absence d'autocritique destructive en cas d'erreur ; discours interne factuel "
                "et bienveillant. Ex : tendance encore vive au syndrome de l'imposteur après un raté.",
            ),
            (
                "m4_note_courage",
                "Courage de confrontation",
                "Vitesse à regarder en face les vérités inconfortables (statistiques, finances, "
                "tensions de couple). Ex : délai de 3 mois avant de clarifier une anomalie financière.",
            ),
            (
                "m4_note_plasticite",
                "Plasticité d'opinion",
                "Facilité à changer d'avis et à désapprendre face à de nouvelles données "
                "contradictoires. Ex : abandon rapide d'une stratégie obsolète sans regret d'ego.",
            ),
        ],
        "questions": [
            (
                "m4_fait_brut",
                "Le fait brut (sans jugement)",
                "Qu'est-ce qui s'est réellement produit factuellement, lors d'un revers majeur de l'année ?",
            ),
            (
                "m4_interpretation_initiale",
                "L'interprétation initiale",
                "Quelle histoire négative me suis-je racontée sur moi-même ?",
            ),
            (
                "m4_variable_controle",
                "La variable de contrôle",
                "Quel facteur dépendant à 100% de moi n'a pas été actionné à temps ?",
            ),
            (
                "m4_regle_systemique",
                "La règle systémique dérivée",
                "Quelle modification de processus garantit que cette erreur ne se répète plus ?",
            ),
        ],
    },
]

_ANNUEL_M5 = {
    "title": "Module 5 — Feuille de Route & Intentions d'Implémentation",
    "objectif": (
        "Convertir les prises de conscience en architectures comportementales concrètes "
        "selon la théorie de l'autodétermination et les habitudes atomiques."
    ),
    "color": PALETTE["tiger"],
    "piliers": [
        ("m5_autonomie_objectif", "m5_autonomie_indicateur", "Autonomie (ma liberté de choix)"),
        (
            "m5_maitrise_objectif",
            "m5_maitrise_indicateur",
            "Maîtrise (l'artisanat & la compétence)",
        ),
        (
            "m5_contribution_objectif",
            "m5_contribution_indicateur",
            "Contribution (l'impact externe)",
        ),
    ],
    "si_alors": [
        (
            "m5_habitude_declencheur",
            "m5_habitude_comportement",
            "Micro-habitude clé (<10 min)",
            "Dès que [heure / événement précis du matin]…",
            "J'exécute immédiatement [action minimale non négociable]…",
        ),
        (
            "m5_distraction_declencheur",
            "m5_distraction_comportement",
            "Gestion de la distraction",
            "Si je ressens l'envie réflexe d'ouvrir [application parasite]…",
            "Alors je m'oblige à [pause somatique de 3 respirations / téléphone hors de la pièce]…",
        ),
        (
            "m5_regulation_declencheur",
            "m5_regulation_comportement",
            "Régulation hebdomadaire",
            "Chaque [jour fixe, ex : dimanche 18h00]…",
            "Je bloque 15 minutes pour auditer mes 3 métriques de la semaine passée…",
        ),
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS DB
# ─────────────────────────────────────────────────────────────────────────────


def _table_exists(conn, name: str) -> bool:
    return (
        conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        is not None
    )


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS DB — Notes pour trop tard
# ─────────────────────────────────────────────────────────────────────────────


def _npt_tables_ready() -> bool:
    with db_session() as conn:
        return _table_exists(conn, "npt_personnes") and _table_exists(conn, "npt_notes")


def _npt_get_persons() -> list[dict]:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM npt_personnes ORDER BY "
            "CASE etat WHEN 'En vie et proche' THEN 0 WHEN 'Mort' THEN 1 ELSE 2 END, "
            "COALESCE(proximite, 0) DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def _npt_get_notes(personne_id: int) -> list[dict]:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM npt_notes WHERE personne_id=? ORDER BY date_note DESC, id DESC",
            (personne_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def _npt_add_note(personne_id: int, date_note: str, contenu: str) -> None:
    with db_session() as conn:
        conn.execute(
            "INSERT INTO npt_notes (personne_id, date_note, contenu) VALUES (?,?,?)",
            (personne_id, date_note, contenu),
        )


def _npt_add_person(
    prenom: str, nom: str, liens: list[str], etat: str, proximite: int | None
) -> int:
    with db_session() as conn:
        cur = conn.execute(
            "INSERT INTO npt_personnes (prenom, nom, liens, etat, proximite) VALUES (?,?,?,?,?)",
            (prenom, nom, ",".join(liens), etat, proximite),
        )
        return cur.lastrowid


def _sync_semaine_metrics(week_id: int) -> dict:
    """
    Agrège vigueur_entries + screen_sessions → semaines_audit, puis déclenche
    la cascade habitudes/focus/score. Retourne les métriques consolidées.
    """
    from src.core.system_engine import trigger_cascade_week

    def _r2(v):
        return round(float(v), 2) if v is not None else None

    with db_session() as conn:
        sa_info = conn.execute(
            "SELECT week_start FROM semaines_audit WHERE id = ?", (week_id,)
        ).fetchone()
        week_start = sa_info["week_start"] if sa_info else None

        # ── Vigueur (Intervals.icu) ──────────────────────────────────────────
        vh = conn.execute("SELECT * FROM v_vigueur_hebdo WHERE id = ?", (week_id,)).fetchone()

        prev_ctl = None
        if week_start:
            prev = conn.execute(
                """SELECT AVG(ve.ctl) AS ctl_moy
                   FROM semaines_audit sa
                   JOIN vigueur_entries ve
                     ON ve.date_entry >= sa.week_start
                    AND ve.date_entry < date(sa.week_start, '+7 days')
                   WHERE sa.week_start = (
                     SELECT week_start FROM semaines_audit
                     WHERE week_start < ? AND is_frozen = 0
                     ORDER BY week_start DESC LIMIT 1
                   )""",
                (week_start,),
            ).fetchone()
            prev_ctl = prev["ctl_moy"] if prev else None

        ctl_curr = vh["ctl_moy"] if vh else None
        ctl_delta = (
            round(ctl_curr - prev_ctl, 2) if ctl_curr is not None and prev_ctl is not None else None
        )

        # ── Screen time (screen_sessions) ────────────────────────────────────
        screen_total = None
        top_apps_text = None
        if week_start:
            total_row = conn.execute(
                """SELECT SUM(duration_seconds) / 60.0 AS total_min
                   FROM screen_sessions
                   WHERE session_start >= ? AND session_start < date(?, '+7 days')""",
                (week_start, week_start),
            ).fetchone()
            if total_row and total_row["total_min"]:
                screen_total = round(float(total_row["total_min"]), 1)

            top_rows = conn.execute(
                """SELECT app_name, SUM(duration_seconds) / 60.0 AS fg_min
                   FROM screen_sessions
                   WHERE session_start >= ? AND session_start < date(?, '+7 days')
                   GROUP BY app_name ORDER BY fg_min DESC LIMIT 5""",
                (week_start, week_start),
            ).fetchall()
            if top_rows:
                top_apps_text = ", ".join(
                    f"{r['app_name']} ({round(r['fg_min'], 1)}min)" for r in top_rows
                )

        # ── Update semaines_audit ─────────────────────────────────────────────
        conn.execute(
            """UPDATE semaines_audit SET
                   ctl             = ?,
                   atl             = ?,
                   tsb             = ?,
                   tss             = ?,
                   ctl_delta       = ?,
                   vo2max          = ?,
                   distance_km     = ?,
                   temps_sport_min = ?,
                   screen_time_min = COALESCE(?, screen_time_min),
                   top_apps_text   = COALESCE(?, top_apps_text),
                   updated_at      = datetime('now')
               WHERE id = ?""",
            (
                _r2(ctl_curr),
                _r2(vh["atl_moy"]) if vh else None,
                _r2(vh["tsb_moy"]) if vh else None,
                _r2(vh["tss_total"]) if vh else None,
                ctl_delta,
                _r2(vh["vo2max"]) if vh else None,
                _r2(vh["distance_km"]) if vh else None,
                round(float(vh["moving_time_min"]), 1) if vh and vh["moving_time_min"] else None,
                screen_total,
                top_apps_text,
                week_id,
            ),
        )

    trigger_cascade_week(week_id)

    with db_session() as conn:
        score_row = conn.execute(
            "SELECT * FROM v_score_semaine WHERE id = ?", (week_id,)
        ).fetchone()
        sa_row = conn.execute(
            """SELECT ctl, atl, tsb, tss, ctl_delta, vo2max,
                      distance_km, temps_sport_min, screen_time_min,
                      top_apps_text, score_semaine
               FROM semaines_audit WHERE id = ?""",
            (week_id,),
        ).fetchone()

    return {
        "score": dict(score_row) if score_row else {},
        "semaine": dict(sa_row) if sa_row else {},
    }


def _load_audit_data(selected_id: int) -> dict:
    """Load audit_narrative from SQLite. Returns dict with extra key '_source': 'db' | 'empty'."""
    with db_session() as conn:
        existing = conn.execute(
            "SELECT * FROM audit_narrative WHERE semaine_id = ?", (selected_id,)
        ).fetchone()

    if existing:
        return {"_source": "db", **dict(existing)}

    return {"_source": "empty"}


def _fmt_min(v) -> str:
    return f"{float(v or 0):.0f} min"


def _fmt_hm(v) -> str:
    if v is None:
        return "—"
    h, m = divmod(int(round(float(v))), 60)
    return f"{h}h{m:02d}"


def _compute_audit_readouts(conn, week_id: int, week_start: str, mode_actif: str | None) -> dict:
    """Lignes lecture-seule du form d'audit hebdo v2 (§4 PLAN_AUDIT_HEBDO_V2.md) : tout ce
    qui est mesurable automatiquement (focus par tag, HRV/sommeil, écran) n'est jamais
    ressaisi à la main."""
    from src.core.focus_manager import (
        PILIERS,
        get_week_pilier_breakdown,
        get_week_sessions,
        get_week_tag_breakdown,
    )

    vig = conn.execute(
        """SELECT SUM(moving_time_min) AS moving_time_min, SUM(distance_km) AS distance_km,
                  AVG(hrv) AS hrv_moy, AVG(sleep_min) AS sleep_moy
           FROM vigueur_entries
           WHERE date_entry >= ? AND date_entry < date(?, '+7 days')""",
        (week_start, week_start),
    ).fetchone()

    if vig and vig["moving_time_min"] and vig["distance_km"]:
        allure = vig["moving_time_min"] / vig["distance_km"]
        volume_txt = f"{vig['distance_km']:.1f} km · {allure:.2f} min/km"
    else:
        volume_txt = "—"

    hrv_txt = f"{vig['hrv_moy']:.0f} ms" if vig and vig["hrv_moy"] else "—"
    sleep_txt = _fmt_hm(vig["sleep_moy"]) if vig and vig["sleep_moy"] else "—"

    tag_breakdown = get_week_tag_breakdown(week_id)
    pilier_breakdown = get_week_pilier_breakdown(week_id)
    total_focus = sum(s["duree_min"] or 0 for s in get_week_sessions(week_id))

    if total_focus:
        parts = [
            f"{p.capitalize()} {pilier_breakdown[p] / total_focus * 100:.0f}%"
            for p in PILIERS
            if pilier_breakdown[p] > 0
        ]
        repartition_txt = " / ".join(parts) if parts else "—"
        focus_total_txt = f"{total_focus:.0f} min ({total_focus / 60:.1f} h) — {repartition_txt}"
    else:
        focus_total_txt = "Aucune session cette semaine"

    score_row = conn.execute(
        "SELECT screen_distraction_min FROM v_score_semaine WHERE id = ?", (week_id,)
    ).fetchone()
    ecran_txt = (
        f"{score_row['screen_distraction_min']:.0f} min"
        if score_row and score_row["screen_distraction_min"] is not None
        else "—"
    )

    jalons_txt = None
    if forge_tag_for_mode(mode_actif) == "FORGE_PRO":
        obj_row = conn.execute(
            "SELECT id FROM objectifs WHERE titre = ? AND statut = 'actif'",
            (get_profile("forge.objectif_pro_titre", ""),),
        ).fetchone()
        if obj_row:
            today_str = today_local().isoformat()
            jalons = conn.execute(
                "SELECT statut, date_echeance FROM taches WHERE objectif_id = ?", (obj_row["id"],)
            ).fetchall()
            en_retard = sum(
                1
                for j in jalons
                if j["statut"] not in ("fait", "annule")
                and j["date_echeance"]
                and j["date_echeance"] < today_str
            )
            a_venir = sum(1 for j in jalons if j["statut"] not in ("fait", "annule"))
            jalons_txt = f"{en_retard} jalon(s) en retard / {a_venir} à venir"
        else:
            jalons_txt = "Objectif pro introuvable en base"

    return {
        "vigueur_volume_txt": volume_txt,
        "vigueur_hrv_sommeil_txt": f"HRV {hrv_txt} · Sommeil {sleep_txt} · Poids —",
        "forge_engagement_txt": _fmt_min(tag_breakdown["FORGE_ENGAGEMENT"]),
        "forge_hardskills_txt": _fmt_min(tag_breakdown["FORGE_HARDSKILLS"]),
        "forge_pro_txt": _fmt_min(tag_breakdown["FORGE_PRO"]),
        "forge_pro_jalons_txt": jalons_txt,
        "logos_txt": _fmt_min(tag_breakdown["LOGOS"]),
        "system_focus_txt": focus_total_txt,
        "system_ecran_txt": ecran_txt,
    }


# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 : AUDIT HEBDOMADAIRE (Sections II–VI)
# ─────────────────────────────────────────────────────────────────────────────


def _render_audit_hebdo(current_week: dict | None) -> None:
    st.markdown("### Audit Hebdomadaire — Template Complet")

    with db_session() as conn:
        if not _table_exists(conn, "audit_narrative"):
            st.info("Table `audit_narrative` non initialisée. Lancez `python main.py init-db`.")
            return
        all_weeks = conn.execute(
            "SELECT id, week_label, week_start FROM semaines_audit ORDER BY week_start DESC LIMIT 52"
        ).fetchall()

    if not all_weeks:
        st.info("Aucune semaine disponible.")
        return

    week_ids = [w["id"] for w in all_weeks]
    week_labels = {w["id"]: w["week_label"] for w in all_weeks}
    week_starts = {w["id"]: w["week_start"] for w in all_weeks}
    default_idx = 0
    if current_week and current_week["id"] in week_ids:
        default_idx = week_ids.index(current_week["id"])

    selected_id = st.selectbox(
        "Semaine",
        options=week_ids,
        format_func=lambda x: week_labels[x],
        index=default_idx,
        key="audit_hebdo_week_sel",
    )

    # Per-week data key: loads fresh when week changes (key not in session_state)
    _data_key = f"_ah_data_{selected_id}"
    if _data_key not in st.session_state:
        with st.spinner("Chargement…"):
            st.session_state[_data_key] = _load_audit_data(selected_id)

    d = st.session_state[_data_key]
    source = d.get("_source", "empty")

    _sync_key = f"_sync_result_{selected_id}"

    col_info, col_btn = st.columns([4, 1])
    with col_info:
        st.markdown(f"**{week_labels[selected_id]}**")
    with col_btn:
        if st.button("⟳ Synchroniser", key=f"sync_{selected_id}", use_container_width=True):
            with st.spinner("Synchronisation…"):
                try:
                    st.session_state[_sync_key] = _sync_semaine_metrics(selected_id)
                except Exception as exc:
                    st.session_state[_sync_key] = {"error": str(exc)}
            st.session_state.pop(_data_key, None)
            st.rerun()

    if _sync_key in st.session_state:
        sync_res = st.session_state[_sync_key]
        if "error" in sync_res:
            st.error(f"Sync échoué : {sync_res['error']}")
        else:
            sa = sync_res.get("semaine", {})
            sc = sync_res.get("score", {})
            score = sc.get("score_semaine")

            score_color = (
                PALETTE["blue_green"]
                if (score or 0) >= 67
                else PALETTE["amber"]
                if (score or 0) >= 34
                else "#e05252"
            )

            def _fmt(v, suffix="", digits=1):
                return f"{round(float(v), digits)}{suffix}" if v is not None else "—"

            def _sleep_fmt(v):
                if v is None:
                    return "—"
                h, m = divmod(int(round(float(v))), 60)
                return f"{h}h{m:02d}"

            def _pill(ok, label, detail=""):
                if _is_dark():
                    bg = "#1a3a2a" if ok else "#3a1a1a"
                else:
                    bg = "#c8eec8" if ok else "#eec8c8"
                mark_col = PALETTE["blue_green"] if ok else "#e05252"
                pill_text = _contrast_text(bg)
                mark = "✓" if ok else "✗"
                detail_html = (
                    f' <span style="opacity:.55;font-size:.71rem;">({detail})</span>'
                    if detail
                    else ""
                )
                return (
                    f'<span style="background:{bg};border:1px solid {mark_col}33;'
                    f'border-radius:4px;padding:2px 8px;font-size:.79rem;white-space:nowrap;color:{pill_text};">'
                    f'<span style="color:{mark_col};font-weight:700;">{mark}</span>'
                    f" {label}{detail_html}</span>"
                )

            seuils = user_config.load()["seuils"]["semaine"]
            sommeil_h, sommeil_m = divmod(int(seuils["sommeil_min"]), 60)
            pills = [
                _pill(
                    sc.get("ok_entrainement"),
                    "Entraîn.",
                    f"{int(sc.get('entrainement_min', 0))}/{seuils['entrainement_min']:.0f}min",
                ),
                _pill(
                    sc.get("ok_seances"),
                    "Séances",
                    f"{int(sc.get('seances', 0))}/{seuils['seances']:.0f}",
                ),
                _pill(
                    sc.get("ok_pas"),
                    "Pas",
                    f"{int(sc.get('pas_total', 0)) // 1000}k/{seuils['pas'] / 1000:.0f}k",
                ),
                _pill(
                    sc.get("ok_sommeil"),
                    "Sommeil moy./nuit",
                    f"{_sleep_fmt(sc.get('sleep_moy'))}/{sommeil_h}h{sommeil_m:02d}",
                ),
                _pill(
                    sc.get("ok_charge_fraicheur"),
                    "Charge/Fraîch.",
                    f"TSB {_fmt(sc.get('tsb'), digits=1)}"
                    + (" · décharge" if sc.get("is_deload_week") else ""),
                ),
                _pill(
                    sc.get("ok_ecran"),
                    "Écran",
                    f"{int(sc.get('screen_distraction_min', 0))}/{seuils['ecran_max_min']:.0f}min",
                ),
                _pill(sc.get("ok_deep_focus"), "Focus", f"{int(sc.get('deep_focus_min', 0))}min"),
                _pill(
                    sc.get("ok_projets_fond"),
                    "Projets fond",
                    f"{int(sc.get('focus_projets_fond_min', 0))}/{seuils['projets_fond_min']:.0f}min",
                ),
                *(
                    [
                        _pill(
                            sc.get("ok_engagement"),
                            user_config.engagement_libelle(),
                            f"{int(sc.get('focus_engagement_min', 0))}min · "
                            f"{int(sc.get('jours_engagement_semaine', 0))}j",
                        )
                    ]
                    if user_config.engagement_actif()
                    else []
                ),
                _pill(sc.get("ok_cloture"), "Clôture", sc.get("social") or "—"),
            ]
            top = sa.get("top_apps_text") or "—"

            st.markdown(
                f'<div style="border-left:3px solid {score_color};padding:8px 14px;margin:6px 0;">'
                f'<div style="font-size:1rem;font-weight:700;color:{score_color};margin-bottom:6px;">'
                f"Score de la semaine : {_fmt(score, '/100', 0)}</div>"
                f'<div style="display:flex;gap:5px;flex-wrap:wrap;">' + " ".join(pills) + "</div>"
                f'<div style="font-size:.74rem;opacity:.55;margin-top:5px;">{top}</div>'
                "</div>",
                unsafe_allow_html=True,
            )

    # Charger le statut social + mode_actif depuis semaines_audit (absents de audit_narrative)
    with db_session() as conn:
        _sa_meta = conn.execute(
            "SELECT social, mode_actif FROM semaines_audit WHERE id = ?", (selected_id,)
        ).fetchone()
    _social_opts = ["Connecté/Ressourcé", "Isolé"]
    _social_current = (
        _sa_meta["social"] if _sa_meta and _sa_meta["social"] in _social_opts else _social_opts[0]
    )
    mode_actif = _sa_meta["mode_actif"] if _sa_meta else None

    _readouts_key = f"_ah_readouts_{selected_id}"
    if _readouts_key not in st.session_state:
        with db_session() as conn:
            st.session_state[_readouts_key] = _compute_audit_readouts(
                conn, selected_id, week_starts[selected_id], mode_actif
            )
    readouts = st.session_state[_readouts_key]

    # ── Formulaire (sans key= sur les widgets : value= pilote tout) ───────────
    with st.form(f"audit_hebdo_form_{selected_id}"):
        st.markdown(
            f'<div style="border-left:3px solid {PALETTE["amber"]};padding:4px 14px;margin-bottom:8px;">'
            f"<strong>II. ÉTAT DU SYSTÈME (STASIE)</strong></div>",
            unsafe_allow_html=True,
        )
        col_j, col_s, col_a = st.columns([2, 1.5, 1])
        with col_j:
            jauge = st.slider(
                "Jauge d'Énergie (1–10)",
                1,
                10,
                value=int(d.get("jauge_energie") or 6),
            )
        with col_s:
            social_val = st.selectbox(
                "Statut social",
                _social_opts,
                index=_social_opts.index(_social_current),
                help="Utilisé dans le critère #3 du score semaine.",
            )
        with col_a:
            alerte = st.checkbox(
                "Alerte Rouge",
                value=bool(d.get("alerte_rouge")),
                help="Ai-je menti sur mes actions ou raté un audit cette semaine ?",
            )
        correction = st.text_area(
            "Correction Immédiate (si alerte rouge)",
            value=d.get("correction_immediate") or "",
            height=60,
            placeholder="Définir l'action de réinitialisation…",
        )

        st.markdown(
            f'<div style="border-left:3px solid {PALETTE["blue_green"]};padding:4px 14px;margin:12px 0 8px;">'
            f"<strong>III. LE PENTAGONE (DYNA)</strong></div>",
            unsafe_allow_html=True,
        )

        st.markdown("**VIGUEUR**")
        col_v1, col_v2, col_v3 = st.columns(3)
        col_v1.caption(f"Volume Course : {readouts['vigueur_volume_txt']}")
        col_v2.caption("Ratio Z2 vs Intensité : — (pas de source, sync Suunto à venir)")
        col_v3.caption(readouts["vigueur_hrv_sommeil_txt"])

        jours_mois = int(d.get("forge_jours_engagement_mois") or 0)
        jours_engagement_sem = int(d.get("jours_engagement_semaine") or 0)
        drill_eng = d.get("forge_drill_engagement") or ""
        if user_config.engagement_actif():
            libelle = user_config.engagement_libelle()
            libelle_jours = user_config.engagement_libelle_jours()
            st.markdown(f"**FORGE — {libelle}**")
            col_m1, col_m2, col_m3 = st.columns(3)
            with col_m1:
                jours_mois = st.number_input(
                    f"{libelle_jours} ce mois-ci",
                    min_value=0,
                    max_value=31,
                    value=jours_mois,
                )
            with col_m2:
                jours_engagement_sem = st.number_input(
                    f"{libelle_jours} cette semaine",
                    min_value=0,
                    max_value=7,
                    value=jours_engagement_sem,
                )
            with col_m3:
                drill_eng = st.text_input(
                    "Pratique de la semaine",
                    value=drill_eng,
                    placeholder="Fait (X min) / Non fait",
                )
            st.caption(f"Temps focus dédié : {readouts['forge_engagement_txt']}")

        st.markdown("**FORGE — Hard Skills & Problématiques Critiques**")
        st.caption(f"Temps focus dédié : {readouts['forge_hardskills_txt']}")
        hardskills_sujet = st.text_input(
            "Sujet technique traité cette semaine",
            value=d.get("forge_hardskills_sujet") or "",
            placeholder="Ex. Optimisation mémoire C++20 / Pipeline TensorRT…",
        )

        # Initialisées avant le bloc conditionnel pour éviter tout NameError hors mode pro
        # (bloc entreprise non rendu, cf. §7 PLAN_AUDIT_HEBDO_V2.md).
        pro_champ_1 = d.get("forge_pro_champ_1")
        pro_champ_2 = d.get("forge_pro_champ_2")
        pro_champ_3 = d.get("forge_pro_champ_3")
        pro_blocage = d.get("forge_pro_blocage")
        pro_dep_tiers = bool(d.get("forge_pro_dependance_tiers"))

        pro_labels = get_profile(
            "audit.forge_pro_labels",
            ["Point 1 — avancement", "Point 2 — avancement", "Point 3 — avancement"],
        )
        if forge_tag_for_mode(mode_actif) == "FORGE_PRO":
            st.markdown("**FORGE — Entreprise**")
            st.caption(f"Temps focus dédié : {readouts['forge_pro_txt']}")
            pro_champ_1 = st.text_input(
                pro_labels[0],
                value=pro_champ_1 or "",
            )
            pro_champ_2 = st.text_input(
                pro_labels[1],
                value=pro_champ_2 or "",
            )
            pro_champ_3 = st.text_input(
                pro_labels[2],
                value=pro_champ_3 or "",
            )
            pro_blocage = st.text_area(
                "Blocage technique rencontré & solution apportée en solo",
                value=pro_blocage or "",
                height=70,
            )
            pro_dep_tiers = st.checkbox(
                "Ai-je eu besoin d'un tiers pour diagnostiquer/valider un problème hard/soft "
                "cette semaine ?",
                value=pro_dep_tiers,
                help="Cible : tendre vers Non.",
            )
            st.caption(f"Jalons de livraison : {readouts['forge_pro_jalons_txt'] or '—'}")

        st.markdown("**LOGOS — Académique & Recherche**")
        st.caption(f"Temps focus dédié : {readouts['logos_txt']}")
        logos_uvs = st.text_input(
            "Avancement UVs critiques / GPA",
            value=d.get("logos_avancement_uvs") or "",
            placeholder="Points durs traités / zéro retard sur rendus…",
        )
        logos_tx = st.text_input(
            "Projet TX & Publication",
            value=d.get("logos_projet_tx") or "",
            placeholder="État du banc de test / rédaction papier / échange enseignant-chercheur…",
        )
        logos_article = st.text_input(
            "Article scientifique analysé cette semaine",
            value=d.get("logos_article_analyse") or "",
            placeholder="Titre / apport direct pour ton projet…",
        )

        st.markdown("**SYSTÈME**")
        col_s1, col_s2 = st.columns(2)
        col_s1.caption(f"Focus total sem. : {readouts['system_focus_txt']}")
        col_s2.caption(f"Écran distractif sem. : {readouts['system_ecran_txt']}")

        st.markdown("**RÉSONNANCE**")
        penta_resonance = st.text_area(
            "RÉSONNANCE — Service / Relations / Mémoire",
            value=d.get("pentagone_resonance") or "",
            height=90,
            placeholder="Service invisible · Temps proches · Gratitude…",
        )

        st.markdown(
            f'<div style="border-left:3px solid {GRAY};padding:4px 14px;margin:12px 0 8px;">'
            f"<strong>IV. L'OMBRE (L'Anti-Soi)</strong></div>",
            unsafe_allow_html=True,
        )
        col_o1, col_o2, col_o3 = st.columns(3)
        with col_o1:
            ombre_med = st.text_area(
                "Signal de Médiocrité",
                value=d.get("ombre_mediocrite") or "",
                height=80,
                placeholder="Tâche administrative critique reportée ?",
            )
        with col_o2:
            ombre_cons = st.text_area(
                "Le Consommateur",
                value=d.get("ombre_consommateur") or "",
                height=80,
                placeholder="Temps écran : création ou consommation passive ?",
            )
        with col_o3:
            ombre_men = st.text_area(
                "Le Menteur",
                value=d.get("ombre_menteur") or "",
                height=80,
                placeholder="Ai-je trahi le journal pour masquer une faiblesse ?",
            )

        st.markdown(
            f'<div style="border-left:3px solid {PALETTE["sky_blue"]};padding:4px 14px;margin:12px 0 8px;">'
            f"<strong>{get_profile('audit.alignement_titre', 'V. ALIGNEMENT OPÉRATIONNEL')}</strong></div>",
            unsafe_allow_html=True,
        )
        col_al1, col_al2 = st.columns(2)
        with col_al1:
            prerequis = st.text_input(
                get_profile("audit.alignement_label_1", "Statut des prérequis"),
                value=d.get("alignement_prerequis") or "",
            )
        with col_al2:
            stage = st.text_input(
                get_profile("audit.alignement_label_2", "Statut du stage / de la formation"),
                value=d.get("alignement_stage") or "",
            )
        friction_semaine = st.text_area(
            "Point de friction tactique ou physique de la semaine",
            value=d.get("alignement_friction_semaine") or "",
            height=70,
        )

        st.markdown(
            f'<div style="border-left:3px solid {PALETTE["amber"]};padding:4px 14px;margin:12px 0 8px;">'
            f"<strong>VI. PLAN DE BATAILLE — SEMAINE N+1</strong></div>",
            unsafe_allow_html=True,
        )
        col_bat1, col_bat2 = st.columns(2)
        with col_bat1:
            plan_prio = st.text_area(
                "La Priorité Unique (The One Thing)",
                value=d.get("plan_priorite_unique") or "",
                height=90,
                placeholder="Si je ne fais que ceci, la semaine est une réussite…",
            )
        plan_drill_engagement = d.get("plan_drill_engagement") or ""
        with col_bat2:
            if user_config.engagement_actif():
                plan_drill_engagement = st.text_input(
                    f"{user_config.engagement_libelle()} sanctuarisé(e) (jour & heure)",
                    value=plan_drill_engagement,
                    placeholder="Ex : mardi 18h — séance dédiée…",
                )

        submitted = st.form_submit_button("Sauvegarder l'audit", use_container_width=True)

    if submitted:
        existing_in_db = source == "db"
        try:
            with db_session() as conn:
                if existing_in_db:
                    conn.execute(
                        """UPDATE audit_narrative
                           SET jauge_energie=?, alerte_rouge=?, correction_immediate=?,
                               pentagone_resonance=?,
                               ombre_mediocrite=?, ombre_consommateur=?, ombre_menteur=?,
                               forge_jours_engagement_mois=?, jours_engagement_semaine=?,
                               forge_drill_engagement=?, forge_hardskills_sujet=?,
                               forge_pro_champ_1=?, forge_pro_champ_2=?,
                               forge_pro_champ_3=?, forge_pro_blocage=?,
                               forge_pro_dependance_tiers=?,
                               logos_avancement_uvs=?, logos_projet_tx=?, logos_article_analyse=?,
                               alignement_prerequis=?, alignement_stage=?,
                               alignement_friction_semaine=?,
                               plan_priorite_unique=?, plan_drill_engagement=?,
                               updated_at=datetime('now')
                           WHERE semaine_id=?""",
                        (
                            jauge,
                            int(alerte),
                            correction or None,
                            penta_resonance or None,
                            ombre_med or None,
                            ombre_cons or None,
                            ombre_men or None,
                            int(jours_mois),
                            int(jours_engagement_sem),
                            drill_eng or None,
                            hardskills_sujet or None,
                            pro_champ_1 or None,
                            pro_champ_2 or None,
                            pro_champ_3 or None,
                            pro_blocage or None,
                            int(pro_dep_tiers),
                            logos_uvs or None,
                            logos_tx or None,
                            logos_article or None,
                            prerequis or None,
                            stage or None,
                            friction_semaine or None,
                            plan_prio or None,
                            plan_drill_engagement or None,
                            selected_id,
                        ),
                    )
                else:
                    conn.execute(
                        """INSERT INTO audit_narrative
                           (semaine_id, jauge_energie, alerte_rouge, correction_immediate,
                            pentagone_resonance,
                            ombre_mediocrite, ombre_consommateur, ombre_menteur,
                            forge_jours_engagement_mois, jours_engagement_semaine,
                            forge_drill_engagement, forge_hardskills_sujet,
                            forge_pro_champ_1, forge_pro_champ_2,
                            forge_pro_champ_3, forge_pro_blocage,
                            forge_pro_dependance_tiers,
                            logos_avancement_uvs, logos_projet_tx, logos_article_analyse,
                            alignement_prerequis, alignement_stage,
                            alignement_friction_semaine,
                            plan_priorite_unique, plan_drill_engagement)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            selected_id,
                            jauge,
                            int(alerte),
                            correction or None,
                            penta_resonance or None,
                            ombre_med or None,
                            ombre_cons or None,
                            ombre_men or None,
                            int(jours_mois),
                            int(jours_engagement_sem),
                            drill_eng or None,
                            hardskills_sujet or None,
                            pro_champ_1 or None,
                            pro_champ_2 or None,
                            pro_champ_3 or None,
                            pro_blocage or None,
                            int(pro_dep_tiers),
                            logos_uvs or None,
                            logos_tx or None,
                            logos_article or None,
                            prerequis or None,
                            stage or None,
                            friction_semaine or None,
                            plan_prio or None,
                            plan_drill_engagement or None,
                        ),
                    )
                conn.execute(
                    "UPDATE semaines_audit SET social = ?, updated_at = datetime('now') WHERE id = ?",
                    (social_val, selected_id),
                )
                conn.commit()
            from src.core.system_engine import trigger_cascade_week

            trigger_cascade_week(selected_id)
            st.session_state.pop(_data_key, None)
            st.session_state.pop(_readouts_key, None)
            st.success("Audit enregistré.")
            st.rerun()
        except Exception as exc:
            st.error(f"Erreur : {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 : AUDIT TRIMESTRIEL
# ─────────────────────────────────────────────────────────────────────────────


def _render_audit_trimestriel() -> None:
    st.markdown("### Audit Trimestriel — Bilan & Intentions")

    today = today_local()
    saison_defaut = _SAISON_PAR_MOIS.get(today.month, "Printemps")

    col_s, col_y = st.columns([2, 1])
    with col_s:
        saison = st.selectbox(
            "Saison", _SAISONS, index=_SAISONS.index(saison_defaut), key="trim_saison"
        )
    with col_y:
        annee = st.number_input(
            "Année", min_value=2024, max_value=2040, value=today.year, step=1, key="trim_annee"
        )

    with db_session() as conn:
        if not _table_exists(conn, "audit_trimestriel"):
            st.info("Table non initialisée. Lancez `python main.py init-db`.")
            return
        row = conn.execute(
            "SELECT * FROM audit_trimestriel WHERE saison=? AND annee=?", (saison, annee)
        ).fetchone()
        ex = dict(row) if row else {}

    st.markdown("")

    all_vals: dict[str, str] = {}
    annee_int = int(annee)

    with st.form(f"audit_trim_form_{saison}_{annee_int}"):
        for partie in _TRIM_PARTIES:
            st.markdown(
                f'<div style="border-left:3px solid {partie["color"]};padding:4px 14px;margin:14px 0 10px;">'
                f"<strong>{partie['title']}</strong></div>",
                unsafe_allow_html=True,
            )
            for field_key, label, hint in partie["champs"]:
                st.caption(hint)
                all_vals[field_key] = st.text_area(
                    label,
                    value=ex.get(field_key) or "",
                    height=110,
                    key=f"trim_{saison}_{annee_int}_{field_key}",
                )

        submitted = st.form_submit_button(
            f"Sauvegarder — {saison} {annee}", use_container_width=True
        )

    if submitted:
        with db_session() as conn:
            try:
                if ex:
                    set_clause = (
                        ", ".join(f"{k}=?" for k in all_vals) + ", updated_at=datetime('now')"
                    )
                    conn.execute(
                        f"UPDATE audit_trimestriel SET {set_clause} WHERE saison=? AND annee=?",
                        (*all_vals.values(), saison, annee),
                    )
                else:
                    keys = ", ".join(["saison", "annee"] + list(all_vals.keys()))
                    placeholders = ", ".join(["?"] * (2 + len(all_vals)))
                    conn.execute(
                        f"INSERT INTO audit_trimestriel ({keys}) VALUES ({placeholders})",
                        (saison, annee, *all_vals.values()),
                    )
                conn.commit()
                st.success(f"Audit {saison} {annee} enregistré.")
                st.rerun()
            except Exception as exc:
                st.error(f"Erreur : {exc}")

    # Historique des audits trimestriels
    with db_session() as conn:
        hist = (
            conn.execute(
                "SELECT saison, annee, created_at FROM audit_trimestriel ORDER BY annee DESC, created_at DESC"
            ).fetchall()
            if _table_exists(conn, "audit_trimestriel")
            else []
        )

    if hist:
        st.markdown("---")
        st.markdown("#### Audits précédents")
        cols = st.columns(min(len(hist), 4))
        for i, h in enumerate(hist):
            with cols[i % 4]:
                st.markdown(
                    f'<div style="border-left:2px solid {PALETTE["blue_green"]};'
                    f'padding:4px 10px;font-size:.85rem;">'
                    f"<strong>{h['saison']} {h['annee']}</strong></div>",
                    unsafe_allow_html=True,
                )


# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 : AUDIT ANNUEL
# ─────────────────────────────────────────────────────────────────────────────


def _annuel_module_score(ex: dict, module: dict) -> int | None:
    notes = [ex.get(field_key) for field_key, _label, _hint in module["indicators"]]
    if any(n is None for n in notes):
        return None
    return int(sum(notes))


def _render_audit_annuel() -> None:
    st.markdown("### Audit Annuel de Clarté & d'Alignement Personnel")
    st.caption(
        "Cadre méthodologique : psychologie comportementale, Théorie de l'Autodétermination "
        "(Deci & Ryan), Théorie de l'Acceptation et de l'Engagement (ACT) et neurosciences "
        "appliquées. Ce protocole remplace l'autocritique moralisante par une observation "
        "clinique et factuelle — réponds avec honnêteté, sans complaisance ni autoflagellation."
    )

    today = today_local()
    annee = st.number_input(
        "Année de l'audit",
        min_value=2024,
        max_value=2040,
        value=today.year,
        step=1,
        key="annuel_annee",
    )
    date_audit = st.date_input("Date de réalisation", value=today, key="annuel_date")

    with db_session() as conn:
        if not _table_exists(conn, "audit_annuel"):
            st.info("Table non initialisée. Lancez `python main.py init-db`.")
            return
        row = conn.execute("SELECT * FROM audit_annuel WHERE annee=?", (annee,)).fetchone()
        ex = dict(row) if row else {}

    annee_int = int(annee)
    all_vals: dict[str, object] = {}

    with st.form(f"audit_annuel_form_{annee_int}"):
        for module in _ANNUEL_MODULES:
            st.markdown(
                f'<div style="border-left:3px solid {module["color"]};'
                f'padding:4px 14px;margin:18px 0 10px;">'
                f"<strong>{module['title']}</strong><br>"
                f'<span style="font-size:.82rem;opacity:.75;">{module["objectif"]}</span></div>',
                unsafe_allow_html=True,
            )

            cols = st.columns(4)
            for (field_key, label, hint), col in zip(module["indicators"], cols, strict=True):
                with col:
                    all_vals[field_key] = st.number_input(
                        label,
                        min_value=1,
                        max_value=5,
                        value=int(ex.get(field_key) or 3),
                        step=1,
                        help=hint,
                        key=f"annuel_{annee_int}_{field_key}",
                    )
            score = _annuel_module_score(ex, module)
            st.caption(
                f"Score du Pilier (dernier enregistrement) : {score} / 20"
                if score is not None
                else "Score du Pilier : pas encore enregistré."
            )

            for field_key, label, hint in module["questions"]:
                st.caption(f"**{label}** — {hint}")
                all_vals[field_key] = st.text_area(
                    label,
                    value=ex.get(field_key) or "",
                    height=90,
                    key=f"annuel_{annee_int}_{field_key}",
                    label_visibility="collapsed",
                    placeholder="Ta réponse ici…",
                )

        # Module 5 — structure dédiée (piliers + intentions Si/Alors)
        st.markdown(
            f'<div style="border-left:3px solid {_ANNUEL_M5["color"]};'
            f'padding:4px 14px;margin:18px 0 10px;">'
            f"<strong>{_ANNUEL_M5['title']}</strong><br>"
            f'<span style="font-size:.82rem;opacity:.75;">{_ANNUEL_M5["objectif"]}</span></div>',
            unsafe_allow_html=True,
        )
        st.markdown("**5.1 Définition des 3 piliers clés (12 mois)**")
        for obj_key, ind_key, label in _ANNUEL_M5["piliers"]:
            st.caption(label)
            col_obj, col_ind = st.columns(2)
            with col_obj:
                all_vals[obj_key] = st.text_input(
                    "Objectif",
                    value=ex.get(obj_key) or "",
                    key=f"annuel_{annee_int}_{obj_key}",
                )
            with col_ind:
                all_vals[ind_key] = st.text_input(
                    "Indicateur de succès",
                    value=ex.get(ind_key) or "",
                    key=f"annuel_{annee_int}_{ind_key}",
                )

        st.markdown("**5.2 Architecture des comportements — Intentions « Si / Alors »**")
        for decl_key, comp_key, label, decl_hint, comp_hint in _ANNUEL_M5["si_alors"]:
            st.caption(label)
            col_si, col_alors = st.columns(2)
            with col_si:
                all_vals[decl_key] = st.text_input(
                    "SI…",
                    value=ex.get(decl_key) or "",
                    placeholder=decl_hint,
                    key=f"annuel_{annee_int}_{decl_key}",
                )
            with col_alors:
                all_vals[comp_key] = st.text_input(
                    "ALORS…",
                    value=ex.get(comp_key) or "",
                    placeholder=comp_hint,
                    key=f"annuel_{annee_int}_{comp_key}",
                )

        # Synthèse du bilan annuel
        st.markdown(
            f'<div style="border-left:3px solid {PALETTE["amber"]};'
            f'padding:4px 14px;margin:18px 0 10px;">'
            f"<strong>Synthèse du Bilan Annuel</strong></div>",
            unsafe_allow_html=True,
        )
        total_score = 0
        total_known = True
        for module in _ANNUEL_MODULES:
            s = _annuel_module_score(ex, module)
            if s is None:
                total_known = False
            else:
                total_score += s
        st.caption(
            f"Total général de maturité comportementale (dernier enregistrement) : "
            f"{total_score if total_known else '—'} / 80"
        )
        col_o1, col_o2, col_o3, col_o4 = st.columns(4)
        objectif_cols = [col_o1, col_o2, col_o3, col_o4]
        for module, col in zip(_ANNUEL_MODULES, objectif_cols, strict=True):
            okey = f"objectif_{module['key']}"
            with col:
                all_vals[okey] = st.number_input(
                    f"Objectif suivant — {module['title'].split('—')[0].strip()}",
                    min_value=0,
                    max_value=20,
                    value=int(ex.get(okey) or 0),
                    step=1,
                    key=f"annuel_{annee_int}_{okey}",
                )

        all_vals["date_audit"] = date_audit.isoformat()

        submitted = st.form_submit_button(f"Sauvegarder — Audit {annee}", use_container_width=True)

    if submitted:
        with db_session() as conn:
            try:
                if ex:
                    set_clause = (
                        ", ".join(f"{k}=?" for k in all_vals) + ", updated_at=datetime('now')"
                    )
                    conn.execute(
                        f"UPDATE audit_annuel SET {set_clause} WHERE annee=?",
                        (*all_vals.values(), annee),
                    )
                else:
                    keys = ", ".join(["annee"] + list(all_vals.keys()))
                    placeholders = ", ".join(["?"] * (1 + len(all_vals)))
                    conn.execute(
                        f"INSERT INTO audit_annuel ({keys}) VALUES ({placeholders})",
                        (annee, *all_vals.values()),
                    )
                conn.commit()
                st.success(f"Audit {annee} enregistré.")
                st.rerun()
            except Exception as exc:
                st.error(f"Erreur : {exc}")

    # Liste des années enregistrées
    with db_session() as conn:
        years = (
            conn.execute("SELECT * FROM audit_annuel ORDER BY annee DESC").fetchall()
            if _table_exists(conn, "audit_annuel")
            else []
        )

    if years:
        st.markdown("---")
        st.markdown("#### Années enregistrées")
        cols = st.columns(min(len(years), 5))
        for i, y in enumerate(years):
            y_dict = dict(y)
            total = 0
            total_known = True
            for module in _ANNUEL_MODULES:
                s = _annuel_module_score(y_dict, module)
                if s is None:
                    total_known = False
                else:
                    total += s
            score_label = f"{total} / 80" if total_known else "—"
            with cols[i % 5]:
                label = y["date_audit"] or str(y["annee"])
                st.markdown(
                    f'<div style="border-left:2px solid {PALETTE["amber"]};'
                    f'padding:4px 10px;font-size:.85rem;">'
                    f"<strong>{y['annee']}</strong><br>"
                    f'<span style="font-size:.75rem;opacity:.65;">{label}</span><br>'
                    f'<span style="font-size:.75rem;opacity:.65;">{score_label}</span></div>',
                    unsafe_allow_html=True,
                )


# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 : NOTES POUR TROP TARD
# ─────────────────────────────────────────────────────────────────────────────

_ETAT_COLORS = {
    "En vie et proche": PALETTE["blue_green"],
    "En vie et distant": PALETTE["sky_blue"],
    "Mort": GRAY,
}
_ETAT_ORDER = ["En vie et proche", "Mort", "En vie et distant", ""]
_LIEN_COLORS = {
    "Famille": PALETTE["amber"],
    "Amour": "#b84c8e",
    "Amis": PALETTE["blue_green"],
    "Complexe": GRAY,
}


def _render_notes_trop_tard() -> None:
    st.markdown("### Notes pour trop tard — Mémoire & Présences")
    st.caption("Pour les personnes qui comptent et celles qui ne sont plus là.")

    if not _npt_tables_ready():
        st.info("Tables non initialisées. Lancez `python main.py init-db`.")
        return

    persons = _npt_get_persons()

    if not persons:
        st.info("Aucune personne enregistrée. Utilise le formulaire ci-dessous.")

    # ── Liste des personnes ──────────────────────────────────────────────────
    for etat_groupe in ["En vie et proche", "Mort", "En vie et distant"]:
        groupe = [p for p in persons if p["etat"] == etat_groupe]
        if not groupe:
            continue
        color = _ETAT_COLORS.get(etat_groupe, GRAY)
        st.markdown(
            f'<div style="border-left:3px solid {color};padding:3px 14px;margin:18px 0 10px;">'
            f'<strong style="font-size:.9rem;text-transform:uppercase;letter-spacing:.08em;">'
            f"{etat_groupe}</strong></div>",
            unsafe_allow_html=True,
        )

        for person in groupe:
            pid = person["id"]
            full_name = f"{person['prenom']} {person['nom']}".strip()
            liens_list = [
                lien.strip() for lien in (person["liens"] or "").split(",") if lien.strip()
            ]
            liens_html = " ".join(
                f'<span style="font-size:.72rem;padding:1px 6px;border-radius:3px;'
                f'background:{_LIEN_COLORS.get(lien, GRAY)}22;color:{_LIEN_COLORS.get(lien, GRAY)};">'
                f"{lien}</span>"
                for lien in liens_list
            )
            prox_html = (
                f'<span style="font-size:.78rem;opacity:.6;">{person["proximite"]}%</span>'
                if person["proximite"] is not None
                else ""
            )
            st.markdown(
                f'<div style="display:flex;align-items:baseline;gap:10px;margin-bottom:4px;">'
                f'<span style="font-size:1rem;">{full_name}</span>'
                f"{liens_html}{prox_html}</div>",
                unsafe_allow_html=True,
            )

            notes = _npt_get_notes(pid)
            with st.expander(f"Notes ({len(notes)})"):
                for note in notes:
                    date_display = note.get("date_note") or "—"
                    contenu = note.get("contenu", "")
                    st.markdown(
                        f'<div style="border-left:2px solid {color}40;padding:6px 12px;'
                        f'margin:4px 0;font-size:.88rem;">'
                        f'<span style="font-size:.75rem;opacity:.55;">{date_display}</span><br>'
                        f'<span style="white-space:pre-wrap;">{contenu}</span></div>',
                        unsafe_allow_html=True,
                    )
                if not notes:
                    st.caption("Aucune note pour cette personne.")

            st.markdown(
                '<hr style="border:none;border-top:1px solid #8ecae620;margin:6px 0;">',
                unsafe_allow_html=True,
            )

    # ── Ajouter une entrée ───────────────────────────────────────────────────
    if persons:
        st.markdown("---")
        st.markdown("#### Ajouter une entrée")
        person_labels = [f"{p['prenom']} {p['nom']}".strip() for p in persons]
        person_ids = [p["id"] for p in persons]

        with st.form("npt_add_note_form"):
            col_sel, col_date = st.columns([2, 1])
            with col_sel:
                selected_idx = st.selectbox(
                    "Personne",
                    range(len(person_labels)),
                    format_func=lambda i: person_labels[i],
                )
            with col_date:
                note_date = st.date_input("Date", value=today_local())
            new_note = st.text_area(
                "Note",
                height=90,
                placeholder="Ce que je ressens, un souvenir, une pensée…",
            )
            if st.form_submit_button("Ajouter au journal", use_container_width=True):
                if not new_note.strip():
                    st.warning("Écris quelque chose avant d'enregistrer.")
                else:
                    _npt_add_note(
                        person_ids[selected_idx],
                        note_date.isoformat(),
                        new_note.strip(),
                    )
                    st.success(f"Note ajoutée pour {person_labels[selected_idx]}.")
                    st.rerun()

    # ── Nouvelle personne ────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Nouvelle personne")

    with st.form("npt_new_person_form"):
        col_fn, col_ln = st.columns(2)
        with col_fn:
            new_prenom = st.text_input("Prénom")
        with col_ln:
            new_nom = st.text_input("Nom")
        col_l, col_e, col_p = st.columns(3)
        with col_l:
            new_liens = st.multiselect("Lien avec toi", ["Famille", "Amour", "Amis", "Complexe"])
        with col_e:
            new_etat = st.selectbox("État", ["En vie et proche", "En vie et distant", "Mort"])
        with col_p:
            new_prox = st.number_input("Proximité (%)", 0, 100, value=50)
        new_intro = st.text_area("Note initiale (optionnel)", height=80)
        if st.form_submit_button("Créer", use_container_width=True):
            if not new_prenom.strip():
                st.warning("Le prénom est requis.")
            else:
                new_id = _npt_add_person(
                    new_prenom.strip(),
                    new_nom.strip(),
                    new_liens,
                    new_etat,
                    int(new_prox),
                )
                if new_intro.strip():
                    _npt_add_note(new_id, today_local().isoformat(), new_intro.strip())
                st.success(f"{new_prenom.strip()} ajouté(e).")
                st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# RENDU PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────


def render(current_week: dict | None) -> None:
    st.header("RÉSONNANCE — Écrits & Profondeur")

    tab_hebdo, tab_trim, tab_annuel, tab_notes = st.tabs(
        [
            "Audit hebdo",
            "Audit trimestriel",
            "Audit annuel",
            "Notes pour trop tard",
        ]
    )

    with tab_hebdo:
        _render_audit_hebdo(current_week)

    with tab_trim:
        _render_audit_trimestriel()

    with tab_annuel:
        _render_audit_annuel()

    with tab_notes:
        _render_notes_trop_tard()
