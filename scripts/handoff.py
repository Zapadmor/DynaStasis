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
  bascule Reprise manuelle (bouton « Basculer ici », scripts/stop_peer.sh) : arrête les conteneurs
          locaux, arrête ceux du pair, force le scan Syncthing, attend la fin de la synchro,
          vérifie que la base est identique des deux côtés (sha256) et saine (integrity_check),
          sans journal WAL résiduel ni nouveau fichier `sync-conflict`, puis seulement démarre
          les conteneurs locaux. Code de sortie 1 si l'une des vérifications échoue.
  notify  À l'ouverture de session : affiche une notification si le démarrage attend une
          confirmation et que le conteneur local est toujours arrêté.

Limite connue : Syncthing ne copie rien tant que les deux machines ne sont pas allumées en même
temps. Une machine qui s'éteint pendant que l'autre est éteinte garde ses dernières écritures
chez elle ; c'est pourquoi un démarrage seul demande une confirmation (icône du bureau).

Tous les conteneurs qui écrivent dans la base sont gérés ensemble (Streamlit ET API).
Les vérifications de base (WAL résiduel, integrity_check, empreinte identique des deux côtés)
protègent contre le cas observé : un fichier remplacé par Syncthing sous un conteneur ouvert, ou
posé à côté d'un -wal périmé (les -wal/-shm ne sont pas synchronisés).

Variables d'environnement : DYNASTASIS_PEER_SSH (obligatoire, cible SSH du pair),
DYNASTASIS_CONTAINERS (défaut « dynastasie-streamlit,dynastasie-api », ordre de démarrage),
DYNASTASIS_PEER_DB_DIR (dossier db/ sur le pair, défaut : même chemin relatif au HOME), DYNASTASIS_SYNCTHING_FOLDER (défaut
yc55x-xzatk), DYNASTASIS_SYNCTHING_CONFIG (défaut ~/.local/state/syncthing/config.xml).
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import shlex
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

CONTENEURS = [
    c.strip()
    for c in os.environ.get(
        "DYNASTASIS_CONTAINERS",
        os.environ.get("DYNASTASIS_CONTAINER", "dynastasie-streamlit,dynastasie-api"),
    ).split(",")
    if c.strip()
]
CONTENEUR = CONTENEURS[0]  # compat : le premier (Streamlit) est celui qui migre la base
DB_DIR = Path(__file__).resolve().parents[1] / "db"
DB_NOM = "dynastasie.db"
PEER = os.environ.get("DYNASTASIS_PEER_SSH", "")
DOSSIER_ST = os.environ.get("DYNASTASIS_SYNCTHING_FOLDER", "yc55x-xzatk")
try:
    _DB_REL = DB_DIR.relative_to(Path.home()).as_posix()
except ValueError:
    _DB_REL = ""
PEER_DB_DIR = os.environ.get("DYNASTASIS_PEER_DB_DIR", _DB_REL)
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
    *,
    local_actif: bool,
    pair_joignable: bool,
    pair_actif: bool,
    synchronise: bool,
    empreintes_egales: bool = True,
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
    if not empreintes_egales:
        return ATTENTE, "La base locale diffère de celle de l'autre PC malgré la synchro."
    return DEMARRER, "L'autre PC est arrêté et la base est à jour."


def decider_arret(
    *,
    local_actif: bool,
    pair_joignable: bool,
    pair_actif: bool,
    synchronise: bool,
    base_saine: bool = True,
    empreintes_egales: bool = True,
) -> tuple[str, str]:
    """Décide quoi faire à l'extinction (après l'arrêt du conteneur local) ; (action, raison)."""
    if not local_actif:
        return RIEN, "Le conteneur local était déjà arrêté : rien à passer."
    if not pair_joignable:
        return ABANDON, "L'autre PC est injoignable : conteneur non démarré là-bas."
    if pair_actif:
        return RIEN, "Le conteneur de l'autre PC tourne déjà."
    if not base_saine:
        return ABANDON, "Base locale non saine : elle n'est pas propagée à l'autre PC."
    if not synchronise:
        return ABANDON, "Synchronisation incomplète : démarrage évité sur une base périmée."
    if not empreintes_egales:
        return ABANDON, "La base de l'autre PC diffère de la locale : démarrage évité."
    return DEMARRER_PAIR, "Base synchronisée : démarrage du conteneur sur l'autre PC."


