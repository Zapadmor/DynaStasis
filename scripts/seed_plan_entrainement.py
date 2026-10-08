#!/usr/bin/env python3
"""
Import du plan d'entraînement (exports Google Calendar CSV) dans `plan_entrainement`.

Dérive automatiquement, par ligne :
- mesocycle : préfixe "[...]" du Subject (ex "M1-S1", "M1-S4", "S2-Été", "Kickoff Automne")
- type_semaine : charge (S1/S2) / hardcore (S3) / decharge (S4) / kickoff / hors_cycle
- is_repos : présence du mot "repos" dans le titre (insensible à la casse)
- saison : Automne (23/09-21/12) ou Ete (21/06-23/09) — les CSV actuels ne couvrent que ces 2

Idempotent — UNIQUE(date_jour, titre), re-lancer ne crée pas de doublons (INSERT OR IGNORE).

Usage :
  python scripts/seed_plan_entrainement.py fichier1.csv [fichier2.csv ...]
"""

from __future__ import annotations

import csv
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.database.connection import db_session, init_db

_MESOCYCLE_RE = re.compile(r"^\[([^\]]+)\]")
_SEMAINE_S_RE = re.compile(r"-S(\d)$|^S(\d)-")

_SAISON_BOUNDS = [
    ("Automne", date(2026, 9, 23), date(2026, 12, 21)),
    ("Ete", date(2026, 6, 21), date(2026, 9, 23)),
]


def _parse_date(raw: str) -> str:
    """MM/DD/YYYY (format export Google Calendar US) -> ISO YYYY-MM-DD."""
    m, d, y = raw.strip().split("/")
    return f"{y}-{int(m):02d}-{int(d):02d}"


def _mesocycle(subject: str) -> str | None:
    m = _MESOCYCLE_RE.match(subject.strip())
    return m.group(1) if m else None


def _type_semaine(mesocycle: str | None) -> str:
    if mesocycle is None:
        return "hors_cycle"
    if "Kickoff" in mesocycle:
        return "kickoff"
    m = _SEMAINE_S_RE.search(mesocycle)
    if not m:
        return "hors_cycle"
    s_num = int(m.group(1) or m.group(2))
    return {1: "charge", 2: "charge", 3: "hardcore", 4: "decharge"}.get(s_num, "hors_cycle")


def _saison(date_iso: str) -> str | None:
    """Bornes inclusives des deux côtés : le jour J d'un solstice/équinoxe (fin d'une
    saison ET début de la suivante) est rattaché à la saison qu'il clôture."""
    d = date.fromisoformat(date_iso)
    for nom, debut, fin in _SAISON_BOUNDS:
        if debut <= d <= fin:
            return nom
    return None


def import_csv(path: Path) -> int:
    n = 0
    with open(path, encoding="utf-8") as f, db_session() as conn:
        for row in csv.DictReader(f):
            subject = row["Subject"].strip()
            date_iso = _parse_date(row["Start Date"])
            description = (row.get("Description") or "").strip() or None
            mesocycle = _mesocycle(subject)
            type_semaine = _type_semaine(mesocycle)
            is_repos = 1 if "repos" in subject.lower() else 0
            saison = _saison(date_iso)

            cur = conn.execute(
                """INSERT OR IGNORE INTO plan_entrainement
                   (date_jour, titre, description, mesocycle, type_semaine, is_repos, saison, source_csv)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    date_iso,
                    subject,
                    description,
                    mesocycle,
                    type_semaine,
                    is_repos,
                    saison,
                    path.name,
                ),
            )
            n += cur.rowcount
    return n


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage : python scripts/seed_plan_entrainement.py fichier1.csv [fichier2.csv ...]")
        return 1

    init_db()
    total = 0
    for arg in sys.argv[1:]:
        path = Path(arg)
        if not path.exists():
            print(f"[WARN] Fichier introuvable, ignoré : {path}")
            continue
        n = import_csv(path)
        print(f"[OK] {path.name} : {n} ligne(s) insérée(s).")
        total += n
    print(f"Total : {total} ligne(s) insérée(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
