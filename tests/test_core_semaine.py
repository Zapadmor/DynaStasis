"""system_engine (semaine, gel, cascade), habit_manager et focus_manager."""

from __future__ import annotations

from datetime import datetime

import pytest

from src.core import focus_manager, habit_manager, system_engine
from src.database.connection import db_session


def _semaine(week_id):
    with db_session() as c:
        return dict(c.execute("SELECT * FROM semaines_audit WHERE id = ?", (week_id,)).fetchone())


def _session(c, week_id, date, duree, piliers=None, num=None, **kw):
    num = (
        num
        or c.execute("SELECT COALESCE(MAX(numero_session), 0) + 1 FROM focus_sessions").fetchone()[
            0
        ]
    )
    c.execute(
        "INSERT INTO focus_sessions (numero_session, date_session, heure_debut, duree_min, piliers,"
        " source, semaine_id) VALUES (?, ?, ?, ?, ?, 'manual', ?)",
        (num, date, f"{8 + num:02d}:00", duree, piliers, week_id),
    )


# --- get_or_create_week_id -----------------------------------------------------------------


def test_semaine_calee_sur_le_lundi_avec_libelle(db):
    wid = system_engine.get_or_create_week_id("2026-03-05")  # jeudi
    row = _semaine(wid)
    assert row["week_start"] == "2026-03-02"
    assert row["week_label"] == "Audit S10 – 02/03/2026"


def test_semaine_idempotente_et_meme_id_pour_tous_les_jours(db):
    ids = {system_engine.get_or_create_week_id(f"2026-03-0{d}") for d in range(2, 9)}
    assert len(ids) == 1
    assert system_engine.get_or_create_week_id("2026-03-09") not in ids


def test_mode_actif_depuis_sequences_mode_sinon_ecole(db):
    with db_session() as c:
        c.execute(
            "INSERT INTO sequences_mode (numero, lieu, date_debut, date_fin)"
            " VALUES (1, 'entreprise', '2026-03-02', '2026-03-13')"
        )
    assert _semaine(system_engine.get_or_create_week_id("2026-03-04"))["mode_actif"] == "entreprise"
    assert _semaine(system_engine.get_or_create_week_id("2026-03-16"))["mode_actif"] == "ecole"


# --- gel hebdomadaire --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("debut", "fin", "gelee"),
    [
        ("2026-03-08", "2026-03-20", 1),  # chevauche le dimanche de la semaine
        ("2026-02-20", "2026-03-02", 1),  # finit le lundi
        ("2026-03-04", "2026-03-04", 1),  # un jour au milieu
        ("2026-02-20", "2026-03-01", 0),  # finit la veille
        ("2026-03-09", "2026-03-20", 0),  # commence la semaine suivante
    ],
)
def test_semaine_creee_pendant_un_gel_est_marquee_gelee(db, debut, fin, gelee):
    with db_session() as c:
        c.execute(
            "INSERT INTO system_freezes (date_debut, date_fin, raison) VALUES (?, ?, 'test')",
            (debut, fin),
        )
    assert _semaine(system_engine.get_or_create_week_id("2026-03-03"))["is_frozen"] == gelee


def test_gel_ajoute_apres_coup_ne_modifie_pas_une_semaine_existante(db):
    wid = system_engine.get_or_create_week_id("2026-03-03")
    with db_session() as c:
        c.execute(
            "INSERT INTO system_freezes (date_debut, date_fin, raison)"
            " VALUES ('2026-03-01', '2026-03-31', 'test')"
        )
    assert _semaine(system_engine.get_or_create_week_id("2026-03-03"))["is_frozen"] == 0
    assert wid == system_engine.get_or_create_week_id("2026-03-04")


def test_semaine_gelee_exclue_de_la_reference_hrv(db):
    ids = [
        system_engine.get_or_create_week_id(d) for d in ("2026-02-16", "2026-02-23", "2026-03-02")
    ]
    with db_session() as c:
        c.execute("UPDATE semaines_audit SET is_frozen = 1 WHERE id = ?", (ids[1],))
        for date, hrv in (("2026-02-16", 40), ("2026-02-23", 90), ("2026-03-02", 70)):
            c.execute("INSERT INTO vigueur_entries (date_entry, hrv) VALUES (?, ?)", (date, hrv))
    system_engine.trigger_cascade_week(ids[2])
    assert _semaine(ids[2])["hrv_delta_s1"] == 30.0  # 70 - 40, la semaine gelée est sautée


