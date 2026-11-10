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
            "saine": True,
            "egales": True,
            "pair_arrete": True,
            "conflits": set(),
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

    def arreter_pair(self):
        self.appels.append("arreter_pair")
        return self.etat["pair_arrete"]

    def base_saine(self):
        return self.etat["saine"], "detail"

    def empreintes_identiques(self, attente=40):
        return self.etat["egales"]

    def conflits(self):
        # appelé avant puis après : le 2e appel renvoie les conflits « nouveaux »
        self.etat.setdefault("_n", 0)
        self.etat["_n"] += 1
        return set() if self.etat["_n"] == 1 else set(self.etat["conflits"])

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


# --- Vérifications de la base et bascule --------------------------------------------------------


def _creer_base(chemin: Path) -> None:
    import sqlite3

    conn = sqlite3.connect(chemin)
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()


def test_inspecter_base_saine(tmp_path):
    base = tmp_path / "dynastasie.db"
    _creer_base(base)
    ok, detail = handoff.inspecter_base(base)
    assert ok, detail


def test_inspecter_base_absente(tmp_path):
    ok, _ = handoff.inspecter_base(tmp_path / "dynastasie.db")
    assert not ok


def test_inspecter_base_corrompue(tmp_path):
    base = tmp_path / "dynastasie.db"
    _creer_base(base)
    octets = bytearray(base.read_bytes())
    octets[4096 : 4096 + 64] = b"\xff" * 64  # écrase le début de la page 2 (la table)
    base.write_bytes(bytes(octets))
    ok, _ = handoff.inspecter_base(base)
    assert not ok


def test_inspecter_base_refuse_un_wal_residuel(tmp_path):
    base = tmp_path / "dynastasie.db"
    _creer_base(base)
    (tmp_path / "dynastasie.db-wal").write_bytes(b"x" * 32)
    ok, detail = handoff.inspecter_base(base)
    assert not ok
    assert "WAL" in detail
    assert (tmp_path / "dynastasie.db-wal").exists()  # rien n'est supprimé


def test_inspecter_base_tolere_un_wal_vide(tmp_path):
    base = tmp_path / "dynastasie.db"
    _creer_base(base)
    (tmp_path / "dynastasie.db-wal").write_bytes(b"")
    assert handoff.inspecter_base(base)[0]


def test_lister_conflits(tmp_path):
    (tmp_path / "dynastasie.db").write_bytes(b"")
    (tmp_path / "dynastasie.sync-conflict-20261110-101159-L55IXMM.db").write_bytes(b"")
    assert handoff.lister_conflits(tmp_path) == {
        "dynastasie.sync-conflict-20261110-101159-L55IXMM.db"
    }
    assert handoff.lister_conflits(tmp_path / "absent") == set()


def test_empreinte_fichier(tmp_path):
    f = tmp_path / "a"
    f.write_bytes(b"abc")
    assert handoff.empreinte_fichier(f).startswith("ba7816bf")


@pytest.mark.parametrize(
    ("surcharge", "attendu"),
    [
        ({}, handoff.DEMARRER),
        ({"pair_joignable": False}, handoff.ABANDON),
        ({"pair_arrete": False}, handoff.ABANDON),
        ({"synchronise": False}, handoff.ABANDON),
        ({"empreintes_egales": False}, handoff.ABANDON),
        ({"base_saine": False}, handoff.ABANDON),
        ({"conflits_nouveaux": True}, handoff.ABANDON),
    ],
)
def test_decider_bascule(surcharge, attendu):
    args = (
        dict(
            pair_joignable=True,
            pair_arrete=True,
            synchronise=True,
            empreintes_egales=True,
            base_saine=True,
            conflits_nouveaux=False,
        )
        | surcharge
    )
    action, raison = handoff.decider_bascule(**args)
    assert action == attendu
    assert raison


def test_bascule_nominale_arrete_tout_verifie_puis_demarre_en_dernier():
    hote = HoteFactice()
    action, _ = handoff.executer_bascule(hote)
    assert action == handoff.DEMARRER
    assert hote.appels == [
        "arreter_local",
        "arreter_pair",
        "synchronise(scanner=True)",
        "demarrer_local",
    ]


@pytest.mark.parametrize(
    "surcharge",
    [
        {"joignable": False},
        {"pair_arrete": False},
        {"sync": False},
        {"egales": False},
        {"saine": False},
        {"conflits": {"dynastasie.sync-conflict-x.db"}},
    ],
)
def test_bascule_ne_demarre_jamais_si_une_verification_echoue(surcharge):
    hote = HoteFactice(**surcharge)
    action, raison = handoff.executer_bascule(hote)
    assert action == handoff.ABANDON
    assert raison
    assert "demarrer_local" not in hote.appels


def test_bascule_echec_arret_local_ne_touche_pas_au_pair():
    hote = HoteFactice(stop_ok=False)
    action, _ = handoff.executer_bascule(hote)
    assert action == handoff.ABANDON
    assert "arreter_pair" not in hote.appels


def test_arret_base_locale_non_saine_n_est_pas_propagee():
    hote = HoteFactice(saine=False)
    action, _ = handoff.executer_arret(hote)
    assert action == handoff.ABANDON
    assert "demarrer_pair" not in hote.appels


def test_arret_empreintes_differentes_ne_demarre_pas_le_pair():
    hote = HoteFactice(egales=False)
    action, _ = handoff.executer_arret(hote)
    assert action == handoff.ABANDON
    assert "demarrer_pair" not in hote.appels


def test_demarrage_base_non_saine_attend_confirmation():
    hote = HoteFactice(local=False, saine=False)
    action, raison = handoff.executer_demarrage(hote)
    assert action == handoff.ATTENTE
    assert "demarrer_local" not in hote.appels
    assert "refusée" in raison


def test_demarrage_empreintes_differentes_attend_confirmation():
    hote = HoteFactice(local=False, egales=False)
    action, _ = handoff.executer_demarrage(hote)
    assert action == handoff.ATTENTE
    assert "demarrer_local" not in hote.appels
