"""
DynaStasie OS — Orchestrateur CLI

Commandes :
  sync           Toutes les sources configurées, isolées (--only / --skip intervals,strava,logos,finance ; --timeout N)
  init-db        Initialise la base de données SQLite
  seed-demo      Crée une base de démonstration fictive (--db chemin, --base-reelle)
  profile        Contenu de profil en base : `profile export [fichier]` / `profile import fichier.json`
  app            Lance l'interface Streamlit (défaut)

Les commandes propres à un pilier (vigueur, logos, finance, strava-auth…) sont déclarées dans
`src/pillars/` : `python main.py --help` les liste.
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "app"

    if cmd in ("-h", "--help", "help"):
        from src.pillars import commands  # noqa: PLC0415

        print((__doc__ or "").rstrip())
        print("\nCommandes des piliers :")
        for c in commands().values():
            print(f"  {c.name:<14} {c.help}")
        return 0

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
        parser.add_argument(
            "--skip",
            help="sources à exclure, séparées par des virgules (ex. logos, lancé depuis l'hôte)",
        )
        parser.add_argument("--timeout", type=int, help="délai maximal par source, en secondes")
        args = parser.parse_args(sys.argv[2:])
        only = [k.strip() for k in args.only.split(",") if k.strip()] if args.only else None
        skip = [k.strip() for k in args.skip.split(",") if k.strip()] if args.skip else None
        inconnues = set((only or []) + (skip or [])) - {s.key for s in default_sources()}
        if inconnues:
            print(f"Source(s) inconnue(s) : {', '.join(sorted(inconnues))}", file=sys.stderr)
            return 2
        from src.database.connection import init_db

        init_db()  # idempotent : base fraîche (timer lancé avant la première ouverture de l'app)
        return exit_code(run_all(only=only, timeout=args.timeout, skip=skip))

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

    from src.pillars import commands  # noqa: PLC0415

    piliers = commands()
    if cmd in piliers:
        return piliers[cmd].run(sys.argv[2:])

    noyau = ["sync", "init-db", "seed-demo", "profile", "app"]
    print(f"Commande inconnue : {cmd}\nUsage: python main.py [{'|'.join([*noyau, *piliers])}]")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
