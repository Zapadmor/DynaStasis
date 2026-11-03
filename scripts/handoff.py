#!/usr/bin/env python3
"""Passage de relais du conteneur DynaStasis entre deux machines, à l'extinction et au démarrage.

La base SQLite (db/, synchronisée par Syncthing) n'a qu'un seul écrivain valable à la fois.
Avec `restart: unless-stopped`, Docker relance seul au boot un conteneur qu'il a lui-même arrêté
à l'extinction : sans arrêt explicite, les deux machines peuvent écrire en même temps.

Modes (lancés par le service systemd dynastasie-handoff.service, sur l'hôte) :

  stop    Extinction. Arrête le conteneur local (checkpoint WAL), force un scan Syncthing, attend
          que le pair ait reçu la base, puis démarre le conteneur du pair par SSH. Si le pair est
          injoignable ou la synchronisation incomplète, rien n'est démarré : un conteneur éteint
          vaut mieux qu'un démarrage sur une base périmée.
  start   Démarrage. Démarre le conteneur local seulement si le pair est joignable, que son
          conteneur est arrêté et que la synchronisation est terminée. Pair injoignable (ou base
          pas à jour) : rien n'est démarré, l'état « attente_confirmation » est enregistré et
          `notify` le signale à l'ouverture de session. Pair joignable avec son conteneur en
          marche : on ne touche à rien (gestion manuelle par les icônes du bureau).
  notify  À l'ouverture de session : affiche une notification si le démarrage attend une
          confirmation et que le conteneur local est toujours arrêté.

Limite connue : Syncthing ne copie rien tant que les deux machines ne sont pas allumées en même
temps. Une machine qui s'éteint pendant que l'autre est éteinte garde ses dernières écritures
chez elle ; c'est pourquoi un démarrage seul demande une confirmation (icône du bureau).

Variables d'environnement : DYNASTASIS_PEER_SSH (obligatoire, cible SSH du pair),
DYNASTASIS_CONTAINER (défaut dynastasie-streamlit), DYNASTASIS_SYNCTHING_FOLDER (défaut
yc55x-xzatk), DYNASTASIS_SYNCTHING_CONFIG (défaut ~/.local/state/syncthing/config.xml).
"""

from __future__ import annotations

import datetime
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

CONTENEUR = os.environ.get("DYNASTASIS_CONTAINER", "dynastasie-streamlit")
PEER = os.environ.get("DYNASTASIS_PEER_SSH", "")
DOSSIER_ST = os.environ.get("DYNASTASIS_SYNCTHING_FOLDER", "yc55x-xzatk")
STATUT = Path.home() / ".local" / "state" / "dynastasie" / "handoff.json"

# Actions décidées (voir decider_demarrage / decider_arret)
DEMARRER = "demarrer"
ARRETER_LOCAL = "arreter_local"
ATTENTE = "attente_confirmation"
RIEN = "rien"
DEMARRER_PAIR = "demarrer_pair"
ABANDON = "abandon"

_JOBS_ARRET = re.compile(r"\b(poweroff|reboot|halt|kexec|shutdown)\.target\b")


# --- Décisions pures (testées sans réseau ni Docker) ---------------------------------------------


def decider_demarrage(
    *, local_actif: bool, pair_joignable: bool, pair_actif: bool, synchronise: bool
) -> tuple[str, str]:
    """Décide quoi faire au démarrage de cette machine ; renvoie (action, raison)."""
    if not pair_joignable:
        return ATTENTE, "L'autre PC est injoignable (éteint ou VPN coupé) : base peut-être périmée."
    if pair_actif:
        if local_actif:
            return ARRETER_LOCAL, "Le conteneur de l'autre PC tourne : double écrivain évité."
        return RIEN, "Le conteneur de l'autre PC tourne : gestion manuelle."
    if not synchronise:
        return ATTENTE, "La synchronisation Syncthing avec l'autre PC n'est pas terminée."
    return DEMARRER, "L'autre PC est arrêté et la base est à jour."


def decider_arret(
    *, local_actif: bool, pair_joignable: bool, pair_actif: bool, synchronise: bool
) -> tuple[str, str]:
    """Décide quoi faire à l'extinction (après l'arrêt du conteneur local) ; (action, raison)."""
    if not local_actif:
        return RIEN, "Le conteneur local était déjà arrêté : rien à passer."
    if not pair_joignable:
        return ABANDON, "L'autre PC est injoignable : conteneur non démarré là-bas."
    if pair_actif:
        return RIEN, "Le conteneur de l'autre PC tourne déjà."
    if not synchronise:
        return ABANDON, "Synchronisation incomplète : démarrage évité sur une base périmée."
    return DEMARRER_PAIR, "Base synchronisée : démarrage du conteneur sur l'autre PC."