# --- trigger_cascade_week --------------------------------------------------------------------


def test_cascade_recalcule_focus_habitudes_et_score(db):
    wid = system_engine.get_or_create_week_id("2026-03-02")
    with db_session() as c:
        _session(c, wid, "2026-03-02", 60.0, "FORGE_ENGAGEMENT")
        _session(c, wid, "2026-03-03", 40.0, "FORGE_PRO,LOGOS")
        _session(c, wid, "2026-03-04", 20.0)
        for d, lecture, jeune in (("2026-03-02", 1, 1), ("2026-03-03", 1, 0), ("2026-03-04", 0, 1)):
            c.execute(
                "INSERT INTO habitude_logs (date_log, semaine_id, lecture_10min, jeune_intermittent,"
                " bonne_recup_8h9h, sport_marche_45min) VALUES (?, ?, ?, ?, 1, ?)",
                (d, wid, lecture, jeune, lecture),
            )
    system_engine.trigger_cascade_week(wid)
    row = _semaine(wid)
    assert row["deep_focus_min"] == 120.0
    assert row["focus_engagement_min"] == 60.0
    assert row["focus_projets_fond_min"] == 40.0  # FORGE_PRO + LOGOS à parts égales
    assert (row["nuits_bonne_recup"], row["sessions_lecture"]) == (3, 2)
    assert (row["sessions_sport"], row["sessions_jeune"]) == (2, 2)
    assert row["score_semaine"] == 20.0  # écran (par défaut) + engagement >= 45 min


def test_cascade_sans_donnees_met_les_compteurs_a_zero(db):
    wid = system_engine.get_or_create_week_id("2026-03-02")
    system_engine.trigger_cascade_week(wid)
    row = _semaine(wid)
    assert row["deep_focus_min"] == 0.0
    assert (row["nuits_bonne_recup"], row["sessions_lecture"]) == (0, 0)


def test_cascade_calcule_le_delta_hrv(db):
    prev = system_engine.get_or_create_week_id("2026-02-23")
    wid = system_engine.get_or_create_week_id("2026-03-02")
    with db_session() as c:
        c.execute("INSERT INTO vigueur_entries (date_entry, hrv) VALUES ('2026-02-24', 60)")
        c.execute("INSERT INTO vigueur_entries (date_entry, hrv) VALUES ('2026-03-03', 67.34)")
    system_engine.trigger_cascade_week(wid)
    assert _semaine(wid)["hrv_delta_s1"] == 7.3
    system_engine.trigger_cascade_week(prev)
    assert _semaine(prev)["hrv_delta_s1"] is None


# --- habit_manager ------------------------------------------------------------------------------


def test_upsert_habit_log_cree_le_journal_et_declenche_la_cascade(db):
    wid = habit_manager.upsert_habit_log("2026-03-03", lecture=True, jeune=False, note="ok")
    (log,) = habit_manager.get_week_habits(wid)
    assert (log["date_log"], log["lecture_10min"], log["jeune_intermittent"]) == (
        "2026-03-03",
        1,
        0,
    )
    assert log["note_libre"] == "ok"
    assert log["jour_label"] == "Tuesday"
    assert _semaine(wid)["sessions_lecture"] == 1


def test_upsert_habit_log_met_a_jour_le_meme_jour(db):
    wid = habit_manager.upsert_habit_log("2026-03-03", lecture=True)
    assert habit_manager.upsert_habit_log("2026-03-03", lecture=False, jeune=True) == wid
    (log,) = habit_manager.get_week_habits(wid)
    assert (log["lecture_10min"], log["jeune_intermittent"]) == (0, 1)
    row = _semaine(wid)
    assert (row["sessions_lecture"], row["sessions_jeune"]) == (0, 1)


def test_get_week_habits_trie_par_date_et_isole_par_semaine(db):
    w1 = habit_manager.upsert_habit_log("2026-03-04")
    habit_manager.upsert_habit_log("2026-03-02")
    w2 = habit_manager.upsert_habit_log("2026-03-10")
    assert [h["date_log"] for h in habit_manager.get_week_habits(w1)] == [
        "2026-03-02",
        "2026-03-04",
    ]
    assert len(habit_manager.get_week_habits(w2)) == 1


