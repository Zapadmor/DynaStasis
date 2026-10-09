"""Règles de la vue v_score_semaine (10 critères x 10 points) et de v_progression_quotidienne."""

from __future__ import annotations

import pytest

MONDAY = "2026-03-02"  # lundi ; la semaine couvre du 2026-03-02 au 2026-03-08


def _semaine(conn, week_start=MONDAY, **cols):
    cols.setdefault("week_label", f"S {week_start}")
    names = ["week_start", *cols]
    cur = conn.execute(
        f"INSERT INTO semaines_audit ({', '.join(names)}) VALUES ({', '.join('?' * len(names))})",
        [week_start, *cols.values()],
    )
    return cur.lastrowid


def _jour(conn, date, **cols):
    names = ["date_entry", *cols]
    conn.execute(
        f"INSERT INTO vigueur_entries ({', '.join(names)}) VALUES ({', '.join('?' * len(names))})",
        [date, *cols.values()],
    )


def _jours(conn, valeurs, debut=MONDAY, **col):
    """Une entrée par jour à partir de `debut`, avec la colonne donnée."""
    from datetime import date, timedelta

    d0 = date.fromisoformat(debut)
    for i, v in enumerate(valeurs):
        _jour(conn, (d0 + timedelta(days=i)).isoformat(), **{next(iter(col)): v})


def _score(conn, week_start=MONDAY):
    return conn.execute(
        "SELECT * FROM v_score_semaine WHERE week_start = ?", (week_start,)
    ).fetchone()


def test_semaine_vide_ne_valide_que_ecran(conn):
    _semaine(conn)
    row = _score(conn)
    assert row["ok_ecran"] == 1
    assert sum(row[k] for k in row.keys() if k.startswith("ok_")) == 1
    assert row["score_semaine"] == 10.0


def test_score_parfait_vaut_100(conn):
    sid = _semaine(
        conn,
        mode_actif="ecole",
        tsb=0,
        deep_focus_min=1500,
        focus_projets_fond_min=120,
        focus_engagement_min=45,
        social="Connecté/Ressourcé",
    )
    conn.execute("INSERT INTO audit_narrative (semaine_id) VALUES (?)", (sid,))
    for i in range(7):
        _jour(conn, f"2026-03-0{2 + i}", moving_time_min=60, steps=10000, sleep_min=450)
    row = _score(conn)
    assert row["score_semaine"] == 100.0
    assert row["ok_entrainement"] == row["ok_seances"] == row["ok_cloture"] == 1


@pytest.mark.parametrize(("minutes", "attendu"), [(419, 0), (420, 1)])
def test_ok_entrainement_seuil_420_min(conn, minutes, attendu):
    _semaine(conn)
    _jour(conn, MONDAY, moving_time_min=minutes)
    assert _score(conn)["ok_entrainement"] == attendu


@pytest.mark.parametrize(("seances", "attendu"), [(5, 0), (6, 1)])
def test_ok_seances_six_jours_de_30_min(conn, seances, attendu):
    _semaine(conn)
    _jours(conn, [30] * seances + [29] * (7 - seances), moving_time_min=0)
    assert _score(conn)["ok_seances"] == attendu


@pytest.mark.parametrize(("pas", "attendu"), [(69999, 0), (70000, 1)])
def test_ok_pas_seuil_70000_hebdo(conn, pas, attendu):
    _semaine(conn)
    _jour(conn, MONDAY, steps=pas)
    assert _score(conn)["ok_pas"] == attendu


@pytest.mark.parametrize(("sommeil", "attendu"), [(449, 0), (450, 1)])
def test_ok_sommeil_moyenne_450_min(conn, sommeil, attendu):
    _semaine(conn)
    _jours(conn, [sommeil, sommeil], sleep_min=0)
    assert _score(conn)["ok_sommeil"] == attendu


