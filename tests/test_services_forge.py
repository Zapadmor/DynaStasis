"""Services Forge : finance (classement des soldes, versements, imports) et objectifs."""

from __future__ import annotations

import pytest

from src.services import finance, objectifs

# ── Finance : calculs purs ──────────────────────────────────────────────────────────────────────


def _l(source, type_compte, solde, classe=""):
    return {"source": source, "type_compte": type_compte, "classe_actif": classe, "solde": solde}


def test_classer_soldes_repartit_par_source_et_type():
    s = finance.classer_soldes(
        [
            _l("CMB", "courant", 100),
            _l("cmb", "lep", 50),
            _l("cmb", "livret_jeune", 25),
            _l("revolut", "epargne", 10),
            _l("revolut", "pocket", 5),
            _l("revolut", "courant", 1),
            _l("fortuneo", "pea", 200),
            _l("fortuneo", "especes_pea", 20),
            _l("linxea", "fonds_euros", 300, "fonds_euros"),
            _l("linxea", "uc_diversifies", 400, "actions"),
            _l("autre", "x", 999),
            _l(None, None, None),
        ]
    )
    assert s == {
        "cmb_cheques": 100,
        "cmb_lep": 50,
        "cmb_lj": 25,
        "rev_epargne": 10,
        "rev_pocket": 5,
        "rev_cheques": 1,
        "fortuneo_pea": 220,
        "linxea_fe": 300,
        "linxea_uc": 400,
    }
    assert set(s) == set(finance.ENVELOPPES)


def test_analyser_versements_priorite_aux_cases_puis_transactions():
    vide = finance.analyser_versements(None, [])
    assert vide["source"] == "—" and not vide["pea"]

    flags = {"pea": 1, "av_fe": 0, "av_uc": None}
    r = finance.analyser_versements(flags, [])
    assert (r["pea"], r["av_fe"], r["source"]) == (True, False, "semaines_audit")

    txs = [
        {"libelle": "Virement Fortuneo", "montant": -150.0},
        {"libelle": "linxea avenir", "montant": -50.0},
        {"libelle": "Courses", "montant": -20.0},
    ]
    r = finance.analyser_versements(None, txs)
    assert (r["pea"], r["av_fe"]) == (True, True)
    assert (r["pea_montant"], r["av_montant"], r["source"]) == (150.0, 50.0, "transactions")


def test_dedupliquer_comptes_garde_le_premier_par_paire():
    lignes = [
        {"id": 2, "source": "cmb", "type_compte": "lep", "classe_actif": "livrets"},
        {"id": 1, "source": "cmb", "type_compte": "lep", "classe_actif": "livrets"},
        {"id": 3, "source": "cmb", "type_compte": "courant", "classe_actif": "liquidites"},
    ]
    # un seul compte par paire (le premier de la liste), trié par classe d'actif
    assert [c["id"] for c in finance.dedupliquer_comptes(lignes)] == [3, 2]


def test_parser_revolut_csv_garde_le_dernier_solde_par_produit():
    csv_txt = (
        "Product,State,Currency,Balance,Completed Date\n"
        "Current,COMPLETED,EUR,10.5,2026-01-01 10:00\n"
        "Current,COMPLETED,EUR,12.0,2026-01-02 10:00\n"
        "Current,PENDING,EUR,99,2026-01-03 10:00\n"
        "Savings,COMPLETED,EUR,50,2026-01-01 10:00\n"
        "Current,COMPLETED,USD,7,2026-01-04 10:00\n"
        "Current,COMPLETED,EUR,abc,2026-01-05 10:00\n"
    )
    assert finance.parser_revolut_csv(csv_txt) == {"Current": 12.0, "Savings": 50.0}


