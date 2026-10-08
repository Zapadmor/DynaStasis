"""
Diagnostic ADB WiFi — réseau, ports, mDNS, mise à jour secrets.

Android 11+ (débogage sans fil / TLS) : le device apparaît AUTOMATIQUEMENT
dans `adb devices` quand le nouveau daemon Google tourne et que le téléphone
a le débogage sans fil activé. `adb connect IP:port` ne fonctionne PAS pour
ces ports TLS — seul `adb devices` après redémarrage du daemon suffit.

Usage :
  python scripts/debug_adb.py              # redémarre daemon + mDNS/devices
  python scripts/debug_adb.py --ports      # scan ports 5555-5565 + plage Android 11+
  python scripts/debug_adb.py --scan       # scan tout le /24 sur port 5555
  python scripts/debug_adb.py --host IP    # forcer une IP
  python scripts/debug_adb.py --no-update  # ne pas modifier le fichier de secrets
"""

from __future__ import annotations

import argparse
import glob
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.config import get_secret, set_secret

DEFAULT_PORT = 5555
CLASSIC_PORTS = list(range(5555, 5566))
WIRELESS_DEBUG_RANGE = (37000, 45000)
WIRELESS_DEBUG_SAMPLE = [37000, 38000, 39000, 40000, 41000, 42000, 43000, 44000, 45000]

# Préférer la version platform-tools Google (≥r31) si installée
_ADB_CANDIDATES = [
    Path.home() / ".local" / "android-platform-tools" / "adb",
    Path("/tmp/platform-tools/adb"),
    Path("/usr/bin/adb"),
]
ADB = str(next((p for p in _ADB_CANDIDATES if p.exists()), Path("adb")))


def run(cmd: list[str], timeout: int = 8) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return -1, f"[timeout après {timeout}s]"
    except FileNotFoundError:
        return -2, f"commande introuvable : {cmd[0]}"


def adb(args: list[str], timeout: int = 8) -> tuple[int, str]:
    return run([ADB, *args], timeout=timeout)


def section(title: str) -> None:
    print(f"\n{'─' * 55}")
    print(f"  {title}")
    print(f"{'─' * 55}")


# ── 1. ADB binaire ───────────────────────────────────────────
def check_adb_installed() -> bool:
    section("1. ADB binaire utilisé")
    rc, out = adb(["version"])
    if rc != 0:
        print(f"  ERREUR  adb non trouvé ({ADB})")
        return False
    build_line = next(
        (line for line in out.splitlines() if line.startswith("Version")), out.splitlines()[0]
    )
    print(f"  {ADB}")
    print(f"  {build_line}")
    if "debian" in out.lower():
        print("  ATTENTION  version Debian obsolète — mDNS/TLS non supportés")
    return True


# ── 2. Secrets ───────────────────────────────────────────────
def check_secrets() -> tuple[str, int]:
    section("2. Secrets — IP/port configurés")
    host = get_secret("samsung", "adb_host")
    port = int(get_secret("samsung", "adb_port") or DEFAULT_PORT)
    if host:
        print(f"  samsung.adb_host = {host}")
        print(f"  samsung.adb_port = {port}  {'(défaut)' if port == DEFAULT_PORT else ''}")
    else:
        print("  MANQUANT  SAMSUNG_ADB_HOST absent (voir secrets.env)")
    return host, port


def update_secrets(new_host: str, new_port: int) -> None:
    path = set_secret("samsung", "adb_host", new_host)
    set_secret("samsung", "adb_port", str(new_port))
    print(f"  {path} mis à jour → adb_host={new_host}  adb_port={new_port}")


# ── 3. Daemon ────────────────────────────────────────────────
def ensure_daemon() -> None:
    """
    Garantit que le daemon ADB en cours est le nouveau binaire Google.
    Si un vieux daemon Debian (/usr/bin/adb) tourne, il ne supporte pas
    les appareils TLS Android 11+ : on le remplace.
    """
    section("3. Daemon ADB")
    old_running = any(_safe_readlink(p) == "/usr/bin/adb" for p in glob.glob("/proc/*/exe"))
    if old_running:
        print("  Vieux daemon Debian détecté — remplacement par le nouveau…")
        run(["/usr/bin/adb", "kill-server"], timeout=5)
        time.sleep(0.5)

    _, out = adb(["start-server"], timeout=10)
    daemon_version = next((line for line in out.splitlines() if "version" in line.lower()), "")
    print(f"  Daemon démarré  {daemon_version or ADB}")