def test_ok_sommeil_est_une_moyenne_pas_une_somme(conn):
    _semaine(conn)
    _jours(conn, [300, 560], sleep_min=0)  # moyenne 430
    assert _score(conn)["ok_sommeil"] == 0


@pytest.mark.parametrize(("tsb", "attendu"), [(-26, 0), (-25, 1), (None, 0)])
def test_ok_charge_fraicheur_semaine_normale(conn, tsb, attendu):
    _semaine(conn, tsb=tsb)
    assert _score(conn)["ok_charge_fraicheur"] == attendu


@pytest.mark.parametrize(
    ("tsb", "hrv_delta", "attendu"),
    [(-6, -1, 0), (-5, -1, 1), (-30, 0, 1), (-30, None, 0)],
)
def test_ok_charge_fraicheur_semaine_de_decharge(conn, tsb, hrv_delta, attendu):
    _semaine(conn, tsb=tsb, hrv_delta_s1=hrv_delta)
    conn.execute(
        "INSERT INTO plan_entrainement (date_jour, titre, type_semaine) VALUES (?, 'x', 'decharge')",
        ("2026-03-04",),
    )
    row = _score(conn)
    assert row["is_deload_week"] == 1
    assert row["ok_charge_fraicheur"] == attendu


def _ecran(conn, minutes, date=MONDAY, package="app.distraction"):
    conn.execute("INSERT OR IGNORE INTO apps_distrayantes (package) VALUES ('app.distraction')")
    conn.execute(
        "INSERT INTO screen_sessions (package, app_name, session_start, session_end,"
        " duration_seconds) VALUES (?, 'a', ?, ?, ?)",
        (package, f"{date} 10:00:00", f"{date} 11:00:00", minutes * 60),
    )


@pytest.mark.parametrize(("minutes", "attendu"), [(211, 0), (210, 1)])
def test_ok_ecran_seuil_210_min(conn, minutes, attendu):
    _semaine(conn)
    _ecran(conn, minutes)
    assert _score(conn)["ok_ecran"] == attendu


def test_ok_ecran_ignore_les_apps_non_distrayantes(conn):
    _semaine(conn)
    _ecran(conn, 600, package="app.utile")
    row = _score(conn)
    assert row["screen_distraction_min"] == 0
    assert row["ok_ecran"] == 1


def test_ok_ecran_valide_si_en_baisse_vs_semaine_precedente(conn):
    _semaine(conn, "2026-02-23")
    _semaine(conn)
    _ecran(conn, 400, date="2026-02-24")
    _ecran(conn, 300, date="2026-03-03")
    assert _score(conn)["ok_ecran"] == 1  # 300 > 210 mais < 400
    _ecran(conn, 200, date="2026-03-04")  # 500 > 400
    assert _score(conn)["ok_ecran"] == 0


@pytest.mark.parametrize(
    ("mode", "minutes", "attendu"),
    [
        ("Entreprise", 899, 0),
        ("Entreprise", 900, 1),
        ("ecole", 1499, 0),
        ("ecole", 1500, 1),
        (None, 630, 0),
        (None, 631, 1),
    ],
)
def test_ok_deep_focus_seuil_selon_le_mode(conn, mode, minutes, attendu):
    _semaine(conn, mode_actif=mode, deep_focus_min=minutes)
    assert _score(conn)["ok_deep_focus"] == attendu


@pytest.mark.parametrize(("minutes", "attendu"), [(119, 0), (120, 1)])
def test_ok_projets_fond_seuil_120_min(conn, minutes, attendu):
    _semaine(conn, focus_projets_fond_min=minutes)
    assert _score(conn)["ok_projets_fond"] == attendu


