"""Rendu des pages Streamlit (AppTest) sur une base temporaire."""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest


def _app(page):
    from src.app.views import dashboard, forge, logos, resonance, systeme, vigueur

    pages = {
        "dashboard": lambda: dashboard.render(None),
        "forge": lambda: forge.render(None),
        "logos": lambda: logos.render(None),
        "vigueur": vigueur.render,
        "resonance": lambda: resonance.render(None),
        "systeme": systeme.render,
    }
    pages[page]()


@pytest.mark.parametrize("page", ["dashboard", "forge", "logos", "vigueur", "resonance", "systeme"])
def test_page_se_rend_sur_base_vide(db, page):
    at = AppTest.from_function(_app, args=(page,), default_timeout=60).run()
    assert not at.exception
    assert not at.error, [e.value for e in at.error]


@pytest.mark.parametrize("page", ["dashboard", "forge", "logos", "vigueur", "resonance", "systeme"])
def test_page_se_rend_sur_base_de_demo(demo_db, page):
    at = AppTest.from_function(_app, args=(page,), default_timeout=60).run()
    assert not at.exception
    assert not at.error, [e.value for e in at.error]


def test_historique_journal_avec_semaine_gelee(db, caplog):
    import sqlite3

    with sqlite3.connect(db) as c:
        c.execute(
            "INSERT INTO semaines_audit (week_start, week_label, score_semaine, is_frozen)"
            " VALUES ('2026-03-02', 'S10', 55.0, 0), ('2026-03-09', 'S11', NULL, 1)"
        )

    def app():
        from src.app.views import dashboard

        dashboard._render_history()

    at = AppTest.from_function(app, default_timeout=60).run()
    assert not at.exception
    (df,) = [e.value for e in at.dataframe]
    assert sorted(df["Score"].dropna()) == ["55", "freeze"]


def test_systeme_affiche_le_statut_des_sources(db):
    import sqlite3

    with sqlite3.connect(db) as c:
        c.execute(
            "INSERT INTO sync_checkpoints (source, statut, last_success_at, last_error_at,"
            " last_error, last_duration_s) VALUES ('intervals', 'erreur', '2026-10-09 07:00:00',"
            " '2026-10-10 07:00:00', 'Missing secret', 1.5)"
        )

    def app():
        from src.app.views import systeme

        systeme._render_sync_status()

    at = AppTest.from_function(app, default_timeout=60).run()
    assert not at.exception
    (df,) = [e.value for e in at.dataframe]
    ligne = df[df["Source"] == "intervals"].iloc[0]
    assert ligne["Statut"] == "Erreur" and "Missing secret" in ligne["Dernière erreur"]
    assert set(df["Source"]) == {"intervals", "strava", "logos", "finance"}


def _vigueur_app():
    from src.app.views import vigueur

    vigueur.render()


def test_vigueur_deux_onglets_seulement(demo_db):
    at = AppTest.from_function(_vigueur_app, default_timeout=60).run()
    assert not at.exception
    assert [t.label for t in at.tabs] == ["Charge & Récupération", "Log Workouts"]


def test_vigueur_jalons_du_macro_cycle_sont_cochables(demo_db):
    import sqlite3

    at = AppTest.from_function(_vigueur_app, default_timeout=60).run()
    assert not at.exception
    cases = [c for c in at.checkbox if str(c.key).startswith("jalon_")]
    assert cases, "le macro-cycle de démonstration doit afficher des jalons"
    ouvertes = [c for c in cases if not c.value]
    cible = ouvertes[0]
    tache_id = int(str(cible.key).removeprefix("jalon_"))
    cible.check().run()
    assert not at.exception
    with sqlite3.connect(demo_db) as c:
        assert (
            c.execute("SELECT statut FROM taches WHERE id = ?", (tache_id,)).fetchone()[0] == "fait"
        )
    # le jalon reste visible, coché
    assert any(str(c.key) == f"jalon_{tache_id}" and c.value for c in at.checkbox)


def _app_vigueur():
    from src.app.views import vigueur

    vigueur.render()


def _sessions(db):
    import sqlite3

    with sqlite3.connect(db) as c:
        return c.execute("SELECT COUNT(*) FROM workout_sessions").fetchone()[0]


