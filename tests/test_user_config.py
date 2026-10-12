"""Configuration utilisateur : défauts, validation, effet sur le score, migration des anciens modes."""

from __future__ import annotations

import sqlite3
import tomllib
from datetime import date

import pytest

from src.core import system_engine, tz, user_config
from src.database import connection


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """Écrit un user.toml temporaire et recharge la configuration."""

    def _write(content: str):
        path = tmp_path / "user.toml"
        path.write_text(content, encoding="utf-8")
        monkeypatch.setenv("DYNASTASIS_CONFIG", str(path))
        user_config.reload()

    yield _write
    monkeypatch.delenv("DYNASTASIS_CONFIG", raising=False)
    user_config.reload()


def test_exemple_versionne_reprend_les_defauts():
    exemple = user_config.CONFIG_PATH.with_name("user.toml.example")
    with open(exemple, "rb") as f:
        assert tomllib.load(f) == user_config.defaults()


def test_sans_fichier_les_defauts_s_appliquent(cfg, tmp_path, monkeypatch):
    monkeypatch.setenv("DYNASTASIS_CONFIG", str(tmp_path / "absent.toml"))
    user_config.reload()
    assert user_config.timezone().key == "Europe/Paris"
    assert user_config.default_mode() == "ecole"
    assert user_config.engagement_actif()


def test_fuseau_horaire_configurable(cfg):
    cfg('[general]\ntimezone = "Pacific/Auckland"\n')
    assert tz.tz().key == "Pacific/Auckland"
    assert isinstance(tz.today_local(), date)


@pytest.mark.parametrize(
    "contenu",
    [
        '[general]\ntimezone = "Mars/Olympus"\n',
        "[inconnu]\nx = 1\n",
        '[piliers]\nactifs = ["MAGIE"]\n',
        "[general\n",
        "[modes.a]\nlabel = 'A'\n",
        "[poids]\npas = -1\n",
    ],
)
def test_configuration_invalide_est_refusee(cfg, contenu):
    with pytest.raises(user_config.ConfigError):
        cfg(contenu)


def test_modes_remplacent_ceux_par_defaut(cfg):
    cfg(
        '[modes.travail]\nlabel = "Bureau"\nfocus_jour_min = 100\nfocus_semaine_min = 500\n'
        "tag_pro = true\n"
    )
    assert list(user_config.modes()) == ["travail"]
    assert user_config.mode_label("travail") == "Bureau"
    assert user_config.mode_label("ancien") == "ancien"
    assert user_config.default_mode() == "travail"


def _score(conn, week_id):
    return conn.execute("SELECT * FROM v_score_semaine WHERE id = ?", (week_id,)).fetchone()


def test_seuils_et_poids_pilotent_la_vue_de_score(cfg, db):
    cfg("[seuils.semaine]\nentrainement_min = 100\n")
    connection.init_db()
    with sqlite3.connect(db) as c:
        c.row_factory = sqlite3.Row
        c.execute("INSERT INTO semaines_audit (week_start, week_label) VALUES ('2026-03-02', 'S')")
        c.execute(
            "INSERT INTO vigueur_entries (date_entry, moving_time_min) VALUES ('2026-03-02', 150)"
        )
        assert _score(c, 1)["ok_entrainement"] == 1
    cfg("[seuils.semaine]\nentrainement_min = 200\n")
    connection.init_db()
    with sqlite3.connect(db) as c:
        c.row_factory = sqlite3.Row
        assert _score(c, 1)["ok_entrainement"] == 0


def test_desactiver_l_engagement_normalise_le_score(cfg, db):
    with sqlite3.connect(db) as c:
        c.execute(
            "INSERT INTO semaines_audit (week_start, week_label, focus_engagement_min)"
            " VALUES ('2026-03-02', 'S', 60)"
        )
        c.row_factory = sqlite3.Row
        avant = _score(c, 1)["score_semaine"]
    assert avant == 20.0  # écran (par défaut) + engagement
    cfg("[engagement]\nactif = false\n")
    connection.init_db()
    with sqlite3.connect(db) as c:
        c.row_factory = sqlite3.Row
        assert _score(c, 1)["score_semaine"] == pytest.approx(11.1, abs=0.05)  # 1 critère sur 9
    assert not user_config.critere_actif("engagement")


def test_seuil_focus_du_mode_est_celui_de_la_config(cfg, db):
    cfg('[modes.court]\nlabel = "Court"\nfocus_jour_min = 10\nfocus_semaine_min = 20\n')
    connection.init_db()
    with sqlite3.connect(db) as c:
        c.row_factory = sqlite3.Row
        c.execute(
            "INSERT INTO semaines_audit (week_start, week_label, mode_actif, deep_focus_min)"
            " VALUES ('2026-03-02', 'S', 'court', 25)"
        )
        assert _score(c, 1)["ok_deep_focus"] == 1