@pytest.mark.parametrize(
    ("minutes", "jours_engagement", "attendu"), [(44, 0, 0), (45, 0, 1), (0, 1, 1), (0, 0, 0)]
)
def test_ok_engagement_focus_ou_jour_engagement(conn, minutes, jours_engagement, attendu):
    sid = _semaine(conn, focus_engagement_min=minutes)
    conn.execute(
        "INSERT INTO audit_narrative (semaine_id, jours_engagement_semaine) VALUES (?, ?)",
        (sid, jours_engagement),
    )
    assert _score(conn)["ok_engagement"] == attendu


def test_ok_cloture_exige_social_et_audit_narratif(conn):
    sid = _semaine(conn, social="Connecté/Ressourcé")
    assert _score(conn)["ok_cloture"] == 0  # pas d'audit narratif
    conn.execute("INSERT INTO audit_narrative (semaine_id) VALUES (?)", (sid,))
    assert _score(conn)["ok_cloture"] == 1
    conn.execute("UPDATE semaines_audit SET social = 'Isolé' WHERE id = ?", (sid,))
    assert _score(conn)["ok_cloture"] == 0


def test_hrv_mediane_et_delta_vs_semaine_precedente(conn):
    _semaine(conn, "2026-02-23")
    _semaine(conn)
    _jours(conn, [50, 60, 100], debut="2026-02-23", hrv=0)  # médiane 60
    _jours(conn, [70, 80], hrv=0)  # médiane (70+80)/2 = 75
    row = _score(conn)
    assert row["hrv_moy"] == 75.0
    assert row["hrv_moy_prev"] == 60.0
    assert row["hrv_delta"] == 15.0


def test_semaine_gelee_ignoree_comme_reference(conn):
    _semaine(conn, "2026-02-16")
    _semaine(conn, "2026-02-23", is_frozen=1)
    _semaine(conn)
    _jours(conn, [40], debut="2026-02-16", hrv=0)
    _jours(conn, [90], debut="2026-02-23", hrv=0)
    _jours(conn, [70], hrv=0)
    row = _score(conn)
    assert row["hrv_moy_prev"] == 40.0  # saute la semaine gelée


# --- Journée parfaite (6 critères) -------------------------------------------------------


def _jour_parfait(conn, date="2026-03-03", **vigueur):
    _semaine(conn)
    sid = conn.execute("SELECT id FROM semaines_audit").fetchone()[0]
    conn.execute("INSERT INTO habitude_logs (date_log, semaine_id) VALUES (?, ?)", (date, sid))
    if vigueur:
        _jour(conn, date, **vigueur)
    return conn.execute(
        "SELECT * FROM v_progression_quotidienne WHERE date_log = ?", (date,)
    ).fetchone()


def test_journee_sans_donnees_seul_ecran_valide(conn):
    row = _jour_parfait(conn)
    assert row["ok_ecran"] == 1
    assert (row["score_6"], row["rank"]) == (1, "D")


def test_journee_parfaite_rang_s(conn):
    sid = _semaine(conn, mode_actif="ecole")
    d = "2026-03-03"
    conn.execute("INSERT INTO habitude_logs (date_log, semaine_id) VALUES (?, ?)", (d, sid))
    _jour(conn, d, moving_time_min=60, sleep_min=450, steps=10000)
    conn.execute(
        "INSERT INTO focus_sessions (numero_session, date_session, heure_debut, duree_min,"
        " piliers, source, semaine_id) VALUES (1, ?, '09:00', 240, 'LOGOS', 'manual', ?)",
        (d, sid),
    )
    row = conn.execute(
        "SELECT * FROM v_progression_quotidienne WHERE date_log = ?", (d,)
    ).fetchone()
    assert (row["score_6"], row["pct"], row["rank"]) == (6, 100.0, "S")


@pytest.mark.parametrize(
    ("col", "seuil", "critere"),
    [
        ("sleep_min", 450, "ok_sommeil"),
        ("steps", 10000, "ok_pas"),
        ("moving_time_min", 60, "ok_sport"),
    ],
)
def test_journee_seuils_vigueur(conn, col, seuil, critere):
    assert _jour_parfait(conn, **{col: seuil - 1})[critere] == 0
    conn.execute("UPDATE vigueur_entries SET " + col + " = ?", (seuil,))
    row = conn.execute("SELECT * FROM v_progression_quotidienne").fetchone()
    assert row[critere] == 1


