"""
DynaStasie OS — Orchestrateur CLI

Commandes :
  vigueur        Sync Intervals.icu + Strava PRs → SQLite
  logos          Sync temps écran Samsung ADB → SQLite
                   --manual : saisie manuelle du temps d'écran sans ADB
  finance        Résumé financier depuis les exports CSV/XLSX
  strava-auth    Autorisation OAuth Strava (scope activity:read_all)
  init-db        Initialise la base de données SQLite
  profile        Contenu de profil en base : `profile export [fichier]` / `profile import fichier.json`
  app            Lance l'interface Streamlit (défaut)
"""

from __future__ import annotations

import sys


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "app"

    if cmd == "vigueur":
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        from bots.vigueur_bot import main as _m

        return _m()

    if cmd == "logos":
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        from bots.logos_bot import main as _m

        return _m()

    if cmd == "finance":
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        from src.collectors.finance_collector import main as _m

        return _m()

    if cmd == "strava-auth":
        from src.collectors.strava_client import StravaAPIError, StravaClient

        try:
            StravaClient().authorize()
        except StravaAPIError as exc:
            print(f"Erreur : {exc}", file=sys.stderr)
            return 1
        return 0

    if cmd == "init-db":
        from src.database.connection import init_db

        init_db()
        return 0

    if cmd == "profile":
        from src.core.profile import export_profile, import_profile

        action = sys.argv[2] if len(sys.argv) > 2 else ""
        target = sys.argv[3] if len(sys.argv) > 3 else None
        if action == "export":
            return export_profile(target)
        if action == "import" and target:
            return import_profile(target)
        print("Usage: python main.py profile export [fichier] | profile import fichier.json")
        return 1

    if cmd == "app":
        import os
        import subprocess
        from pathlib import Path

        root = Path(__file__).resolve().parent
        return subprocess.call(
            ["streamlit", "run", str(root / "src" / "app" / "ui_main.py")],
            cwd=str(root),
            env={**os.environ, "PYTHONPATH": str(root)},
        )

    print(
        f"Commande inconnue : {cmd}\nUsage: python main.py [vigueur|logos|finance|init-db|profile|app]"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