def decider_bascule(
    *,
    pair_joignable: bool,
    pair_arrete: bool,
    synchronise: bool,
    empreintes_egales: bool,
    base_saine: bool,
    conflits_nouveaux: bool,
) -> tuple[str, str]:
    """Décide, une fois les conteneurs arrêtés, si l'on peut démarrer ici ; (action, raison)."""
    if not pair_joignable:
        return ABANDON, "L'autre PC est injoignable : rien n'a été arrêté ni démarré."
    if not pair_arrete:
        return ABANDON, "Le conteneur de l'autre PC tourne encore : double écrivain évité."
    if not synchronise:
        return ABANDON, "Synchronisation Syncthing incomplète : conteneur local non relancé."
    if conflits_nouveaux:
        return ABANDON, "Nouveau fichier sync-conflict dans db/ : à examiner avant de relancer."
    if not empreintes_egales:
        return ABANDON, "La base diffère entre les deux PC (sha256) : conteneur local non relancé."
    if not base_saine:
        return ABANDON, "Base locale non saine : conteneur local non relancé."
    return DEMARRER, "Base identique sur les deux PC et saine : conteneurs locaux relancés."


# --- Vérifications de la base (pures côté fichier, testables avec tmp_path) --------------------


def inspecter_base(chemin: Path) -> tuple[bool, str]:
    """Vérifie une base fermée : pas de WAL résiduel, puis PRAGMA integrity_check (lecture seule).

    Le WAL est testé AVANT l'ouverture : un -wal non vide à côté d'un fichier remplacé par
    Syncthing serait rejoué sur la mauvaise base. Rien n'est supprimé ici : on refuse seulement.
    """
    if not chemin.is_file():
        return False, f"Base introuvable : {chemin}"
    wal = chemin.with_name(chemin.name + "-wal")
    if wal.exists() and wal.stat().st_size > 0:
        return False, f"Journal WAL résiduel non vide ({wal.name}) : base possiblement incohérente."
    try:
        # immutable=1 : le WAL est déjà écarté ci-dessus, et l'ouverture ne crée ni -wal ni -shm
        # dans db/ (que Syncthing surveille).
        conn = sqlite3.connect(f"file:{chemin}?mode=ro&immutable=1", uri=True, timeout=5)
        try:
            verdict = conn.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return False, f"Base illisible : {exc}"
    return (verdict == "ok"), (
        "integrity_check ok" if verdict == "ok" else f"integrity_check : {verdict}"
    )


def empreinte_fichier(chemin: Path) -> str:
    h = hashlib.sha256()
    with chemin.open("rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def lister_conflits(dossier: Path) -> set[str]:
    """Noms des copies `sync-conflict` présentes dans db/ (produites par Syncthing)."""
    return {p.name for p in dossier.glob("*.sync-conflict-*")} if dossier.is_dir() else set()


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

    def _actif_local(self, nom: str) -> bool:
        r = _run(["docker", "inspect", "-f", "{{.State.Running}}", nom], 15)
        return r.returncode == 0 and r.stdout.strip() == "true"

    def local_actif(self) -> bool:
        return any(self._actif_local(c) for c in CONTENEURS)

    def arreter_local(self) -> bool:
        """Arrête tous les conteneurs locaux qui tournent (API d'abord, Streamlit ensuite)."""
        ok = True
        for nom in reversed(CONTENEURS):
            if self._actif_local(nom):
                ok = _run(["docker", "stop", "-t", "30", nom], 60).returncode == 0 and ok
        return ok and not self.local_actif()

    def demarrer_local(self) -> bool:
        """Démarre Streamlit (qui migre la base) puis l'API ; un conteneur absent est ignoré."""
        ok = False
        for i, nom in enumerate(CONTENEURS):
            r = _run(["docker", "start", nom], 60)
            if i == 0:
                ok = r.returncode == 0
        return ok

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
        cmd = "; ".join(
            f"docker inspect -f '{{{{.State.Running}}}}' {shlex.quote(c)} 2>/dev/null || echo false"
            for c in CONTENEURS
        )
        r = self._ssh(cmd)
        return r.returncode == 0 and "true" in r.stdout.split()

    def arreter_pair(self) -> bool:
        """Arrête les conteneurs du pair ; le succès se juge par pair_actif(), pas par le code."""
        cmd = "; ".join(
            f"docker stop -t 30 {shlex.quote(c)} 2>/dev/null" for c in reversed(CONTENEURS)
        )
        self._ssh(cmd + "; true", timeout=90)
        return not self.pair_actif()

    def demarrer_pair(self) -> bool:
        premier, *autres = [shlex.quote(c) for c in CONTENEURS]
        # Le code de sortie ne compte que pour Streamlit (l'API peut ne pas exister sur ce PC)
        etapes = [f"docker start {premier} || exit 1"]
        etapes += [f"docker start {c} 2>/dev/null" for c in autres]
        cmd = "; ".join([*etapes, "true"])
        return self._ssh(cmd, timeout=60).returncode == 0

    def base_saine(self) -> tuple[bool, str]:
        return inspecter_base(DB_DIR / DB_NOM)

    def conflits(self) -> set[str]:
        return lister_conflits(DB_DIR)

    def empreinte_pair(self) -> tuple[str, int] | None:
        """(sha256 de la base, taille du -wal) sur le pair, ou None si illisible."""
        if not PEER_DB_DIR:
            return None
        d = f'"$HOME"/{shlex.quote(PEER_DB_DIR)}'
        r = self._ssh(
            f"cd {d} && sha256sum {DB_NOM} && (stat -c %s {DB_NOM}-wal 2>/dev/null || echo 0)",
            timeout=60,
        )
        lignes = r.stdout.split()
        if r.returncode != 0 or len(lignes) < 3:
            return None
        try:
            return lignes[0], int(lignes[2])
        except ValueError:
            return None

    def empreintes_identiques(self, attente: float = 40) -> bool:
        """Base identique (sha256) des deux côtés et aucun WAL en attente ; réessaie le temps
        que l'index du pair parte (son fsWatcher attend ~10 s après l'arrêt du conteneur)."""
        fin = time.monotonic() + attente
        while True:
            try:
                locale = empreinte_fichier(DB_DIR / DB_NOM)
            except OSError:
                return False
            distante = self.empreinte_pair()
            if distante and distante[0] == locale and distante[1] == 0:
                return True
            if time.monotonic() >= fin:
                return False
            time.sleep(4)

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
    base_saine, detail = hote.base_saine()
    if not base_saine:
        return ABANDON, f"Base locale non saine, non propagée au pair : {detail}"
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
        base_saine=base_saine,
        empreintes_egales=bool(synchronise) and hote.empreintes_identiques(),
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
        empreintes_egales=(not synchronise) or hote.empreintes_identiques(),
    )
    if action == DEMARRER and not local_actif:
        saine, detail = hote.base_saine()
        if not saine:
            action, raison = ATTENTE, f"Base locale refusée : {detail}"
    if action == DEMARRER and not local_actif and not hote.demarrer_local():
        return ATTENTE, "Échec du démarrage du conteneur local."
    if action in (ARRETER_LOCAL, ATTENTE) and local_actif:
        hote.arreter_local()  # conteneur relancé seul par Docker : on évite un écrivain non validé
    return action, raison