def test_log_workouts_saisie_apres_coup_depuis_un_template(demo_db):
    import sqlite3

    avant = _sessions(demo_db)
    at = AppTest.from_function(_app_vigueur, default_timeout=60).run()
    assert not at.exception
    at.selectbox(key="wk_tpl").select_index(0).run()
    next(b for b in at.button if b.label == "Charger le template").click().run()
    assert not at.exception
    assert at.session_state["wk"]["elements"], "le template doit préremplir des exercices"
    at.number_input(key="wk_duree").set_value(45).run()
    at.button(key="wk_save").click().run()
    assert not at.exception
    assert not at.error, [e.value for e in at.error]
    assert _sessions(demo_db) == avant + 1
    with sqlite3.connect(demo_db) as c:
        c.row_factory = sqlite3.Row
        s = c.execute("SELECT * FROM workout_sessions ORDER BY id DESC LIMIT 1").fetchone()
        nb_series = c.execute(
            "SELECT COUNT(*) FROM workout_session_sets x JOIN workout_session_exercises e "
            "ON e.id = x.session_ex_id WHERE e.session_id = ?",
            (s["id"],),
        ).fetchone()[0]
        wm = c.execute(
            "SELECT workout_min FROM vigueur_entries WHERE date_entry = ?", (s["date_entry"],)
        ).fetchone()[0]
    assert s["duration_min"] == 45 and wm == 45  # durée saisie → journal quotidien
    assert nb_series > 0 and s["session_volume_kg"] is not None
    assert at.session_state["wk"]["elements"] == []  # formulaire remis à zéro


def test_log_workouts_sans_serie_rien_n_est_enregistre(demo_db):
    avant = _sessions(demo_db)
    at = AppTest.from_function(_app_vigueur, default_timeout=60).run()
    # le bouton d'enregistrement est désactivé tant qu'aucun exercice n'est saisi
    assert at.button(key="wk_save").disabled
    assert _sessions(demo_db) == avant


def test_log_workouts_nouvel_exercice_et_emom(demo_db):
    import sqlite3

    at = AppTest.from_function(_app_vigueur, default_timeout=60).run()
    at.text_input(key="wk_new_name").set_value("Planche").run()
    at.selectbox(key="wk_new_kind").select("Statique (secondes)").run()
    at.button(key="wk_new_btn").click().run()
    assert not at.exception
    (el,) = at.session_state["wk"]["elements"]
    assert el["info"] == {
        "name": "Planche",
        "create": True,
        "load_formula": "bw_plus_weight",
        "unit": "sec",
    }
    # un EMOM de 2 exercices exige une durée multiple de 2 : 5 min refusé, 6 min accepté
    with sqlite3.connect(demo_db) as c:
        autre = c.execute("SELECT name FROM exercise_library ORDER BY name LIMIT 1").fetchone()[0]
    at.multiselect(key="wk_emom_noms").set_value(["Planche", autre]).run()
    at.number_input(key="wk_emom_min").set_value(5).run()
    at.button(key="wk_emom_btn").click().run()
    assert any("multiple de 2" in e.value for e in at.error)
    assert len(at.session_state["wk"]["elements"]) == 1  # rien créé
    at.number_input(key="wk_emom_min").set_value(6).run()
    at.button(key="wk_emom_btn").click().run()
    assert not at.exception
    emom = at.session_state["wk"]["elements"][-1]
    assert emom["kind"] == "emom" and [r["minute"] for r in emom["rows"]] == [1, 2, 3, 4, 5, 6]
    assert [r["exercice"] for r in emom["rows"]] == ["Planche", autre] * 3
    # un nom déjà pris est refusé
    at.text_input(key="wk_new_name").set_value("planche").run()
    at.button(key="wk_new_btn").click().run()
    assert any("existe déjà" in e.value for e in at.error)
    with sqlite3.connect(demo_db) as c:  # rien n'est écrit tant que la séance n'est pas enregistrée
        assert (
            c.execute("SELECT COUNT(*) FROM exercise_library WHERE name = 'Planche'").fetchone()[0]
            == 0
        )
