"""Sauvegarde de la base SQLite : copie cohérente (API `backup`) avec rotation.

    python3 scripts/backup_db.py [--db chemin] [--dest dossier] [--keep 14]

Par défaut : $DYNASTASIS_DB ou db/dynastasie.db, vers ~/.local/share/dynastasie/db-backups/.
La base source n'est ouverte qu'en lecture ; la copie est vérifiée (`integrity_check`) avant la rotation.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DEST = Path.home() / ".local" / "share" / "dynastasie" / "db-backups"
PREFIX = "dynastasie-"


def backup(db: Path, dest: Path, keep: int = 14, now: datetime | None = None) -> Path:
    """Crée `dynastasie-AAAAMMJJ-HHMMSS.db` dans `dest`, puis ne garde que les `keep` plus récents."""
    if not db.is_file():
        raise FileNotFoundError(f"Base introuvable : {db}")
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / f"{PREFIX}{(now or datetime.now()).strftime('%Y%m%d-%H%M%S')}.db"
    partial = target.with_suffix(".db.part")
    src = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        out = sqlite3.connect(partial)
        try:
            src.backup(out)
            verdict = out.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            out.close()
    finally:
        src.close()
    if verdict != "ok":
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"Copie corrompue ({verdict}) : sauvegarde abandonnée")
    partial.replace(target)
    for old in sorted(dest.glob(f"{PREFIX}*.db"))[:-keep] if keep > 0 else []:
        old.unlink()
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Sauvegarde rotative de la base SQLite.")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(os.environ.get("DYNASTASIS_DB") or ROOT_DIR / "db" / "dynastasie.db"),
    )
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument("--keep", type=int, default=14, help="nombre de sauvegardes conservées")
    args = parser.parse_args()
    try:
        target = backup(args.db, args.dest, args.keep)
    except (OSError, sqlite3.Error, RuntimeError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    print(f"Sauvegarde : {target} ({target.stat().st_size // 1024} Ko)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