def _safe_readlink(path: str) -> str:
    try:
        return os.readlink(path)
    except OSError:
        return ""


# ── 4. Ping ──────────────────────────────────────────────────
def check_ping(host: str) -> bool:
    section(f"4. Ping {host}")
    rc, out = run(["ping", "-c", "3", "-W", "1", host], timeout=10)
    for line in out.splitlines():
        if any(k in line for k in ("rtt", "round-trip", "packets", "loss")):
            print(f"  {line.strip()}")
    if rc == 0:
        return True
    print(f"  ÉCHEC  {out.splitlines()[-1] if out else 'pas de réponse'}")
    print("  → Téléphone éteint, en mode avion, ou IP changée (--scan pour retrouver).")
    return False


# ── 5. Devices déjà connectés (mDNS auto-discover Android 11+)
def check_devices(host: str) -> str | None:
    """
    Retourne le serial d'un appareil connecté correspondant à host,
    ou le seul appareil présent si un seul est là.
    Android 11+ : le device apparaît ici SANS adb connect, via mDNS auto.
    """
    section("5. Appareils ADB connectés (adb devices -l)")
    rc, out = adb(["devices", "-l"])
    serials: list[str] = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 2 or parts[1] != "device":
            continue
        serial = parts[0]
        model = next((p.split(":")[1] for p in parts if p.startswith("model:")), "")
        marker = "  ←" if host in serial else ""
        print(f"  {serial}  {model}{marker}")
        if host in serial:
            return serial
        serials.append(serial)
    if not serials:
        print("  (aucun appareil)")
        return None
    if len(serials) == 1:
        print(f"  → Un seul appareil — utilisation de {serials[0]}")
        return serials[0]
    print(f"  Plusieurs appareils, aucun ne correspond à {host}")
    return None


# ── 6. Scan ports (info seulement — ne pas connecter sur TLS) ─
def scan_ports(host: str) -> int | None:
    """
    Retourne un port classique (5555-5565) si ouvert.
    Les ports TLS Android 11+ (37000-45000) sont listés à titre informatif :
    ils ne supportent PAS adb connect, le device doit apparaître via adb devices.
    """
    section(f"6. Scan des ports ADB sur {host}")
    classic_open: list[int] = []

    print("  Ports classiques (5555-5565) :")
    for port in CLASSIC_PORTS:
        rc, _ = run(["nc", "-z", "-w", "1", host, str(port)], timeout=2)
        status = "OUVERT  ←" if rc == 0 else "fermé"
        print(f"    {port} : {status}")
        if rc == 0:
            classic_open.append(port)

    rc_nmap, _ = run(["which", "nmap"])
    if rc_nmap == 0:
        print(
            f"\n  Ports TLS Android 11+ ({WIRELESS_DEBUG_RANGE[0]}-{WIRELESS_DEBUG_RANGE[1]}) [info seulement] :"
        )
        _, out2 = run(
            [
                "nmap",
                "-p",
                f"{WIRELESS_DEBUG_RANGE[0]}-{WIRELESS_DEBUG_RANGE[1]}",
                "--open",
                "-T4",
                host,
            ],
            timeout=60,
        )
        found_any = False
        for line in out2.splitlines():
            if "/tcp" in line and "open" in line:
                port = int(line.split("/")[0].strip())
                print(f"    {port} : ouvert (TLS — connexion via adb devices, pas adb connect)")
                found_any = True
        if not found_any:
            print("    (aucun port TLS ouvert)")
    else:
        print("\n  sudo apt install nmap  pour scanner la plage TLS 37000-45000")

    return classic_open[0] if classic_open else None


# ── 7. Connexion legacy (port classique 5555) ────────────────
def adb_connect_legacy(host: str, port: int) -> bool:
    section(f"7. adb connect {host}:{port}  (mode legacy)")
    _, out = adb(["connect", f"{host}:{port}"], timeout=8)
    print(f"  {out}")
    if "connected" not in out.lower() and "already" not in out.lower():
        return False
    _, model = adb(["-s", f"{host}:{port}", "shell", "getprop ro.product.model"], timeout=10)
    if model:
        print(f"  Modèle : {model.strip()}")
    return True


