"""Documents markdown en base : import idempotent, export sûr, migration."""

from __future__ import annotations

import sqlite3
import unicodedata

import pytest

from src.core import documents
from src.database import connection


@pytest.fixture
def dossier(tmp_path):
    racine = tmp_path / "notes"
    (racine / "rapports").mkdir(parents=True)
    (racine / "veille" / "sous").mkdir(parents=True)
    (racine / "rapports" / "bilan.md").write_text("# Bilan annuel\n\ncorps\n", encoding="utf-8")
    (racine / "veille" / "sous" / "idee.md").write_text("sans titre\n", encoding="utf-8")
    (racine / "racine.md").write_text("```\n# pas un titre\n```\n# Vrai titre\n", encoding="utf-8")
    (racine / "ignore.txt").write_text("pas du markdown", encoding="utf-8")
    (racine / ".cache").mkdir()
    (racine / ".cache" / "cache.md").write_text("# caché\n", encoding="utf-8")
    return racine


def _lignes(db):
    with sqlite3.connect(db) as c:
        c.row_factory = sqlite3.Row
        return {r["source"]: dict(r) for r in c.execute("SELECT * FROM documents")}


def test_import_titre_categorie_et_fichiers_ignores(db, dossier):
    r = documents.import_documents(dossier)
    assert (r.ajoutes, r.modifies, r.inchanges) == (3, 0, 0)
    lignes = _lignes(db)
    assert set(lignes) == {"rapports/bilan.md", "veille/sous/idee.md", "racine.md"}
    assert lignes["rapports/bilan.md"]["titre"] == "Bilan annuel"
    assert lignes["rapports/bilan.md"]["categorie"] == "rapports"
    assert lignes["veille/sous/idee.md"]["titre"] == "idee"  # sans titre : nom du fichier
    assert lignes["veille/sous/idee.md"]["categorie"] == "veille"
    assert lignes["racine.md"]["titre"] == "Vrai titre"  # le « # » d'un bloc de code est ignoré
    assert lignes["racine.md"]["categorie"] == ""


def test_import_est_idempotent_et_detecte_les_modifications(db, dossier):
    documents.import_documents(dossier)
    r = documents.import_documents(dossier)
    assert (r.ajoutes, r.modifies, r.inchanges) == (0, 0, 3)
    (dossier / "rapports" / "bilan.md").write_text("# Bilan v2\n", encoding="utf-8")
    r = documents.import_documents(dossier)
    assert (r.ajoutes, r.modifies, r.inchanges) == (0, 1, 2)
    assert _lignes(db)["rapports/bilan.md"]["titre"] == "Bilan v2"


def test_import_categorie_imposee(db, dossier):
    documents.import_documents(dossier, categorie="perso")
    assert {d["categorie"] for d in _lignes(db).values()} == {"perso"}


def test_import_normalise_les_noms_de_fichiers_en_nfc(db, tmp_path):
    racine = tmp_path / "n"
    racine.mkdir()
    nom = unicodedata.normalize("NFD", "Coûts.md")
    (racine / nom).write_text("# x\n", encoding="utf-8")
    documents.import_documents(racine)
    assert set(_lignes(db)) == {unicodedata.normalize("NFC", "Coûts.md")}


def test_import_dossier_introuvable(db, tmp_path):
    with pytest.raises(FileNotFoundError):
        documents.import_documents(tmp_path / "absent")


def test_export_aller_retour_et_refus_d_ecraser(db, dossier, tmp_path):
    documents.import_documents(dossier)
    sortie = tmp_path / "sortie"
    assert documents.export_documents(sortie) == 3
    assert (sortie / "rapports" / "bilan.md").read_text(
        encoding="utf-8"
    ) == "# Bilan annuel\n\ncorps\n"
    with pytest.raises(FileExistsError):
        documents.export_documents(sortie)
    assert documents.export_documents(sortie, ecraser=True) == 3


def test_export_refuse_un_chemin_hors_du_dossier_sans_rien_ecrire(db, tmp_path):
    with sqlite3.connect(db) as c:
        c.execute("INSERT INTO documents (source, titre, contenu_md) VALUES ('ok.md', 'ok', 'a')")
        c.execute(
            "INSERT INTO documents (source, titre, contenu_md) VALUES ('../evil.md', 'x', 'b')"
        )
    sortie = tmp_path / "sortie"
    with pytest.raises(ValueError):
        documents.export_documents(sortie)
    assert not sortie.exists()
    assert not (tmp_path / "evil.md").exists()


def test_list_documents(db, dossier):
    documents.import_documents(dossier)
    liste = documents.list_documents()
    assert len(liste) == 3
    assert {"id", "categorie", "titre", "source", "taille", "updated_at"} <= set(liste[0])


def test_migration_006_cree_la_table_sur_une_base_existante(tmp_path, monkeypatch):
    path = tmp_path / "v5.db"
    monkeypatch.setattr(connection, "DB_PATH", path)
    connection.init_db()
    with sqlite3.connect(path) as c:
        c.execute("DROP TABLE documents")
        c.execute("PRAGMA user_version = 5")
    connection.init_db()
    with sqlite3.connect(path) as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == connection.latest_version() >= 6
        assert c.execute("SELECT count(*) FROM documents").fetchone()[0] == 0
