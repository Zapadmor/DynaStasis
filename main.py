"""
DynaStasie OS — Orchestrateur CLI

Commandes :
  sync           Toutes les sources configurées, isolées (--only intervals,strava,logos,finance ; --timeout N)
  vigueur        Sync Intervals.icu + Strava PRs → SQLite (--only intervals|strava)
  logos          Sync temps écran Samsung ADB → SQLite
                   --manual : saisie manuelle du temps d'écran sans ADB
  finance        Résumé financier depuis les exports CSV/XLSX
  strava-auth    Autorisation OAuth Strava (scope activity:read_all)
  init-db        Initialise la base de données SQLite
  seed-demo      Crée une base de démonstration fictive (--db chemin, --base-reelle)
  profile        Contenu de profil en base : `profile export [fichier]` / `profile import fichier.json`
  app            Lance l'interface Streamlit (défaut)
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "app"

    if cmd == "sync":
        import argparse

        from src.core.sync_runner import default_sources, exit_code, run_all

        parser = argparse.ArgumentParser(
            prog="main.py sync",
            description="Synchronise chaque source configurée ; l'échec de l'une ne bloque pas les autres.",
        )
        parser.add_argument(
            "--only",
            help="sources à lancer, séparées par des virgules ("
            + ", ".join(s.key for s in default_sources())
            + ")",
        )
        parser.add_argument("--timeout", type=int, help="délai maximal par source, en secondes")
        args = parser.parse_args(sys.argv[2:])
        only = [k.strip() for k in args.only.split(",") if k.strip()] if args.only else None
        inconnues = set(only or []) - {s.key for s in default_sources()}
        if inconnues:
            print(f"Source(s) inconnue(s) : {', '.join(sorted(inconnues))}", file=sys.stderr)
            return 2
        from src.database.connection import init_db

        init_db()  # idempotent : base fraîche (timer lancé avant la première ouverture de l'app)
        return exit_code(run_all(only=only, timeout=args.timeout))

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

    if cmd == "seed-demo":
        import argparse

        from src.core.demo import DEFAULT_DEMO_DB, DemoSeedError, seed_demo

        parser = argparse.ArgumentParser(
            prog="main.py seed-demo", description="Base de démonstration (données fictives)."
        )
        parser.add_argument(
            "--db",
            help=f"base cible (défaut : $DYNASTASIS_DB ou {DEFAULT_DEMO_DB.name} dans data/demo/)",
        )
        parser.add_argument(
            "--base-reelle",
            action="store_true",
            help="autorise l'écrasement de db/dynastasie.db (DESTRUCTIF)",
        )
        args = parser.parse_args(sys.argv[2:])
        try:
            path = seed_demo(
                args.db or os.environ.get("DYNASTASIS_DB"), allow_real_db=args.base_reelle
            )
        except DemoSeedError as exc:
            print(f"Erreur : {exc}", file=sys.stderr)
            return 1
        print(f"[démo] Base créée : {path}")
        print(f"       Lancer l'app : DYNASTASIS_DB={path} python main.py app")
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
        import subprocess
        from pathlib import Path

        root = Path(__file__).resolve().parent
        return subprocess.call(
            ["streamlit", "run", str(root / "src" / "app" / "ui_main.py")],
            cwd=str(root),
            env={**os.environ, "PYTHONPATH": str(root)},
        )

    print(
        f"Commande inconnue : {cmd}\nUsage: python main.py [sync|vigueur|logos|finance|init-db|seed-demo|profile|app]"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