# ── 8. Scan réseau /24 ────────────────────────────────────────
def scan_network(subnet: str) -> list[str]:
    section(f"SCAN réseau {subnet}.0/24 port {DEFAULT_PORT} — ~30s")
    found: list[str] = []
    rc_nmap, _ = run(["which", "nmap"])
    if rc_nmap == 0:
        rc, out = run(
            ["nmap", "-p", str(DEFAULT_PORT), "--open", "-T4", f"{subnet}.0/24"], timeout=90
        )
        ip = None
        for line in out.splitlines():
            if "Nmap scan report" in line:
                ip = line.split()[-1].strip("()")
            elif str(DEFAULT_PORT) in line and "open" in line and ip:
                print(f"  {ip}:{DEFAULT_PORT}  OUVERT")
                found.append(ip)
    else:
        print("  nmap absent — scan nc (lent)…")
        for i in range(1, 255):
            ip = f"{subnet}.{i}"
            rc, _ = run(["nc", "-z", "-w", "1", ip, str(DEFAULT_PORT)], timeout=2)
            if rc == 0:
                print(f"  {ip}:{DEFAULT_PORT}  OUVERT")
                found.append(ip)
    return found


def suggest_fix(host: str, ping_ok: bool, connect_ok: bool) -> None:
    section("Diagnostic résumé")
    if connect_ok:
        print("  Connexion ADB opérationnelle.")
        return
    if not ping_ok:
        print(f"  Téléphone injoignable ({host}).")
        print("  Sur un nouveau réseau : relancer avec --scan pour retrouver l'IP.")
        print("  Pas besoin de re-appairer — la clé RSA est mémorisée sur le téléphone.")
    else:
        print(f"  Téléphone joignable ({host}) mais aucun appareil ADB visible.")
        print("  → Activer le débogage sans fil sur le téléphone, puis relancer ce script.")
        print("     Paramètres → Options développeur → Débogage sans fil")
        print("  → Si premier usage sur ce PC : adb pair IP:port  (code affiché sur téléphone)")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Diagnostique et auto-configure la connexion ADB WiFi."
    )
    parser.add_argument("--host", default=None, help="Forcer une IP.")
    parser.add_argument("--ports", action="store_true", help="Scanner les ports ADB.")
    parser.add_argument("--scan", action="store_true", help="Scanner tout le /24 sur port 5555.")
    parser.add_argument(
        "--no-update", action="store_true", help="Ne pas modifier le fichier de secrets."
    )
    args = parser.parse_args()

    print("=== DEBUG ADB — DynaStasie ===")

    if not check_adb_installed():
        return 1

    host, configured_port = check_secrets()
    if args.host:
        host = args.host
    if not host:
        return 1

    # Garantir le bon daemon AVANT toute recherche de device
    ensure_daemon()

    # Android 11+ : le device apparaît automatiquement sans adb connect
    serial = check_devices(host)
    connect_ok = serial is not None

    if connect_ok and not args.no_update:
        # Extraire l'IP réelle depuis le serial si c'est une adresse IP:port
        parts = serial.split(":")
        if len(parts) == 2 and parts[0].count(".") == 3:
            real_ip, real_port = parts[0], int(parts[1])
            if real_ip != host or real_port != configured_port:
                section("Mise à jour des secrets")
                update_secrets(real_ip, real_port)
        suggest_fix(host, True, True)
        return 0

    # Ping + scan ports pour diagnostiquer
    ping_ok = check_ping(host)

    if ping_ok:
        if args.ports:
            classic_port = scan_ports(host)
            # Tenter connexion legacy si un port classique est ouvert
            if classic_port:
                connect_ok = adb_connect_legacy(host, classic_port)
                if connect_ok and not args.no_update:
                    section("Mise à jour des secrets")
                    update_secrets(host, classic_port)

    if args.scan and not connect_ok:
        subnet = ".".join(host.split(".")[:3])
        found = scan_network(subnet)
        for new_ip in found:
            rc_p, _ = run(["nc", "-z", "-w", "2", new_ip, str(DEFAULT_PORT)], timeout=3)
            if rc_p == 0 and adb_connect_legacy(new_ip, DEFAULT_PORT):
                connect_ok = True
                if not args.no_update:
                    section("Mise à jour des secrets")
                    update_secrets(new_ip, DEFAULT_PORT)
                break

    suggest_fix(host, ping_ok, connect_ok)
    return 0 if connect_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