def test_semaine_sans_sequence_prend_le_mode_par_defaut(cfg, db):
    cfg('[modes.a]\nlabel = "A"\nfocus_jour_min = 1\nfocus_semaine_min = 1\n')
    wid = system_engine.get_or_create_week_id("2026-03-04")
    with sqlite3.connect(db) as c:
        assert c.execute(
            "SELECT mode_actif FROM semaines_audit WHERE id = ?", (wid,)
        ).fetchone() == ("a",)


def test_tags_proposes_suivent_modes_piliers_et_engagement(cfg):
    from src.core import focus_manager

    assert "FORGE_PRO" in focus_manager.tags_proposes("entreprise")
    assert "FORGE_PRO" not in focus_manager.tags_proposes("ecole")
    assert "FORGE_ENGAGEMENT" in focus_manager.tags_proposes("ecole")
    cfg('[engagement]\nactif = false\n[piliers]\nactifs = ["FORGE", "SYSTEME"]\n')
    assert focus_manager.tags_proposes("ecole") == ["FORGE_HARDSKILLS", "SYSTEME"]


# ── migration 004 sur une base d'avant la configuration ───────────────────────────────────
def _base_version_3(path):
    """Base à la version 3 : CHECK sur les modes, colonnes et tags d'origine."""
    with sqlite3.connect(path) as c:
        c.executescript(
            """
            CREATE TABLE semaines_audit (
                id INTEGER PRIMARY KEY, week_start TEXT NOT NULL UNIQUE, week_label TEXT NOT NULL,
                mode_actif TEXT CHECK (mode_actif IN ('ecole','Entreprise')),
                focus_engagement_min REAL, score_semaine REAL, is_frozen INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE sequences_mode (
                id INTEGER PRIMARY KEY, numero INTEGER NOT NULL,
                lieu TEXT NOT NULL CHECK (lieu IN ('ecole','Entreprise')),
                date_debut TEXT NOT NULL, date_fin TEXT NOT NULL
            );
            CREATE TABLE focus_sessions (
                id INTEGER PRIMARY KEY, date_session TEXT, piliers TEXT,
                semaine_id INTEGER REFERENCES semaines_audit(id)
            );
            CREATE TABLE audit_narrative (
                id INTEGER PRIMARY KEY, semaine_id INTEGER UNIQUE REFERENCES semaines_audit(id),
                jours_engagement_semaine INTEGER DEFAULT 0, forge_drill_engagement TEXT
            );
            INSERT INTO semaines_audit (week_start, week_label, mode_actif, focus_engagement_min)
                VALUES ('2026-01-05', 'S02', 'ecole', 50), ('2026-01-12', 'S03', 'Entreprise', 0);
            INSERT INTO sequences_mode (numero, lieu, date_debut, date_fin)
                VALUES (1, 'Entreprise', '2026-01-12', '2026-02-01');
            INSERT INTO focus_sessions (date_session, piliers, semaine_id)
                VALUES ('2026-01-05', 'FORGE_ENGAGEMENT,LOGOS', 1);
            INSERT INTO audit_narrative (semaine_id, jours_engagement_semaine, forge_drill_engagement)
                VALUES (1, 2, 'fait');
            PRAGMA user_version = 3;
            """
        )


def test_migration_004_convertit_modes_tags_et_colonnes(tmp_path, monkeypatch):
    path = tmp_path / "v3.db"
    monkeypatch.setattr(connection, "DB_PATH", path)
    _base_version_3(path)

    connection.init_db()

    with sqlite3.connect(path) as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == connection.latest_version()
        modes = [r[0] for r in c.execute("SELECT mode_actif FROM semaines_audit ORDER BY id")]
        assert modes == ["ecole", "entreprise"]
        assert c.execute("SELECT lieu FROM sequences_mode").fetchone() == ("entreprise",)
        assert c.execute("SELECT piliers FROM focus_sessions").fetchone() == (
            "FORGE_ENGAGEMENT,LOGOS",
        )
        assert c.execute(
            "SELECT focus_engagement_min FROM semaines_audit WHERE id = 1"
        ).fetchone() == (50,)
        assert c.execute(
            "SELECT jours_engagement_semaine, forge_drill_engagement FROM audit_narrative"
        ).fetchone() == (2, "fait")
        # le CHECK est levé : un code de mode libre est accepté
        c.execute("UPDATE semaines_audit SET mode_actif = 'libre' WHERE id = 1")
        assert c.execute("PRAGMA foreign_key_check").fetchall() == []