def test_parser_linxea_xlsx():
    import io

    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([f"h{i}" for i in range(16)])
    ligne = [None] * 16
    ligne[5], ligne[7], ligne[9], ligne[10], ligne[12], ligne[13], ligne[15] = (
        "Actions",
        "ETF Monde",
        2,
        50.0,
        100.0,
        5.0,
        "3 %",
    )
    ws.append(ligne)
    ws.append([None] * 7 + ["Sans valeur"] + [None] * 8)
    buf = io.BytesIO()
    wb.save(buf)
    (p,) = finance.parser_linxea_xlsx(buf.getvalue())
    assert (p["support"], p["valeur"], p["plus_value"], p["categorie"]) == (
        "ETF Monde",
        100.0,
        5.0,
        "Actions",
    )


# ── Finance : base ──────────────────────────────────────────────────────────────────────────────


def test_comptes_par_defaut_puis_soldes_et_positions(db):
    assert finance.comptes() == []
    finance.assurer_comptes()
    finance.assurer_comptes()  # idempotent
    cs = finance.comptes()
    assert len(cs) == len(finance.COMPTES_PAR_DEFAUT)

    cid = next(c["id"] for c in cs if c["type_compte"] == "pea")
    assert finance.solde_actuel(cid) is None
    finance.enregistrer_solde(cid, 10.0, "2026-03-01")
    finance.enregistrer_solde(cid, 12.0, "2026-03-01")  # même date : mise à jour
    finance.enregistrer_solde(cid, 15.0, "2026-03-05")
    assert finance.solde_actuel(cid) == 15.0

    finance.enregistrer_position("2026-03-05", cid, "ETF A", 2, 10.0, 20.0, 1.0, "2 %", "Actions")
    finance.enregistrer_position("2026-03-05", cid, "ETF A", 3, 10.0, 30.0, 1.0, "2 %", "Actions")
    finance.enregistrer_position("2026-03-05", cid, "ETF B", 1, 5.0, 5.0, None, None, None)
    assert [p["support"] for p in finance.positions_compte(cid)] == ["ETF A", "ETF B"]
    assert finance.total_positions(cid, "2026-03-05") == 35.0

    soldes = finance.soldes_par_enveloppe()
    assert soldes["fortuneo_pea"] == 15.0


def test_versements_coches_a_la_main(db):
    finance.enregistrer_versements("2026-03-04", True, False, True)
    r = finance.verifier_versements("2026-03")
    assert (r["pea"], r["av_fe"], r["av_uc"], r["source"]) == (True, False, True, "semaines_audit")


# ── Objectifs ───────────────────────────────────────────────────────────────────────────────────


def test_cycle_de_vie_objectif_et_taches(db):
    assert objectifs.charger_objectifs() == ([], None)
    objectifs.creer_objectif("Titre", "FORGE", "", "", 2)
    (obj,) = objectifs.charger_objectifs()[0]
    assert obj["date_cible"] is None and obj["description"] is None

    objectifs.creer_tache(obj["id"], "t1", 1, "")
    objectifs.creer_tache(obj["id"], "t2", 2, "2026-12-01")
    t1, t2 = objectifs.charger_taches(obj["id"])
    assert (t1["titre"], t1["statut"]) == ("t1", "todo")

    objectifs.cocher_tache(t1["id"], True)
    assert objectifs.charger_taches(obj["id"])[0]["statut"] == "fait"
    objectifs.cocher_tache(t1["id"], False)
    assert objectifs.charger_taches(obj["id"])[0]["completed_at"] is None

    objectifs.supprimer_tache(t2["id"])
    assert [t["titre"] for t in objectifs.charger_taches(obj["id"])] == ["t1"]

    objectifs.archiver_objectif(obj["id"])
    assert objectifs.charger_objectifs()[0] == []


@pytest.mark.parametrize("fn", [objectifs.charger_taches])
def test_lectures_tolerantes_sans_table(tmp_path, monkeypatch, fn):
    from src.database import connection

    monkeypatch.setattr(connection, "DB_PATH", tmp_path / "vide.db")
    assert fn(1) == []