def executer_bascule(hote) -> tuple[str, str]:
    """Reprise manuelle ici : arrête tout (local puis pair), vérifie, puis seulement redémarre.

    Les conteneurs locaux sont arrêtés d'abord : ni Streamlit ni l'API ne doivent tenir la base
    ouverte pendant que Syncthing peut encore la remplacer (cas de corruption observé).
    """
    if not hote.pair_joignable():
        return decider_bascule(
            pair_joignable=False,
            pair_arrete=False,
            synchronise=False,
            empreintes_egales=False,
            base_saine=False,
            conflits_nouveaux=False,
        )
    conflits_avant = hote.conflits()
    if not hote.arreter_local():
        return ABANDON, "Échec de l'arrêt des conteneurs locaux : bascule annulée."
    pair_arrete = hote.arreter_pair()
    synchronise = bool(pair_arrete and hote.syncthing_pret() and hote.synchronise(scanner=True))
    egales = bool(synchronise and hote.empreintes_identiques())
    saine, detail = hote.base_saine()
    action, raison = decider_bascule(
        pair_joignable=True,
        pair_arrete=pair_arrete,
        synchronise=synchronise,
        empreintes_egales=egales,
        base_saine=saine,
        conflits_nouveaux=bool(hote.conflits() - conflits_avant),
    )
    if action == DEMARRER:
        if not hote.demarrer_local():
            return ABANDON, "Échec du démarrage du conteneur local."
        return action, f"{raison} ({detail})"
    return action, raison if saine else f"{raison} ({detail})"


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
    if mode not in ("start", "stop", "notify", "bascule"):
        print("usage : handoff.py start|stop|notify|bascule [--forcer]", file=sys.stderr)
        return 2
    hote = Hote()
    if mode == "notify":
        return notifier(hote)
    if not PEER:
        _log("DYNASTASIS_PEER_SSH non défini : aucune action.")
        return 2 if mode == "bascule" else 0
    if mode == "bascule":
        action, raison = executer_bascule(hote)
        _log(f"bascule -> {action} : {raison}")
        print(raison)
        ecrire_statut(action, raison)
        return 0 if action == DEMARRER else 1
    if mode == "stop":
        action, raison = executer_arret(hote, forcer="--forcer" in argv)
    else:
        action, raison = executer_demarrage(hote)
    _log(f"{mode} -> {action} : {raison}")
    ecrire_statut(ATTENTE if action == ATTENTE else action, raison)
    return 0  # jamais d'échec d'unité : l'état détaillé est dans le journal et handoff.json


if __name__ == "__main__":
    sys.exit(main(sys.argv))
