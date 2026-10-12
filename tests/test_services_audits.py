"""Services d'audit (calculs purs, enregistrements) et repositories associés."""

from __future__ import annotations

import pytest

from src.repositories.audits import COLONNES_HEBDO
from src.services import audits, npt
from src.services.semaines import get_or_create_week_id

# ── Calculs purs ────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("v", "attendu"), [(None, "—"), (0, "0h00"), (425, "7h05"), (59.6, "1h00")]
)
def test_fmt_hm(v, attendu):
    assert audits.fmt_hm(v) == attendu


def test_fmt_min():
    assert audits.fmt_min(None) == "0 min"
    assert audits.fmt_min(95.4) == "95 min"


def test_delta_ctl():
    assert audits.delta_ctl(50.5, 48.0) == 2.5
    assert audits.delta_ctl(None, 48.0) is None
    assert audits.delta_ctl(50.5, None) is None


def test_texte_top_apps():
    assert audits.texte_top_apps([]) is None
    apps = [{"app_name": "A", "fg_min": 12.34}, {"app_name": "B", "fg_min": 3.0}]
    assert audits.texte_top_apps(apps) == "A (12.3min), B (3.0min)"


def test_texte_volume():
    assert audits.texte_volume(None) == "—"
    assert audits.texte_volume({"moving_time_min": 0, "distance_km": 0}) == "—"
    assert (
        audits.texte_volume({"moving_time_min": 300, "distance_km": 50}) == "50.0 km · 6.00 min/km"
    )


def test_texte_focus_total():
    assert audits.texte_focus_total(0, {}, []) == "Aucune session cette semaine"
    texte = audits.texte_focus_total(
        120, {"FORGE": 90, "LOGOS": 30, "VIGUEUR": 0}, ["FORGE", "LOGOS", "VIGUEUR"]
    )
    assert texte == "120 min (2.0 h) — Forge 75% / Logos 25%"


def test_compter_jalons():
    taches = [
        {"statut": "fait", "date_echeance": "2020-01-01"},
        {"statut": "annule", "date_echeance": "2020-01-01"},
        {"statut": "a_faire", "date_echeance": "2026-01-01"},
        {"statut": "a_faire", "date_echeance": "2026-12-01"},
        {"statut": "a_faire", "date_echeance": None},
    ]
    assert audits.compter_jalons(taches, "2026-06-01") == (1, 3)


def test_score_module_annuel():
    module = {"indicators": [("a", "", ""), ("b", "", "")]}
    assert audits.score_module_annuel({"a": 3, "b": 4}, module) == 7
    assert audits.score_module_annuel({"a": 3}, module) is None


def _valeurs(**surcharge):
    base = dict.fromkeys(COLONNES_HEBDO, "")
    base.update(
        jauge_energie=6,
        alerte_rouge=False,
        forge_jours_engagement_mois=0,
        jours_engagement_semaine=0,
        forge_pro_dependance_tiers=False,
    )
    base.update(surcharge)
    return base


def test_normaliser_audit_hebdo():
    out = audits.normaliser_audit_hebdo(_valeurs(alerte_rouge=True, plan_priorite_unique="x"))
    assert out["alerte_rouge"] == 1 and out["forge_pro_dependance_tiers"] == 0
    assert out["jauge_energie"] == 6
    assert out["plan_priorite_unique"] == "x" and out["correction_immediate"] is None


# ── Enregistrements ─────────────────────────────────────────────────────────────────────────────


def test_audit_hebdo_creation_puis_mise_a_jour(db):
    wid = get_or_create_week_id("2026-03-04")
    assert audits.charger_audit(wid) == {"_source": "empty"}

    audits.sauvegarder_audit_hebdo(wid, _valeurs(plan_priorite_unique="un"), "Isolé")
    a = audits.charger_audit(wid)
    assert a["_source"] == "db" and a["plan_priorite_unique"] == "un"
    assert audits.meta_semaine(wid)["social"] == "Isolé"

    audits.sauvegarder_audit_hebdo(
        wid, _valeurs(plan_priorite_unique="deux", jauge_energie=9), "Connecté/Ressourcé"
    )
    a = audits.charger_audit(wid)
    assert (a["plan_priorite_unique"], a["jauge_energie"]) == ("deux", 9)
    assert audits.meta_semaine(wid)["social"] == "Connecté/Ressourcé"


def test_audit_trimestriel_et_annuel(db):
    assert audits.trimestriel("Hiver", 2026) == {}
    colonnes = [
        c
        for c in _colonnes("audit_trimestriel")
        if c not in ("id", "saison", "annee", "created_at", "updated_at")
    ]
    champ = colonnes[0]
    audits.sauvegarder_trimestriel("Hiver", 2026, {champ: "a"})
    audits.sauvegarder_trimestriel("Hiver", 2026, {champ: "b"})
    assert audits.trimestriel("Hiver", 2026)[champ] == "b"
    assert [(h["saison"], h["annee"]) for h in audits.historique_trimestriel()] == [("Hiver", 2026)]

    assert audits.annuel(2026) == {}
    audits.sauvegarder_annuel(2026, {"date_audit": "2026-12-31"})
    audits.sauvegarder_annuel(2026, {"date_audit": "2027-01-02"})
    assert audits.annuel(2026)["date_audit"] == "2027-01-02"
    assert [a["annee"] for a in audits.historique_annuel()] == [2026]


def _colonnes(table):
    import sqlite3

    from src.database import connection

    with sqlite3.connect(connection.DB_PATH) as c:
        return [r[1] for r in c.execute(f"PRAGMA table_info({table})")]


def test_synchroniser_metriques_sur_base_de_demo(demo_db):
    from datetime import date

    wid = get_or_create_week_id(date.today().isoformat())
    res = audits.synchroniser_metriques(wid)
    assert set(res) == {"score", "semaine"}
    assert res["semaine"]["score_semaine"] is not None
    lecture = audits.lecture_audit(
        wid, res["score"].get("week_start") or date.today().isoformat(), None
    )
    assert lecture["system_ecran_txt"].endswith("min") or lecture["system_ecran_txt"] == "—"


def test_notes_pour_trop_tard(db):
    assert npt.tables_pretes()
    pid = npt.ajouter_personne("Alex", "Test", ["Amis", "Famille"], "En vie et proche", 5)
    npt.ajouter_note(pid, "2026-03-01", "bonjour")
    npt.ajouter_note(pid, "2026-03-02", "salut")
    assert [p["id"] for p in npt.personnes()] == [pid]
    assert [n["contenu"] for n in npt.notes(pid)] == ["salut", "bonjour"]
    assert npt.personnes()[0]["liens"] == "Amis,Famille"
