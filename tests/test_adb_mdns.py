"""Connexion ADB : découverte mDNS avant l'IP configurée, échec signalé par le bot logos."""

from __future__ import annotations

import subprocess

import pytest

from bots import logos_bot
from src.collectors import screen_time_client as stc

TLS = "adb-RZCX10V7YWF-m9hYRI._adb-tls-connect._tcp"


def test_parse_mdns_services():
    sortie = (
        "List of discovered mdns services\n"
        "adb-ABC\t_adb-tls-connect._tcp\t192.168.1.20:41234\n"
        "adb-ABC\t_adb-tls-pairing._tcp\t192.168.1.20:37000\n"
    )
    assert stc.parse_mdns_services(sortie) == ["192.168.1.20:41234"]
    assert stc.parse_mdns_services("List of discovered mdns services\n") == []


class _Faux:
    """Remplace `AdbClient._adb` : rejoue des sorties prévues et mémorise les appels."""

    def __init__(self, devices=(), mdns="", connect_out="failed to connect"):
        self.devices = list(devices)  # un élément par appel à `devices`; le dernier se répète
        self.mdns = mdns
        self.connect_out = connect_out
        self.appels: list[list[str]] = []

    def __call__(self, args, timeout=60):
        self.appels.append(args)
        out = ""
        if args[0] == "devices":
            out = self.devices.pop(0) if len(self.devices) > 1 else self.devices[0]
        elif args[0] == "mdns":
            out = self.mdns
        elif args[0] == "connect":
            out = self.connect_out
        return subprocess.CompletedProcess(args, 0, out, "")


def _client(monkeypatch, faux, host=""):
    monkeypatch.setattr(stc.shutil, "which", lambda _: "/usr/bin/adb")
    monkeypatch.setattr(stc.AdbClient, "_ensure_new_daemon", lambda self: None)
    monkeypatch.setattr(stc.time, "sleep", lambda _: None)
    monkeypatch.setattr(stc, "_MDNS_WAIT_S", 0)
    monkeypatch.setattr(stc, "get_secret", lambda *a, **k: None)
    client = stc.AdbClient(host=host or None)
    monkeypatch.setattr(client, "_adb", faux)
    return client


def _liste(*lignes):
    return "List of devices attached\n" + "".join(f"{x}\n" for x in lignes)


def test_appareil_deja_connecte_sans_ip(monkeypatch):
    faux = _Faux(devices=[_liste(f"{TLS} device product:x")])
    client = _client(monkeypatch, faux)
    client.connect()
    assert client.target == TLS
    assert not any(a[0] == "connect" for a in faux.appels)


def test_mdns_utilise_avant_l_ip_perimee(monkeypatch):
    faux = _Faux(
        devices=[_liste(), _liste(f"{TLS} device")],
        mdns="adb-ABC\t_adb-tls-connect._tcp\t192.168.1.20:41234\n",
        connect_out="connected to 192.168.1.20:41234",
    )
    client = _client(monkeypatch, faux, host="192.168.13.99")
    client.connect()
    assert client.target == TLS
    assert [a for a in faux.appels if a[0] == "connect"] == [["connect", "192.168.1.20:41234"]]


def test_repli_sur_l_ip_configuree(monkeypatch):
    faux = _Faux(devices=[_liste()], connect_out="connected to 192.168.1.5:5555")
    client = _client(monkeypatch, faux, host="192.168.1.5")
    client.connect()
    assert client.target == "192.168.1.5:5555"


def test_echec_sans_ip_ni_mdns(monkeypatch):
    client = _client(monkeypatch, _Faux(devices=[_liste()]))
    with pytest.raises(RuntimeError, match="mDNS"):
        client.connect()


def test_echec_avec_ip_mentionne_mdns(monkeypatch):
    client = _client(monkeypatch, _Faux(devices=[_liste()]), host="192.168.1.5")
    with pytest.raises(RuntimeError, match="mDNS n'a rien trouvé"):
        client.connect()


def test_bot_logos_signale_l_echec_adb(monkeypatch, capsys):
    monkeypatch.setattr(
        logos_bot,
        "run",
        lambda **kw: {"summary": {"adb_error": "No route to host"}},
    )
    monkeypatch.setattr("sys.argv", ["logos"])
    assert logos_bot.main() == 1
    sortie = capsys.readouterr().out
    assert "ÉCHEC ADB" in sortie and "No route to host" in sortie


def test_bot_logos_ok(monkeypatch):
    monkeypatch.setattr(logos_bot, "run", lambda **kw: {"summary": {"adb_error": None}})
    monkeypatch.setattr("sys.argv", ["logos"])
    assert logos_bot.main() == 0
