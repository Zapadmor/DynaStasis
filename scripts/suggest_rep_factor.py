#!/usr/bin/env python3
"""Propose un coefficient `rep_factor` à partir de TES données (rapport de capacités entre deux exercices).

Aucune source scientifique de conversion de reps n'existe pour le muscle-up ou les exercices de grip :
ce script estime « 1 rep de CIBLE vaut k reps de RÉFÉRENCE » avec tes meilleures séries.

Méthode : pour chaque exercice, meilleure série (max de reps) de chaque séance, séries de travail sans lest
(set_type différent de 'W', weight_kg = 0), séances validées uniquement. k = médiane(RÉFÉRENCE) / médiane(CIBLE).
Limite : une série n'est pas forcément menée à l'échec, donc k est une estimation, d'autant moins sûre que
l'échantillon est petit. En dessous de `--min-sessions` séances pour l'un des deux exercices, le script refuse.

Lecture seule : il n'écrit jamais dans la base. La commande SQL proposée est à lancer toi-même.

    python3 scripts/suggest_rep_factor.py --target "Muscle Up" --reference "Pull Up"
"""

from __future__ import annotations

import argparse
import sqlite3
import statistics
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.database import connection  # noqa: E402


class InsufficientData(Exception):
    """Pas assez de séances pour estimer un coefficient fiable."""


def best_reps_per_session(conn: sqlite3.Connection, name: str, since: str) -> list[int]:
    """Meilleure série (reps max) de chaque séance, séries de travail validées et sans lest."""
    rows = conn.execute(
        """
        SELECT MAX(s.reps)
        FROM workout_session_sets s
        JOIN workout_session_exercises x ON x.id = s.session_ex_id
        JOIN workout_sessions w ON w.id = x.session_id
        JOIN exercise_library e ON e.id = x.exercise_id
        WHERE e.name = ? COLLATE NOCASE AND e.unit = 'reps'
          AND s.completed = 1 AND s.set_type != 'W' AND s.weight_kg = 0 AND s.reps > 0
          AND w.date_entry >= ?
        GROUP BY w.id
        """,
        (name, since),
    ).fetchall()
    return [r[0] for r in rows]


def quartiles(values: list[int]) -> tuple[float, float]:
    if len(values) < 2:
        return float(values[0]), float(values[0])
    q = statistics.quantiles(values, n=4, method="inclusive")
    return q[0], q[2]


def suggest(
    conn: sqlite3.Connection, target: str, reference: str, since: str, min_sessions: int
) -> dict:
    tgt = best_reps_per_session(conn, target, since)
    ref = best_reps_per_session(conn, reference, since)
    for label, vals in ((target, tgt), (reference, ref)):
        if len(vals) < min_sessions:
            raise InsufficientData(
                f"Données insuffisantes : {len(vals)} séance(s) validée(s) sans lest pour « {label} » "
                f"depuis {since} (minimum {min_sessions})."
            )
    med_t, med_r = statistics.median(tgt), statistics.median(ref)
    t_lo, t_hi = quartiles(tgt)
    r_lo, r_hi = quartiles(ref)
    return {
        "k": med_r / med_t,
        "k_low": r_lo / t_hi if t_hi else None,
        "k_high": r_hi / t_lo if t_lo else None,
        "target": (len(tgt), med_t),
        "reference": (len(ref), med_r),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Coefficient de reps estimé sur tes propres données.")
    p.add_argument("--target", required=True, help="exercice à convertir (ex. « Muscle Up »)")
    p.add_argument(
        "--reference", default="Pull Up", help="exercice de référence (défaut : Pull Up)"
    )
    p.add_argument(
        "--weeks", type=int, default=26, help="fenêtre d'analyse en semaines (défaut : 26)"
    )
    p.add_argument(
        "--min-sessions", type=int, default=5, help="séances minimum par exercice (défaut : 5)"
    )
    p.add_argument("--db", help="chemin de la base (défaut : DYNASTASIS_DB ou db/dynastasie.db)")
    args = p.parse_args(argv)

    db = Path(args.db) if args.db else connection.DB_PATH
    since = (date.today() - timedelta(weeks=args.weeks)).isoformat()
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)  # lecture seule
    try:
        r = suggest(conn, args.target, args.reference, since, args.min_sessions)
    except InsufficientData as exc:
        print(exc, file=sys.stderr)
        return 2
    finally:
        conn.close()

    (nt, mt), (nr, mr) = r["target"], r["reference"]
    print(f"{args.target} : {nt} séances, médiane des meilleures séries = {mt:g} reps")
    print(f"{args.reference} : {nr} séances, médiane des meilleures séries = {mr:g} reps")
    print(f"Coefficient estimé : 1 {args.target} = {r['k']:.2f} {args.reference}")
    if r["k_low"] and r["k_high"]:
        print(f"Fourchette interquartile : {r['k_low']:.2f} à {r['k_high']:.2f}")
    print(
        "Limites : séries pas forcément menées à l'échec, séries sans lest uniquement, échantillon réduit."
    )
    print("Pour l'appliquer (non fait) :")
    print(
        f'  sqlite3 db/dynastasie.db "UPDATE exercise_library SET rep_factor = {r["k"]:.2f} '
        f"WHERE name = '{args.target}';\""
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
