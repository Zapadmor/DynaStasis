"""Finance : soldes par enveloppe, suivi des versements, comptes manuels, imports Revolut / Linxea."""

from __future__ import annotations

import csv
import io

from src.database.connection import db_session
from src.repositories import finance as repo
from src.services.semaines import get_or_create_week_id

ENVELOPPES = (
    "cmb_cheques",
    "cmb_lj",
    "cmb_lep",
    "rev_cheques",
    "rev_epargne",
    "rev_pocket",
    "fortuneo_pea",
    "linxea_uc",
    "linxea_fe",
)

COMPTES_PAR_DEFAUT = [
    ("cmb", "courant", "CMB Compte Chèques", "liquidites"),
    ("cmb", "livret_jeune", "CMB Livret Jeune", "livrets"),
    ("cmb", "lep", "CMB LEP", "livrets"),
    ("fortuneo", "especes_pea", "Fortuneo PEA — Espèces", "liquidites"),
    ("fortuneo", "pea", "Fortuneo PEA — ETF", "actions"),
    ("revolut", "courant", "Revolut Current", "liquidites"),
    ("revolut", "epargne", "Revolut Épargne", "livrets"),
    ("revolut", "pocket", "Revolut Pockets", "liquidites"),
    ("linxea", "fonds_euros", "Linxea AV — Fonds Euros", "fonds_euros"),
    ("linxea", "uc_diversifies", "Linxea AV — UC Diversifiés", "actions"),
]


# ── Calculs purs ────────────────────────────────────────────────────────────────────────────────


def classer_soldes(lignes: list[dict]) -> dict[str, float]:
    """Répartit les soldes des comptes dans les enveloppes du treemap (source + type de compte)."""
    s = dict.fromkeys(ENVELOPPES, 0.0)
    for r in lignes:
        source = (r["source"] or "").lower()
        tc = (r["type_compte"] or "").lower()
        classe = r["classe_actif"] or ""
        v = float(r["solde"] or 0.0)
        if "cmb" in source:
            if "courant" in tc:
                s["cmb_cheques"] += v
            elif "lep" in tc:
                s["cmb_lep"] += v
            else:
                s["cmb_lj"] += v
        elif "revolut" in source:
            if any(k in tc for k in ("epargne", "coffre", "vault")):
                s["rev_epargne"] += v
            elif "pocket" in tc:
                s["rev_pocket"] += v
            else:
                s["rev_cheques"] += v
        elif "fortuneo" in source:
            s["fortuneo_pea"] += v  # especes_pea + pea → enveloppe PEA
        elif "linxea" in source:
            if classe == "fonds_euros":
                s["linxea_fe"] += v
            else:
                s["linxea_uc"] += v
    return s


def analyser_versements(flags: dict | None, transactions: list[dict]) -> dict:
    """PEA / assurance-vie versés ce mois : cases cochées, sinon transactions d'épargne."""
    r = {
        "pea": False,
        "av_fe": False,
        "av_uc": False,
        "pea_montant": 0.0,
        "av_montant": 0.0,
        "source": "—",
    }
    if flags and any([flags["pea"], flags["av_fe"], flags["av_uc"]]):
        r.update(
            {
                "pea": bool(flags["pea"]),
                "av_fe": bool(flags["av_fe"]),
                "av_uc": bool(flags["av_uc"]),
                "source": "semaines_audit",
            }
        )
    for tx in transactions:
        lib = (tx["libelle"] or "").upper()
        m = abs(float(tx["montant"] or 0.0))
        if any(k in lib for k in ("FORTUNEO", "PEA", "ETF", "ISHARES")):
            r["pea"] = True
            r["pea_montant"] += m
            r["source"] = "transactions"
        if any(k in lib for k in ("LINXEA", "SURAVENIR", "ASSURANCE VIE")):
            r["av_fe"] = True
            r["av_montant"] += m
            r["source"] = "transactions"
    return r


def dedupliquer_comptes(lignes: list[dict]) -> list[dict]:
    """Un compte par (source, type_compte) : celui dont le solde est le plus récent."""
    vus: set[tuple] = set()
    uniques: list[dict] = []
    for r in lignes:
        cle = (r["source"], r["type_compte"])
        if cle not in vus:
            vus.add(cle)
            uniques.append(r)
    uniques.sort(key=lambda c: (c["classe_actif"], c["source"], c["type_compte"]))
    return uniques