def test_journee_repos_planifie_valide_le_sport(conn):
    _semaine(conn)
    conn.execute(
        "INSERT INTO plan_entrainement (date_jour, titre, is_repos) VALUES ('2026-03-03', 'Repos', 1)"
    )
    sid = conn.execute("SELECT id FROM semaines_audit").fetchone()[0]
    conn.execute(
        "INSERT INTO habitude_logs (date_log, semaine_id) VALUES ('2026-03-03', ?)", (sid,)
    )
    assert conn.execute("SELECT ok_sport FROM v_progression_quotidienne").fetchone()[0] == 1


@pytest.mark.parametrize(
    ("mode", "minutes", "attendu"),
    [
        ("Entreprise", 149, 0),
        ("Entreprise", 150, 1),
        ("ecole", 239, 0),
        ("ecole", 240, 1),
        (None, 90, 1),
    ],
)
def test_journee_seuil_focus_selon_le_mode(conn, mode, minutes, attendu):
    sid = _semaine(conn, mode_actif=mode)
    d = "2026-03-03"
    conn.execute("INSERT INTO habitude_logs (date_log, semaine_id) VALUES (?, ?)", (d, sid))
    conn.execute(
        "INSERT INTO focus_sessions (numero_session, date_session, heure_debut, duree_min,"
        " source, semaine_id) VALUES (1, ?, '09:00', ?, 'manual', ?)",
        (d, minutes, sid),
    )
    assert conn.execute("SELECT ok_focus FROM v_progression_quotidienne").fetchone()[0] == attendu


@pytest.mark.parametrize(("pilier", "attendu"), [("LOGOS", 1), ("FORGE_PRO", 1), ("VIGUEUR", 0)])
def test_journee_focus_strategique_30_min_sur_pilier_strategique(conn, pilier, attendu):
    sid = _semaine(conn)
    d = "2026-03-03"
    conn.execute("INSERT INTO habitude_logs (date_log, semaine_id) VALUES (?, ?)", (d, sid))
    conn.execute(
        "INSERT INTO focus_sessions (numero_session, date_session, heure_debut, duree_min,"
        " piliers, source, semaine_id) VALUES (1, ?, '09:00', 30, ?, 'manual', ?)",
        (d, pilier, sid),
    )
    assert (
        conn.execute("SELECT ok_focus_strat FROM v_progression_quotidienne").fetchone()[0]
        == attendu
    )


@pytest.mark.parametrize(("score", "rang"), [(6, "S"), (5, "A"), (4, "B"), (3, "C"), (2, "D")])
def test_rangs_journee(conn, score, rang):
    sid = _semaine(conn)
    d = "2026-03-03"
    conn.execute("INSERT INTO habitude_logs (date_log, semaine_id) VALUES (?, ?)", (d, sid))
    # ok_ecran est toujours à 1 : on active (score - 1) autres critères
    cols = [("moving_time_min", 60), ("sleep_min", 450), ("steps", 10000)]
    vals = dict(cols[: min(score - 1, 3)])
    if vals:
        _jour(conn, d, **vals)
    extra = score - 1 - len(vals)
    if extra:
        conn.execute(
            "INSERT INTO focus_sessions (numero_session, date_session, heure_debut, duree_min,"
            " piliers, source, semaine_id) VALUES (1, ?, '09:00', ?, ?, 'manual', ?)",
            (d, 240 if extra == 2 else 90, "LOGOS" if extra == 2 else None, sid),
        )
    row = conn.execute("SELECT score_6, rank FROM v_progression_quotidienne").fetchone()
    assert (row["score_6"], row["rank"]) == (score, rang)
