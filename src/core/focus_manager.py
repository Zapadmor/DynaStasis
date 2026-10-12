from __future__ import annotations

from datetime import datetime

from src import pillars
from src.core import user_config
from src.core.system_engine import get_or_create_week_id, trigger_cascade_week
from src.core.tz import tz
from src.database.connection import db_session

# Piliers "parents" — utilisés pour la répartition agrégée (sidebar, SYSTÈME de l'audit).
PILIERS = pillars.keys()

# Tags flaguables sur une session focus. FORGE est éclaté en sous-tags : le critère « engagement »
# (libellé configurable, désactivable) et les hard skills sont permanents ; le sous-tag « pro »
# n'est pertinent que dans un mode marqué `tag_pro` (config/user.toml). Le travail académique se
# tague LOGOS. Les autres piliers restent des tags simples.
TAGS: dict[str, tuple[str, str]] = {
    "FORGE_ENGAGEMENT": ("FORGE", f"Forge — {user_config.engagement_libelle()}"),
    "FORGE_HARDSKILLS": ("FORGE", "Forge — Hard Skills"),
    "FORGE_PRO": ("FORGE", "Forge — Entreprise"),
    "LOGOS": ("LOGOS", "Logos — Académique"),
    "VIGUEUR": ("VIGUEUR", "Vigueur"),
    "RESONNANCE": ("RESONNANCE", "Résonnance"),
    "SYSTEME": ("SYSTEME", "Système"),
}


def forge_tag_for_mode(mode_actif: str | None) -> str | None:
    """Sous-tag FORGE additionnel pertinent selon le mode de la semaine courante :
    FORGE_PRO si le mode est configuré avec `tag_pro`, sinon None."""
    mode = user_config.modes().get(mode_actif or "")
    return "FORGE_PRO" if mode and mode.tag_pro else None


def tags_proposes(mode_actif: str | None) -> list[str]:
    """Tags offerts à la sélection : piliers actifs, FORGE_* selon le mode et l'engagement."""
    forge_dispo = {"FORGE_HARDSKILLS", forge_tag_for_mode(mode_actif)} - {None}
    if user_config.engagement_actif():
        forge_dispo.add("FORGE_ENGAGEMENT")
    return [
        t
        for t, (pilier, _) in TAGS.items()
        if user_config.pilier_actif(pilier) and (not t.startswith("FORGE_") or t in forge_dispo)
    ]


def start_focus_session(
    channel: str = "local", piliers: list[str] | None = None
) -> tuple[bool, str]:
    """Démarre une session de deep work si aucune n'est déjà active. Règle R6."""
    now = datetime.now(tz())
    date_session = now.strftime("%Y-%m-%d")
    heure_debut = now.strftime("%H:%M")
    week_id = get_or_create_week_id(date_session)
    piliers_csv = ",".join(p for p in (piliers or []) if p in TAGS) or None

    with db_session() as conn:
        active = conn.execute("SELECT id FROM focus_sessions WHERE heure_fin IS NULL").fetchone()
        if active:
            return False, "Une session est déjà en cours."

        max_row = conn.execute(
            "SELECT COALESCE(MAX(numero_session), 0) AS m FROM focus_sessions"
        ).fetchone()
        next_num = max_row["m"] + 1

        conn.execute(
            """INSERT INTO focus_sessions
               (numero_session, date_session, heure_debut, channel, piliers, source, semaine_id)
               VALUES (?, ?, ?, ?, ?, 'local_cli', ?)""",
            (next_num, date_session, heure_debut, channel, piliers_csv, week_id),
        )
    return True, f"Session #{next_num} démarrée à {heure_debut}."


def stop_focus_session() -> tuple[bool, str]:
    """Ferme la session active, calcule la durée et déclenche la cascade."""
    now = datetime.now(tz())
    heure_fin = now.strftime("%H:%M")

    with db_session() as conn:
        active = conn.execute(
            "SELECT id, heure_debut, semaine_id FROM focus_sessions WHERE heure_fin IS NULL"
        ).fetchone()
        if not active:
            return False, "Aucune session active à arrêter."

        fmt = "%H:%M"
        delta = datetime.strptime(heure_fin, fmt) - datetime.strptime(active["heure_debut"], fmt)
        duree_min = max(round(delta.seconds / 60.0, 1), 1.0)

        conn.execute(
            "UPDATE focus_sessions SET heure_fin = ?, duree_min = ? WHERE id = ?",
            (heure_fin, duree_min, active["id"]),
        )
        week_id = active["semaine_id"]

    trigger_cascade_week(week_id)
    return True, f"Session arrêtée. Durée : {duree_min} min."


def get_active_session() -> dict | None:
    """Retourne la session en cours ou None."""
    with db_session() as conn:
        row = conn.execute("SELECT * FROM focus_sessions WHERE heure_fin IS NULL").fetchone()
    return dict(row) if row else None


def get_week_sessions(week_id: int) -> list[dict]:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM focus_sessions WHERE semaine_id = ? ORDER BY date_session, heure_debut",
            (week_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_week_tag_breakdown(week_id: int) -> dict[str, float]:
    """Minutes focus de la semaine par tag exact (ex: FORGE_ENGAGEMENT, FORGE_PRO…).
    Une session multi-taguée répartit sa durée à parts égales entre ses tags.
    Clé 'NON_TAGUE' pour le reste."""
    breakdown: dict[str, float] = dict.fromkeys(TAGS, 0.0)
    breakdown["NON_TAGUE"] = 0.0

    for s in get_week_sessions(week_id):
        duree = s["duree_min"] or 0.0
        if duree <= 0:
            continue
        tags = [t for t in (s["piliers"] or "").split(",") if t in TAGS]
        if not tags:
            breakdown["NON_TAGUE"] += duree
            continue
        part = duree / len(tags)
        for t in tags:
            breakdown[t] += part

    return breakdown


def get_week_pilier_breakdown(week_id: int) -> dict[str, float]:
    """Minutes focus de la semaine par pilier parent (les sous-tags FORGE_* sont
    agrégés sous 'FORGE'). Clé 'NON_TAGUE' pour le reste."""
    tag_breakdown = get_week_tag_breakdown(week_id)
    breakdown: dict[str, float] = dict.fromkeys(PILIERS, 0.0)
    breakdown["NON_TAGUE"] = tag_breakdown["NON_TAGUE"]

    for tag, minutes in tag_breakdown.items():
        if tag == "NON_TAGUE":
            continue
        parent, _ = TAGS[tag]
        breakdown[parent] += minutes

    return breakdown