# --- focus_manager ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mode", "tag"), [("entreprise", "FORGE_PRO"), ("ecole", None), (None, None)]
)
def test_forge_tag_for_mode(mode, tag):
    assert focus_manager.forge_tag_for_mode(mode) == tag


class _Horloge:
    """Remplace focus_manager.datetime pour contrôler l'heure courante."""

    now_value = datetime(2026, 3, 3, 9, 0)

    @classmethod
    def now(cls, tz=None):
        return cls.now_value

    strptime = staticmethod(datetime.strptime)


@pytest.fixture
def horloge(monkeypatch):
    monkeypatch.setattr(focus_manager, "datetime", _Horloge)
    _Horloge.now_value = datetime(2026, 3, 3, 9, 0)
    return _Horloge


def test_demarrer_puis_arreter_une_session_calcule_la_duree(db, horloge):
    ok, msg = focus_manager.start_focus_session(piliers=["LOGOS", "BIDON", "FORGE_PRO"])
    assert ok and "#1" in msg
    active = focus_manager.get_active_session()
    assert active["piliers"] == "LOGOS,FORGE_PRO"  # tags inconnus écartés
    assert active["heure_debut"] == "09:00"

    horloge.now_value = datetime(2026, 3, 3, 10, 30)
    ok, msg = focus_manager.stop_focus_session()
    assert ok and "90.0" in msg
    assert focus_manager.get_active_session() is None
    wid = system_engine.get_or_create_week_id("2026-03-03")
    assert _semaine(wid)["deep_focus_min"] == 90.0


def test_pas_de_deuxieme_session_simultanee(db, horloge):
    assert focus_manager.start_focus_session()[0] is True
    ok, msg = focus_manager.start_focus_session()
    assert ok is False and "déjà en cours" in msg


def test_arreter_sans_session_active(db, horloge):
    ok, msg = focus_manager.stop_focus_session()
    assert ok is False and "Aucune session" in msg


def test_duree_minimale_une_minute_et_numerotation(db, horloge):
    focus_manager.start_focus_session()
    focus_manager.stop_focus_session()  # même minute
    wid = system_engine.get_or_create_week_id("2026-03-03")
    assert focus_manager.get_week_sessions(wid)[0]["duree_min"] == 1.0
    horloge.now_value = datetime(2026, 3, 3, 11, 0)
    assert "#2" in focus_manager.start_focus_session()[1]


def test_session_sans_pilier_stocke_null(db, horloge):
    focus_manager.start_focus_session(piliers=["INCONNU"])
    assert focus_manager.get_active_session()["piliers"] is None


def test_repartition_par_tag_a_parts_egales(db):
    wid = system_engine.get_or_create_week_id("2026-03-03")
    with db_session() as c:
        _session(c, wid, "2026-03-03", 60.0, "LOGOS")
        _session(c, wid, "2026-03-03", 60.0, "LOGOS,VIGUEUR")
        _session(c, wid, "2026-03-04", 30.0)
        _session(c, wid, "2026-03-04", 30.0, "INCONNU")
        _session(c, wid, "2026-03-05", 0.0, "LOGOS")  # durée nulle ignorée
    tags = focus_manager.get_week_tag_breakdown(wid)
    assert (tags["LOGOS"], tags["VIGUEUR"], tags["NON_TAGUE"]) == (90.0, 30.0, 60.0)
    assert tags["FORGE_PRO"] == 0.0


def test_repartition_par_pilier_agrege_les_sous_tags_forge(db):
    wid = system_engine.get_or_create_week_id("2026-03-03")
    with db_session() as c:
        _session(c, wid, "2026-03-03", 40.0, "FORGE_ENGAGEMENT,FORGE_PRO")
        _session(c, wid, "2026-03-03", 30.0, "FORGE_HARDSKILLS")
        _session(c, wid, "2026-03-04", 10.0, "SYSTEME")
        _session(c, wid, "2026-03-04", 5.0)
    piliers = focus_manager.get_week_pilier_breakdown(wid)
    assert piliers["FORGE"] == 70.0
    assert (piliers["SYSTEME"], piliers["NON_TAGUE"], piliers["LOGOS"]) == (10.0, 5.0, 0.0)
    assert set(piliers) == set(focus_manager.PILIERS) | {"NON_TAGUE"}