def arret_systeme(jobs: str) -> bool:
    """Vrai si la liste `systemctl list-jobs` contient un job d'extinction/redémarrage."""
    return bool(_JOBS_ARRET.search(jobs))


# --- Statut (lu par `notify` à l'ouverture de session) --------------------------------------------


def ecrire_statut(etat: str, message: str, chemin: Path | None = None) -> None:
    chemin = chemin or STATUT
    chemin.parent.mkdir(parents=True, exist_ok=True)
    charge = {
        "etat": etat,
        "message": message,
        "hote": socket.gethostname(),
        "date": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    tmp = chemin.with_suffix(".tmp")
    tmp.write_text(json.dumps(charge, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, chemin)


def lire_statut(chemin: Path | None = None) -> dict:
    chemin = chemin or STATUT
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# --- Entrées/sorties réelles ----------------------------------------------------------------------


def _log(msg: str) -> None:
    print(f"[handoff] {msg}", flush=True)


def _run(argv: list[str], timeout: float) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(argv, 124, "", "délai dépassé")
    except FileNotFoundError as exc:
        return subprocess.CompletedProcess(argv, 127, "", str(exc))


class Syncthing:
    """Client minimal de l'API REST locale de Syncthing."""

    def __init__(self, dossier: str = DOSSIER_ST):
        self.dossier = dossier
        cfg = Path(
            os.environ.get(
                "DYNASTASIS_SYNCTHING_CONFIG",
                str(Path.home() / ".local" / "state" / "syncthing" / "config.xml"),
            )
        )
        if not cfg.exists():
            alt = Path.home() / ".config" / "syncthing" / "config.xml"
            cfg = alt if alt.exists() else cfg
        self.base = ""
        self.cle = ""
        try:
            gui = ET.parse(cfg).getroot().find("gui")
            self.base = "http://" + gui.findtext("address", "127.0.0.1:8384")
            self.cle = gui.findtext("apikey", "")
        except (OSError, ET.ParseError, AttributeError):
            pass

    def _appel(self, chemin: str, methode: str = "GET", timeout: float = 20):
        req = urllib.request.Request(
            f"{self.base}/rest/{chemin}", method=methode, headers={"X-API-Key": self.cle}
        )
        with urllib.request.urlopen(req, timeout=timeout) as rep:
            corps = rep.read()
        return json.loads(corps) if corps else {}

    def pret(self, attente: float = 30) -> bool:
        fin = time.monotonic() + attente
        while True:
            try:
                self._appel("system/status", timeout=5)
                return True
            except (OSError, ValueError):
                if time.monotonic() >= fin:
                    return False
                time.sleep(2)

    def synchronise(self, attente: float = 45, scanner: bool = False) -> bool:
        """Vrai si le(s) pair(s) du dossier ont tout reçu et que rien n'est en attente ici."""
        q = urllib.parse.quote(self.dossier)
        try:
            moi = self._appel("system/status")["myID"]
            pairs = [
                d["deviceID"]
                for d in self._appel(f"config/folders/{q}")["devices"]
                if d["deviceID"] != moi
            ]
            if not pairs:
                return False
            if scanner:
                self._appel(f"db/scan?folder={q}", methode="POST", timeout=60)
                time.sleep(2)  # laisse l'index partir vers le pair avant de lire sa complétion
        except (OSError, ValueError, KeyError):
            return False
        fin = time.monotonic() + attente
        consecutifs = 0
        while time.monotonic() < fin:
            try:
                etat = self._appel(f"db/status?folder={q}")
                connexions = self._appel("system/connections")["connections"]
                ok = etat.get("state") == "idle" and etat.get("needTotalItems", 0) == 0
                for p in pairs:
                    if not connexions.get(p, {}).get("connected"):
                        ok = False
                        continue
                    c = self._appel(f"db/completion?folder={q}&device={p}")
                    ok = ok and c.get("completion") == 100 and c.get("needItems", 0) == 0
            except (OSError, ValueError, KeyError):
                ok = False
            consecutifs = consecutifs + 1 if ok else 0
            if consecutifs >= 2:  # deux relevés d'affilée : évite un 100 % lu avant le scan
                return True
            time.sleep(2)
        return False


class Hote:
    """Actions réelles : Docker local, SSH vers le pair, Syncthing, systemd."""

    def __init__(self):
        self.syncthing = Syncthing()

    def local_actif(self) -> bool:
        r = _run(["docker", "inspect", "-f", "{{.State.Running}}", CONTENEUR], 15)
        return r.returncode == 0 and r.stdout.strip() == "true"

    def arreter_local(self) -> bool:
        return _run(["docker", "stop", "-t", "30", CONTENEUR], 60).returncode == 0

    def demarrer_local(self) -> bool:
        return _run(["docker", "start", CONTENEUR], 60).returncode == 0

    def _ssh(self, commande: str, timeout: float = 15) -> subprocess.CompletedProcess:
        return _run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", PEER, commande], timeout
        )

    def pair_joignable(self, attente: float = 0) -> bool:
        fin = time.monotonic() + attente
        while True:
            if self._ssh("true").returncode == 0:
                return True
            if time.monotonic() >= fin:
                return False
            time.sleep(3)

    def pair_actif(self) -> bool:
        r = self._ssh(f"docker inspect -f '{{{{.State.Running}}}}' '{CONTENEUR}'")
        return r.returncode == 0 and r.stdout.strip() == "true"

    def demarrer_pair(self) -> bool:
        return self._ssh(f"docker start '{CONTENEUR}'", timeout=60).returncode == 0

    def synchronise(self, *, scanner: bool = False) -> bool:
        return self.syncthing.synchronise(scanner=scanner)

    def syncthing_pret(self) -> bool:
        return self.syncthing.pret()

    def arret_systeme(self) -> bool:
        r = _run(["systemctl", "list-jobs", "--no-legend"], 10)
        return arret_systeme(r.stdout)


# --- Scénarios ------------------------------------------------------------------------------------


def executer_arret(hote, *, forcer: bool = False) -> tuple[str, str]:
    """Extinction : arrête le conteneur local puis, si c'est sûr, démarre celui du pair."""
    if not forcer and not hote.arret_systeme():
        return RIEN, "Arrêt manuel du service (pas une extinction) : aucun passage de relais."
    local_actif = hote.local_actif()
    if not local_actif:
        return RIEN, "Le conteneur local était déjà arrêté : rien à passer."
    if not hote.arreter_local():
        return ABANDON, "Échec de l'arrêt du conteneur local : relais annulé."
    joignable = hote.pair_joignable()
    pair_actif = hote.pair_actif() if joignable else False
    synchronise = (
        hote.synchronise(scanner=True)
        if joignable and not pair_actif and hote.syncthing_pret()
        else False
    )
    action, raison = decider_arret(
        local_actif=local_actif,
        pair_joignable=joignable,
        pair_actif=pair_actif,
        synchronise=synchronise,
    )
    if action == DEMARRER_PAIR and not hote.demarrer_pair():
        return ABANDON, "Échec du démarrage du conteneur sur l'autre PC."
    return action, raison


def executer_demarrage(hote) -> tuple[str, str]:
    """Démarrage : lance le conteneur local si l'autre PC est arrêté et la base à jour."""
    st_pret = hote.syncthing_pret()
    joignable = hote.pair_joignable(attente=40)
    local_actif = hote.local_actif()
    pair_actif = hote.pair_actif() if joignable else False
    synchronise = joignable and not pair_actif and st_pret and hote.synchronise()
    action, raison = decider_demarrage(
        local_actif=local_actif,
        pair_joignable=joignable,
        pair_actif=pair_actif,
        synchronise=synchronise,
    )
    if action == DEMARRER and not local_actif and not hote.demarrer_local():
        return ATTENTE, "Échec du démarrage du conteneur local."
    if action in (ARRETER_LOCAL, ATTENTE) and local_actif:
        hote.arreter_local()  # conteneur relancé seul par Docker : on évite un écrivain non validé
    return action, raison


def notifier(hote) -> int:
    statut = lire_statut()
    if statut.get("etat") != ATTENTE:
        return 0
    if hote.local_actif():  # confirmé entre-temps (icône du bureau) : on efface
        ecrire_statut(RIEN, "Conteneur local démarré.")
        return 0
    msg = (
        f"{statut.get('message', '')}\nLance « DynaStasis - Basculer ici » sur le bureau "
        "pour le démarrer sur ce PC."
    )
    _log(msg)
    _run(["notify-send", "-i", "view-refresh", "DynaStasis est arrêté", msg], 10)
    return 0


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else ""
    if mode not in ("start", "stop", "notify"):
        print("usage : handoff.py start|stop|notify [--forcer]", file=sys.stderr)
        return 2
    hote = Hote()
    if mode == "notify":
        return notifier(hote)
    if not PEER:
        _log("DYNASTASIS_PEER_SSH non défini : aucune action.")
        return 0
    if mode == "stop":
        action, raison = executer_arret(hote, forcer="--forcer" in argv)
    else:
        action, raison = executer_demarrage(hote)
    _log(f"{mode} -> {action} : {raison}")
    ecrire_statut(ATTENTE if action == ATTENTE else action, raison)
    return 0  # jamais d'échec d'unité : l'état détaillé est dans le journal et handoff.json


if __name__ == "__main__":
    sys.exit(main(sys.argv))
