"""Sans `adb` installé, le client ADB échoue avec un message lisible (image Docker par défaut)."""

import pytest

from src.collectors import screen_time_client


def test_adb_absent_message_clair(monkeypatch):
    monkeypatch.setattr(screen_time_client, "_ADB_BIN", "adb-inexistant-xyz")
    with pytest.raises(RuntimeError, match="adb.*introuvable"):
        screen_time_client.AdbClient(host="192.0.2.1")
