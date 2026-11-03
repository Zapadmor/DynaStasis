"""Documents markdown stockés en base (table `documents`).

Les notes et rapports personnels vivent dans la base SQLite (hors dépôt), jamais dans l'historique
git. `import_documents` est idempotent : la clé d'un document est son chemin relatif au dossier
importé, et un document dont le contenu n'a pas changé n'est pas modifié.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from src.database.connection import db_session


@dataclass(frozen=True)
class ImportResult:
    ajoutes: int
    modifies: int
    inchanges: int


def _titre(contenu: str, source: str) -> str:
    """Premier titre de niveau 1 hors blocs de code, sinon le nom du fichier sans extension."""
    in_code = False
    for ligne in contenu.splitlines():
        s = ligne.strip()
        if s.startswith(("```", "~~~")):
            in_code = not in_code
        elif not in_code and s.startswith("# ") and s[2:].strip():
            return s[2:].strip()
    return PurePosixPath(source).stem


def _categorie(source: str) -> str:
    parts = PurePosixPath(source).parts
    return parts[0] if len(parts) > 1 else ""


def _fichiers_markdown(racine: Path) -> list[Path]:
    return sorted(
        p
        for p in racine.rglob("*.md")
        if p.is_file() and not any(part.startswith(".") for part in p.relative_to(racine).parts)
    )


def import_documents(dossier: str | Path, categorie: str | None = None) -> ImportResult:
    """Importe (ou met à jour) tous les `.md` d'un dossier, récursivement."""
    racine = Path(dossier).expanduser().resolve()
    if not racine.is_dir():
        raise FileNotFoundError(f"Dossier introuvable : {dossier}")
    ajoutes = modifies = inchanges = 0
    with db_session() as conn:
        for fichier in _fichiers_markdown(racine):
            source = unicodedata.normalize("NFC", fichier.relative_to(racine).as_posix())
            contenu = fichier.read_text(encoding="utf-8")
            row = conn.execute(
                "SELECT contenu_md, categorie FROM documents WHERE source = ?", (source,)
            ).fetchone()
            cat = categorie if categorie is not None else _categorie(source)
            if row is None:
                conn.execute(
                    "INSERT INTO documents (source, titre, categorie, contenu_md) "
                    "VALUES (?, ?, ?, ?)",
                    (source, _titre(contenu, source), cat, contenu),
                )
                ajoutes += 1
            elif row["contenu_md"] != contenu or row["categorie"] != cat:
                conn.execute(
                    "UPDATE documents SET titre = ?, categorie = ?, contenu_md = ?, "
                    "updated_at = datetime('now', 'localtime') WHERE source = ?",
                    (_titre(contenu, source), cat, contenu, source),
                )
                modifies += 1
            else:
                inchanges += 1
    return ImportResult(ajoutes, modifies, inchanges)


def export_documents(dossier: str | Path, ecraser: bool = False) -> int:
    """Réécrit les documents sous `dossier` (même arborescence). Retourne le nombre de fichiers.

    Tout est vérifié avant la première écriture : chemin hors du dossier cible ou fichier
    existant (sauf `ecraser`) font échouer l'export entier.
    """
    destination = Path(dossier).expanduser().resolve()
    with db_session() as conn:
        rows = conn.execute("SELECT source, contenu_md FROM documents ORDER BY source").fetchall()
    cibles: list[tuple[Path, str]] = []
    for r in rows:
        cible = (destination / r["source"]).resolve()
        if destination not in cible.parents:
            raise ValueError(f"Chemin hors du dossier cible : {r['source']}")
        if cible.exists() and not ecraser:
            raise FileExistsError(f"Fichier existant (utiliser --ecraser) : {cible}")
        cibles.append((cible, r["contenu_md"]))
    for cible, contenu in cibles:
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_text(contenu, encoding="utf-8")
    return len(cibles)


def list_documents() -> list[dict]:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT id, categorie, titre, source, length(CAST(contenu_md AS BLOB)) AS taille, "
            "updated_at FROM documents ORDER BY categorie, titre"
        ).fetchall()
    return [dict(r) for r in rows]
