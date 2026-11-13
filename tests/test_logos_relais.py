"""Bouton « Sync Écran » : relais hôte depuis le conteneur, sous-processus en local, erreurs visibles."""

import datetime
import json
import threading
import time

import pytest

from src.app.views import systeme
from src.core import sync_runner


def _chemins(monkeypatch, tmp_path):
    requete, resultat = tmp_path / "logos_request.json", tmp_path / "logos_result.json"
    monkeypatch.setattr(systeme, "_LOGOS_REQUEST", requete)
    monkeypatch.setattr(systeme, "_LOGOS_RESULT", resultat)
    return requete, resultat


def _faux_watcher(requete, resultat, ok, message):
    """Imite l'hôte : consomme la demande puis écrit le résultat avec le même nonce."""

    def boucle():
        for _ in range(100):
            if requete.exists():
                nonce = json.loads(requete.read_text())["nonce"]
                requete.unlink()
                resultat.write_text(json.dumps({"nonce": nonce, "ok": ok, "message": message}))
                return
            time.sleep(0.02)

    t = threading.Thread(target=boucle)
    t.start()
    return t


def test_relais_hote_succes(monkeypatch, tmp_path):
    requete, resultat = _chemins(monkeypatch, tmp_path)
    t = _faux_watcher(requete, resultat, True, "12 sessions")
    assert systeme._run_logos_via_hote(prise_en_charge_s=2, timeout_s=5) == (True, "12 sessions")
    t.join()


def test_relais_hote_echec_metier_remonte_le_motif(monkeypatch, tmp_path):
    requete, resultat = _chemins(monkeypatch, tmp_path)
    t = _faux_watcher(requete, resultat, False, "[ÉCHEC ADB] aucun téléphone")
    ok, msg = systeme._run_logos_via_hote(prise_en_charge_s=2, timeout_s=5)
    t.join()
    assert not ok and "ÉCHEC ADB" in msg


def test_relais_hote_ignore_un_ancien_resultat(monkeypatch, tmp_path):
    requete, resultat = _chemins(monkeypatch, tmp_path)
    resultat.write_text(json.dumps({"nonce": "ancien", "ok": True, "message": "vieux"}))
    ok, msg = systeme._run_logos_via_hote(prise_en_charge_s=0.2, timeout_s=2)
    assert not ok and "dynastasie-logos.path" in msg


def test_relais_hote_watcher_absent_nettoie_la_demande(monkeypatch, tmp_path):
    requete, _ = _chemins(monkeypatch, tmp_path)
    ok, msg = systeme._run_logos_via_hote(prise_en_charge_s=0.2, timeout_s=2)
    assert not ok and "installé" in msg
    assert not requete.exists()  # sinon le watcher la rejouerait à son installation


def test_run_logos_choisit_le_relais_en_conteneur(monkeypatch):
    monkeypatch.setattr(systeme, "_en_conteneur", lambda: True)
    monkeypatch.setattr(systeme, "_run_logos_via_hote", lambda: (True, "hote"))
    monkeypatch.setattr(systeme, "_run_logos_local", lambda: (True, "local"))
    assert systeme._run_logos() == (True, "hote")
    monkeypatch.setattr(systeme, "_en_conteneur", lambda: False)
    assert systeme._run_logos() == (True, "local")


def _src(key, configure=True):
    return sync_runner.Source(key, key, ("true",), lambda: configure, "non configuré")


def test_sync_all_en_conteneur_confie_logos_a_l_hote(monkeypatch):
    """« Tout synchroniser » en conteneur : logos exclu du run local, lancé par le relais hôte."""
    appels = {}

    def faux_run_all(**kw):
        appels.update(kw)
        return [sync_runner.Result("vigueur", sync_runner.OK)]

    monkeypatch.setattr(systeme, "_en_conteneur", lambda: True)
    monkeypatch.setattr(sync_runner, "run_all", faux_run_all)
    monkeypatch.setattr(sync_runner, "default_sources", lambda: [_src("logos"), _src("vigueur")])
    monkeypatch.setattr(systeme, "_run_logos_via_hote", lambda: (False, "téléphone introuvable"))
    results = systeme._sync_all()
    assert appels == {"skip": ["logos"]}
    logos = next(r for r in results if r.key == "logos")
    assert logos.failed and "introuvable" in logos.message
    assert [r.key for r in results] == ["vigueur", "logos"]


def test_sync_all_en_conteneur_sans_logos_configure_n_appelle_pas_l_hote(monkeypatch):
    monkeypatch.setattr(systeme, "_en_conteneur", lambda: True)
    monkeypatch.setattr(sync_runner, "run_all", lambda **kw: [])
    monkeypatch.setattr(sync_runner, "default_sources", lambda: [_src("logos", configure=False)])
    monkeypatch.setattr(systeme, "_run_logos_via_hote", lambda: pytest.fail("relais appelé"))
    assert systeme._sync_all() == []


def test_sync_all_hors_conteneur_lance_tout_en_local(monkeypatch):
    appels = []
    monkeypatch.setattr(systeme, "_en_conteneur", lambda: False)
    monkeypatch.setattr(sync_runner, "run_all", lambda **kw: appels.append(kw) or ["tout"])
    monkeypatch.setattr(systeme, "_run_logos_via_hote", lambda: pytest.fail("relais appelé"))
    assert systeme._sync_all() == ["tout"]
    assert appels == [{}]


def test_local_echec_adb_n_est_pas_un_succes(monkeypatch):
    echec = sync_runner.Result("logos", sync_runner.ERREUR, 1.0, 1, "[ÉCHEC ADB] injoignable")
    monkeypatch.setattr(sync_runner, "run_all", lambda **kw: [echec])
    ok, msg = systeme._run_logos_local()
    assert not ok and "ÉCHEC ADB" in msg


def test_local_source_non_configuree_est_un_echec_lisible(monkeypatch):
    ignoree = sync_runner.Result("logos", sync_runner.IGNOREE, message="SAMSUNG_ADB_HOST absent")
    monkeypatch.setattr(sync_runner, "run_all", lambda **kw: [ignoree])
    ok, msg = systeme._run_logos_local()
    assert not ok and "SAMSUNG_ADB_HOST" in msg


def test_logs_systeme_utilise_l_heure_locale_configuree(db, monkeypatch):
    """Le conteneur est en UTC : `datetime('now','localtime')` SQLite y donnait 1 h de retard."""
    fixe = datetime.datetime(2026, 11, 7, 19, 1, 55)
    monkeypatch.setattr(sync_runner, "now_local", lambda: fixe)
    source = sync_runner.Source("logos", "screen_time", ("x",), lambda: True, "")
    sync_runner._record(source, sync_runner.Result("logos", sync_runner.OK, 1.0, 0, "ok"))
    from src.database.connection import db_session

    with db_session() as conn:
        ts = conn.execute("SELECT timestamp FROM logs_systeme ORDER BY id DESC").fetchone()[0]
        cp = conn.execute(
            "SELECT updated_at FROM sync_checkpoints WHERE source='logos'"
        ).fetchone()[0]
    assert ts == cp == "2026-11-07 19:01:55"