def parser_revolut_csv(content: str) -> dict[str, float]:
    """Parse CSV Revolut et retourne {produit: solde_final}."""
    reader = csv.DictReader(io.StringIO(content))
    balances: dict[str, tuple[float, str]] = {}
    for row in reader:
        if row.get("State") != "COMPLETED":
            continue
        if row.get("Currency", "EUR") != "EUR":
            continue
        product = row.get("Product", "Current")
        try:
            balance = float(row["Balance"])
            completed = row.get("Completed Date", "")[:10]
        except (ValueError, KeyError):
            continue
        existing = balances.get(product)
        if existing is None or completed >= existing[1]:
            balances[product] = (balance, completed)
    return {prod: bal for prod, (bal, _) in balances.items()}


def parser_linxea_xlsx(content: bytes) -> list[dict]:
    """Parse XLSX Linxea et retourne les lignes de positions."""
    try:
        import openpyxl
    except ImportError:
        return []

    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    ws = wb.active
    lignes = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0 or not any(row):
            continue
        try:
            categorie = str(row[5] or "")
            support = str(row[7] or "")
            nb_parts = float(row[9] or 0)
            cotation = float(row[10] or 0)
            valeur = float(row[12] or 0)
            pv = float(row[13] or 0)
            perf_ytd = str(row[15] or "")
            if not support or valeur == 0:
                continue
            lignes.append(
                {
                    "categorie": categorie,
                    "support": support,
                    "nb_parts": nb_parts,
                    "cotation": cotation,
                    "valeur": valeur,
                    "plus_value": pv,
                    "perf_ytd": perf_ytd,
                }
            )
        except (ValueError, TypeError, IndexError):
            continue
    return lignes


# ── Lecture / écriture ──────────────────────────────────────────────────────────────────────────


def soldes_par_enveloppe() -> dict[str, float]:
    """Soldes du treemap ; tout à zéro si la base n'a pas encore les tables."""
    try:
        with db_session() as conn:
            lignes = repo.soldes_courants(conn)
    except Exception:
        return dict.fromkeys(ENVELOPPES, 0.0)
    return classer_soldes(lignes)


def verifier_versements(mois: str) -> dict:
    """Versements PEA / AV du mois (« AAAA-MM »)."""
    try:
        with db_session() as conn:
            flags = repo.flags_investissement(conn, mois)
            txs = repo.transactions_epargne(conn, mois)
    except Exception:
        return analyser_versements(None, [])
    return analyser_versements(flags, txs)


def enregistrer_versements(date_iso: str, pea: bool, av_fe: bool, av_uc: bool) -> None:
    """Coche à la main les versements dans la semaine de `date_iso`."""
    week_id = get_or_create_week_id(date_iso)
    with db_session() as conn:
        repo.maj_flags_investissement(conn, week_id, pea, av_fe, av_uc)


def assurer_comptes() -> None:
    """Crée les comptes par défaut si la table est vide."""
    try:
        with db_session() as conn:
            if repo.nb_comptes(conn) == 0:
                repo.inserer_comptes(conn, COMPTES_PAR_DEFAUT)
    except Exception:
        pass


def comptes() -> list[dict]:
    try:
        with db_session() as conn:
            lignes = repo.comptes_actifs(conn)
    except Exception:
        return []
    return dedupliquer_comptes(lignes)


def solde_actuel(compte_id: int) -> float | None:
    try:
        with db_session() as conn:
            return repo.dernier_solde(conn, compte_id)
    except Exception:
        return None


def enregistrer_solde(compte_id: int, solde: float, date_snapshot: str) -> None:
    with db_session() as conn:
        repo.enregistrer_solde(conn, compte_id, solde, date_snapshot)


def positions_compte(compte_id: int) -> list[dict]:
    try:
        with db_session() as conn:
            return repo.positions_recentes(conn, compte_id)
    except Exception:
        return []


def total_positions(compte_id: int, date_snapshot: str) -> float:
    with db_session() as conn:
        return repo.total_positions(conn, compte_id, date_snapshot)


def enregistrer_position(
    date_snapshot: str,
    compte_id: int,
    support: str,
    nb_parts: float | None,
    cotation: float | None,
    valeur: float,
    plus_value: float | None,
    perf_ytd: str | None,
    categorie: str | None,
    frais_pct: float | None = None,
) -> None:
    with db_session() as conn:
        repo.enregistrer_position(
            conn,
            date_snapshot,
            compte_id,
            support,
            nb_parts,
            cotation,
            valeur,
            plus_value,
            perf_ytd,
            categorie,
            frais_pct,
        )
