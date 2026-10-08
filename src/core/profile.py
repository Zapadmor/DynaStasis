"""Contenu de profil stocké en base (table `profil_contenu`).

Tout ce qui est personnel (plans, textes, référentiels, objectifs) vit dans la base SQLite,
jamais dans le code. Les valeurs sont du JSON ; `default` est renvoyé si la clé est absente
ou si la table n'existe pas encore.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from typing import Any

from src.database.connection import db_session


def get_profile(key: str, default: Any = None) -> Any:
    try:
        with db_session() as conn:
            row = conn.execute(
                "SELECT valeur_json FROM profil_contenu WHERE cle = ?", (key,)
            ).fetchone()
    except sqlite3.OperationalError:
        return default
    if row is None:
        return default
    try:
        return json.loads(row["valeur_json"])
    except json.JSONDecodeError:
        return default


def set_profile(key: str, value: Any) -> None:
    with db_session() as conn:
        conn.execute(
            "INSERT INTO profil_contenu (cle, valeur_json, updated_at) "
            "VALUES (?, ?, datetime('now', 'localtime')) "
            "ON CONFLICT(cle) DO UPDATE SET valeur_json = excluded.valeur_json, "
            "updated_at = excluded.updated_at",
            (key, json.dumps(value, ensure_ascii=False)),
        )


def export_profile(path: str | None = None) -> int:
    """Exporte tout le contenu de profil en JSON (stdout ou fichier)."""
    with db_session() as conn:
        rows = conn.execute("SELECT cle, valeur_json FROM profil_contenu ORDER BY cle").fetchall()
    data = {r["cle"]: json.loads(r["valeur_json"]) for r in rows}
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if path:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"[profil] {len(data)} clé(s) exportée(s) → {path}")
    else:
        print(text)
    return 0


def import_profile(path: str) -> int:
    """Importe un fichier JSON {clé: valeur} dans la table `profil_contenu`."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        print("Le fichier doit contenir un objet JSON {clé: valeur}.", file=sys.stderr)
        return 1
    for key, value in data.items():
        set_profile(key, value)
    print(f"[profil] {len(data)} clé(s) importée(s)")
    return 0
