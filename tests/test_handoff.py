"""Passage de relais entre machines : décisions, scénarios (hôte factice) et statut."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "handoff", Path(__file__).resolve().parents[1] / "scripts" / "handoff.py"
)
handoff = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(handoff)


@pytest.mark.parametrize(
    ("local", "joignable", "pair", "sync", "attendu"),
    [
        (False, False, False, False, handoff.ATTENTE),  # démarrage seul : confirmation requise
        (True, False, False, False, handoff.ATTENTE),  # relancé par Docker, pair injoignable
        (False, True, True, True, handoff.RIEN),  # les deux allumés : gestion manuelle
        (True, True, True, True, handoff.ARRETER_LOCAL),  # double écrivain évité
        (False, True, False, False, handoff.ATTENTE),  # synchro incomplète
        (False, True, False, True, handoff.DEMARRER),  # pair arrêté, base à jour
    ],
)
def test_decider_demarrage(local, joignable, pair, sync, attendu):
    action, raison = handoff.decider_demarrage(
        local_actif=local, pair_joignable=joignable, pair_actif=pair, synchronise=sync
    )
    assert action == attendu
    assert raison


@pytest.mark.parametrize(
    ("local", "joignable", "pair", "sync", "attendu"),
    [
        (False, True, False, True, handoff.RIEN),  # rien à passer
        (True, False, False, False, handoff.ABANDON),  # pair éteint
        (True, True, True, True, handoff.RIEN),  # pair déjà actif
        (True, True, False, False, handoff.ABANDON),  # base pas encore reçue
        (True, True, False, True, handoff.DEMARRER_PAIR),
    ],
)
def test_decider_arret(local, joignable, pair, sync, attendu):
    action, _ = handoff.decider_arret(
        local_actif=local, pair_joignable=joignable, pair_actif=pair, synchronise=sync
    )
    assert action == attendu


def test_arret_systeme():
    assert handoff.arret_systeme("123 poweroff.target start waiting")
    assert handoff.arret_systeme("9 reboot.target start waiting")
    assert not handoff.arret_systeme("")
    assert not handoff.arret_systeme("5 dynastasie-handoff.service stop running")


class HoteFactice:
    def __init__(self, **etat):
        self.etat = {
            "arret_systeme": True,
            "local": True,
            "stop_ok": True,
            "joignable": True,
            "pair": False,
            "sync": True,
            "st_pret": True,
            "start_ok": True,
        } | etat
        self.appels: list[str] = []

    def arret_systeme(self):
        return self.etat["arret_systeme"]

    def local_actif(self):
        return self.etat["local"]

    def arreter_local(self):
        self.appels.append("arreter_local")
        return self.etat["stop_ok"]

    def demarrer_local(self):
        self.appels.append("demarrer_local")
        return self.etat["start_ok"]

    def pair_joignable(self, attente=0):
        return self.etat["joignable"]

    def pair_actif(self):
        return self.etat["pair"]

    def demarrer_pair(self):
        self.appels.append("demarrer_pair")
        return self.etat["start_ok"]

    def syncthing_pret(self):
        return self.etat["st_pret"]

    def synchronise(self, *, scanner=False):
        self.appels.append(f"synchronise(scanner={scanner})")
        return self.etat["sync"]


def test_arret_nominal_stoppe_puis_demarre_le_pair_apres_synchro():
    hote = HoteFactice()
    action, _ = handoff.executer_arret(hote)
    assert action == handoff.DEMARRER_PAIR
    assert hote.appels == ["arreter_local", "synchronise(scanner=True)", "demarrer_pair"]


def test_arret_manuel_du_service_ne_fait_rien():
    hote = HoteFactice(arret_systeme=False)
    action, _ = handoff.executer_arret(hote)
    assert action == handoff.RIEN
    assert hote.appels == []


def test_arret_pair_injoignable_ne_demarre_rien():
    hote = HoteFactice(joignable=False)
    action, _ = handoff.executer_arret(hote)
    assert action == handoff.ABANDON
    assert hote.appels == ["arreter_local"]


def test_arret_synchro_incomplete_ne_demarre_pas_le_pair():
    hote = HoteFactice(sync=False)
    action, _ = handoff.executer_arret(hote)
    assert action == handoff.ABANDON
    assert "demarrer_pair" not in hote.appels


def test_arret_conteneur_local_deja_arrete():
    hote = HoteFactice(local=False)
    action, _ = handoff.executer_arret(hote)
    assert action == handoff.RIEN
    assert hote.appels == []


def test_arret_echec_de_arret_local_annule_le_relais():
    hote = HoteFactice(stop_ok=False)
    action, _ = handoff.executer_arret(hote)
    assert action == handoff.ABANDON
    assert "demarrer_pair" not in hote.appels


def test_demarrage_pair_arrete_et_base_a_jour_demarre_en_local():
    hote = HoteFactice(local=False)
    action, _ = handoff.executer_demarrage(hote)
    assert action == handoff.DEMARRER
    assert hote.appels == ["synchronise(scanner=False)", "demarrer_local"]


def test_demarrage_pair_injoignable_attend_confirmation_et_stoppe_docker_autostart():
    hote = HoteFactice(joignable=False, local=True)
    action, _ = handoff.executer_demarrage(hote)
    assert action == handoff.ATTENTE
    assert hote.appels == ["arreter_local"]


def test_demarrage_pair_actif_laisse_la_gestion_manuelle():
    hote = HoteFactice(local=False, pair=True)
    action, _ = handoff.executer_demarrage(hote)
    assert action == handoff.RIEN
    assert hote.appels == []


def test_demarrage_syncthing_indisponible_attend_confirmation():
    hote = HoteFactice(local=False, st_pret=False)
    action, _ = handoff.executer_demarrage(hote)
    assert action == handoff.ATTENTE
    assert "demarrer_local" not in hote.appels


def test_statut_aller_retour(tmp_path):
    chemin = tmp_path / "etat" / "handoff.json"
    assert handoff.lire_statut(chemin) == {}
    handoff.ecrire_statut(handoff.ATTENTE, "pair injoignable", chemin)
    statut = handoff.lire_statut(chemin)
    assert statut["etat"] == handoff.ATTENTE
    assert statut["message"] == "pair injoignable"


def test_notifier_signale_l_attente_puis_s_efface_quand_le_conteneur_tourne(tmp_path, monkeypatch):
    monkeypatch.setattr(handoff, "STATUT", tmp_path / "handoff.json")
    envois: list[list[str]] = []
    monkeypatch.setattr(handoff, "_run", lambda argv, timeout: envois.append(argv))
    handoff.ecrire_statut(handoff.ATTENTE, "pair injoignable")

    assert handoff.notifier(HoteFactice(local=False)) == 0
    assert envois and envois[0][0] == "notify-send"

    envois.clear()
    assert handoff.notifier(HoteFactice(local=True)) == 0  # démarré entre-temps via l'icône
    assert not envois
    assert handoff.lire_statut()["etat"] == handoff.RIEN
    assert handoff.notifier(HoteFactice(local=False)) == 0  # plus rien à signaler
    assert not envois
