from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

from src.config import get_secret
from src.core.tz import now_local

# ADB stocke ses clés RSA dans $HOME/.android — on force HOME pour que le
# daemon ne tente pas de créer un chemin invalide si la variable est absente.
_ADB_ENV = {**os.environ, "HOME": str(Path.home())}

# Préférer la version platform-tools Google (≥r31) si installée, sinon fallback système.
_ADB_CANDIDATES = [
    Path.home() / ".local" / "android-platform-tools" / "adb",
    Path("/tmp/platform-tools/adb"),
    Path("/usr/bin/adb"),
]
_ADB_BIN = next((str(p) for p in _ADB_CANDIDATES if p.exists()), "adb")

# Service mDNS publié par le débogage sans fil d'Android 11+ (jumelé une fois, sans IP fixe).
_MDNS_CONNECT = "_adb-tls-connect._tcp"
_MDNS_WAIT_S = 10  # attente maximale de l'apparition de l'appareil après découverte

_EVENT_RE = re.compile(r'time="(?P<ts>[^"]+)" type=(?P<type>\S+) package=(?P<pkg>\S+)')

# Human-readable names for well-known package IDs
KNOWN_APPS: dict[str, str] = {
    "com.instagram.android": "Instagram",
    "com.twitter.android": "X (Twitter)",
    "com.facebook.katana": "Facebook",
    "com.google.android.youtube": "YouTube",
    "com.whatsapp": "WhatsApp",
    "com.snapchat.android": "Snapchat",
    "com.reddit.frontpage": "Reddit",
    "com.netflix.mediaclient": "Netflix",
    "com.spotify.music": "Spotify",
    "com.google.android.gm": "Gmail",
    "com.android.chrome": "Chrome",
    "com.discord": "Discord",
    "com.telegram.messenger": "Telegram",
    "com.linkedin.android": "LinkedIn",
    "com.zhiliaoapp.musically": "TikTok",
    "com.samsung.android.health": "Samsung Health",
    "com.samsung.android.messaging": "Messages",
    "com.google.android.apps.maps": "Google Maps",
    "com.google.android.apps.photos": "Google Photos",
    "com.google.android.keep": "Google Keep",
    "com.duolingo": "Duolingo",
    "com.chess": "Chess.com",
    "com.google.android.calendar": "Google Calendar",
    "com.kakao.talk": "KakaoTalk",
    "notion.id": "Notion",
    "com.beeper.android": "Beeper",
    "fr.leboncoin": "Leboncoin",
    "com.google.android.apps.messaging": "Messages Google",
    "deezer.android.app": "Deezer",
    "com.supercell.brawlstars": "Brawl Stars",
    "com.google.android.apps.docs.editors.docs": "Google Docs",
    "com.google.android.apps.docs.editors.sheets": "Google Sheets",
    "com.google.android.apps.docs": "Google Drive",
}

# Package prefixes that are internal system services (not counted as screen time)
_SYSTEM_PREFIXES = (
    "android",
    "com.android.",
    "com.google.android.gms",
    "com.google.android.gsf",
    "com.google.android.ext.services",
    "com.google.android.permissioncontroller",
    "com.sec.",
    "com.qualcomm.",
    "com.qti.",
    "com.mediatek.",
    "com.samsung.android.providers",
    "com.samsung.android.app.",
    "com.samsung.android.wifi",
    "com.samsung.android.bluetooth",
    "com.samsung.android.net.",
    "com.samsung.android.nfc",
    "com.samsung.android.server",
    "com.samsung.android.incallui",
    "com.samsung.android.dialer",
    "com.sec.android.app.launcher",  # Samsung home screen launcher
)

# Minimum session duration to record (avoids noise from accidental taps)
_MIN_SESSION_SECONDS = 5.0


def parse_mdns_services(output: str) -> list[str]:
    """Extrait les `ip:port` des services `_adb-tls-connect._tcp` de `adb mdns services`."""
    addrs = []
    for line in output.splitlines():
        parts = line.split()
        if _MDNS_CONNECT in parts and parts[-1] != _MDNS_CONNECT:
            addrs.append(parts[-1])
    return addrs


def _is_system_package(package: str) -> bool:
    return any(package == p or package.startswith(p) for p in _SYSTEM_PREFIXES)


def _resolve_app_name(package: str) -> str:
    if package in KNOWN_APPS:
        return KNOWN_APPS[package]
    parts = [p for p in package.split(".") if p not in ("com", "android", "app", "apps")]
    return parts[-1].capitalize() if parts else package


class AdbClient:
    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        if shutil.which(_ADB_BIN) is None:
            raise RuntimeError(
                "`adb` est introuvable. Installez android-tools (apt install adb) ou, avec Docker, "
                "reconstruisez l'image avec la cible adb : DYNASTASIS_TARGET=adb docker compose up -d --build."
            )
        # L'IP est facultative : sans elle (ou si elle est périmée après un changement de réseau),
        # l'appareil jumelé est retrouvé par mDNS.
        self.host = host or get_secret("samsung", "adb_host") or ""
        self.port = port or int(get_secret("samsung", "adb_port") or 5555)
        self.target = f"{self.host}:{self.port}" if self.host else ""

    def _adb(self, args: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
        return subprocess.run(
            [_ADB_BIN, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_ADB_ENV,
        )

    def _find_connected_device(self) -> str | None:
        """
        Retourne le serial d'un appareil déjà connecté qui correspond à self.host,
        ou le premier appareil connecté si un seul est présent.
        Utile quand Android 11+ wireless debug utilise un serial TLS au lieu d'IP:port.
        """
        result = self._adb(["devices", "-l"], timeout=8)
        serials = []
        for line in result.stdout.splitlines():
            parts = line.split()
            # format : <serial> <state> [product:... model:... ...]
            # "offline" et "unauthorized" sont ignorés
            if len(parts) < 2 or parts[1] != "device":
                continue
            serial = parts[0]
            if self.host and self.host in serial:
                return serial
            serials.append(serial)
        return serials[0] if len(serials) == 1 else None

    def _ensure_new_daemon(self) -> None:
        """
        Si le daemon ADB en cours vient du paquet Debian système (/usr/bin/adb,
        version 28.0.2), il ne supporte pas les appareils TLS Android 11+.
        On détecte ça en regardant le binaire du processus adb serveur en cours.
        """
        try:
            import glob

            for pid_path in glob.glob("/proc/*/exe"):
                try:
                    exe = os.readlink(pid_path)
                except OSError:
                    continue
                if exe == "/usr/bin/adb":
                    # Vieux daemon Debian — le remplacer
                    subprocess.run(
                        [_ADB_BIN, "kill-server"], capture_output=True, env=_ADB_ENV, timeout=5
                    )
                    subprocess.run(
                        [_ADB_BIN, "start-server"], capture_output=True, env=_ADB_ENV, timeout=10
                    )
                    break
        except Exception:
            pass

    def _mdns_addresses(self) -> list[str]:
        """Adresses `ip:port` des appareils qui annoncent le débogage sans fil (mDNS)."""
        try:
            out = self._adb(["mdns", "services"], timeout=8).stdout
        except (subprocess.TimeoutExpired, OSError):
            return []
        return parse_mdns_services(out)

    def _connect_via_mdns(self) -> str | None:
        """Retrouve l'appareil jumelé sur le réseau courant, sans connaître son IP."""
        for addr in self._mdns_addresses():
            try:
                self._adb(["connect", addr], timeout=8)
            except (subprocess.TimeoutExpired, OSError):
                continue
        deadline = time.monotonic() + _MDNS_WAIT_S
        while True:
            device = self._find_connected_device()
            if device or time.monotonic() >= deadline:
                return device
            time.sleep(1)

    def connect(self) -> None:
        self._ensure_new_daemon()

        # 1. Appareil déjà visible (mDNS auto-découverte Android 11+)
        already = self._find_connected_device()
        if already:
            self.target = already
            return

        # 2. Découverte mDNS : indépendante de l'IP, donc valable d'un réseau à l'autre
        found = self._connect_via_mdns()
        if found:
            self.target = found
            return

        # 3. Repli sur l'IP configurée
        if not self.target:
            raise RuntimeError(
                "Aucun téléphone trouvé par mDNS. Vérifiez que le débogage sans fil est activé, "
                "que le téléphone est sur le même réseau et déjà jumelé, ou définissez "
                "SAMSUNG_ADB_HOST dans secrets.env."
            )
        try:
            result = self._adb(["connect", self.target], timeout=8)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"ADB connect vers {self.target} a expiré (8s) — "
                "vérifier que le Samsung est sur le même réseau WiFi et que "
                "le débogage WiFi ADB est activé (Paramètres → Options développeur)."
            ) from exc
        output = (result.stdout + result.stderr).lower()
        if "connected" not in output and "already" not in output:
            raise RuntimeError(
                f"ADB connect vers {self.target} a échoué (mDNS n'a rien trouvé non plus) : "
                f"{(result.stdout + result.stderr).strip()}"
            )

    def shell(self, command: str, timeout: int = 60) -> str:
        result = self._adb(["-s", self.target, "shell", command], timeout=timeout)
        if result.returncode != 0:
            raise RuntimeError(f"ADB shell a échoué : {result.stderr.strip()}")
        return result.stdout


def _parse_events_to_sessions(raw: str, since: datetime) -> list[dict]:
    """
    Parse ACTIVITY_RESUMED/PAUSED events from dumpsys usagestats output.

    Returns a list of completed sessions:
        {package, name, start (ISO str), end (ISO str), duration_seconds}

    Deduplication anchor: (package, start) is unique per app session.
    SCREEN_NON_INTERACTIVE closes all open sessions at screen-off time.
    Sessions shorter than _MIN_SESSION_SECONDS are discarded (tap noise).
    """
    sessions: list[dict] = []
    active: dict[str, datetime] = {}  # package -> resumed_at
    screen_on = True
    now = now_local()

    for line in raw.splitlines():
        m = _EVENT_RE.search(line)
        if not m:
            continue
        try:
            ts = datetime.strptime(m.group("ts"), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue

        event_type = m.group("type")
        pkg = m.group("pkg")

        if event_type == "SCREEN_NON_INTERACTIVE":
            screen_on = False
            for p, start in list(active.items()):
                _maybe_add(sessions, p, start, min(ts, now), since)
            active.clear()

        elif event_type == "SCREEN_INTERACTIVE":
            screen_on = True

        elif event_type == "ACTIVITY_RESUMED":
            if screen_on and not _is_system_package(pkg):
                active[pkg] = ts

        elif event_type in ("ACTIVITY_PAUSED", "ACTIVITY_STOPPED"):
            if pkg in active:
                start = active.pop(pkg)
                _maybe_add(sessions, pkg, start, min(ts, now), since)

    # Close sessions still open when the dump was taken (app in foreground right now)
    for pkg, start in active.items():
        _maybe_add(sessions, pkg, start, now, since)

    return sessions


def _maybe_add(
    sessions: list[dict],
    pkg: str,
    start: datetime,
    end: datetime,
    since: datetime,
) -> None:
    """Add a session to the list if it passes the start and duration filters."""
    if start < since:
        start = since  # clip to week boundary instead of discarding
    dur = (end - start).total_seconds()
    if dur < _MIN_SESSION_SECONDS:
        return
    sessions.append(
        {
            "package": pkg,
            "name": _resolve_app_name(pkg),
            "start": start.strftime("%Y-%m-%dT%H:%M:%S"),
            "end": end.strftime("%Y-%m-%dT%H:%M:%S"),
            "duration_seconds": round(dur, 1),
        }
    )


def get_screen_time_summary(
    host: str | None = None,
    top_n: int = 5,
    min_minutes: float = 1.0,
) -> dict:
    """
    Fetch events from Samsung, merge into the persistent store,
    and return the aggregated weekly summary.
    """
    from src.collectors.screen_time_store import (
        aggregate_week,
        load_store,
        merge_sessions,
        purge_old_sessions,
        save_store,
        week_start_dt,
    )

    now = now_local()
    ws = week_start_dt()

    client = AdbClient(host=host)
    adb_error: str | None = None
    new_sessions: list[dict] = []
    try:
        client.connect()
        raw = client.shell("dumpsys usagestats")
        new_sessions = _parse_events_to_sessions(raw, ws)
    except RuntimeError as exc:
        adb_error = str(exc)
        print(f"[ADB] connexion échouée : {adb_error}")

    store = load_store()
    if adb_error is None:
        merged, added = merge_sessions(store["sessions"], new_sessions)
        store["sessions"] = purge_old_sessions(merged)
        store["last_fetched"] = now.strftime("%Y-%m-%dT%H:%M:%S")
        save_store(store)
        print(
            f"ADB: {len(new_sessions)} sessions parsées, "
            f"{added} nouvelles ajoutées, "
            f"{len(store['sessions'])} total en base."
        )
    else:
        added = 0
        print(
            f"ADB: collecte ignorée (erreur réseau) — "
            f"{len(store['sessions'])} sessions en cache utilisées."
        )

    weekly = aggregate_week(store["sessions"], ws)
    weekly = [a for a in weekly if a["foreground_minutes"] >= min_minutes]
    total_minutes = round(sum(a["foreground_minutes"] for a in weekly), 1)

    return {
        "total_screen_time_minutes": total_minutes,
        "top_apps": weekly[:top_n],
        "all_apps": weekly,
        "new_sessions_added": added,
        "adb_error": adb_error,
    }
