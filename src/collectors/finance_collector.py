"""
Collecteur de données financières — Phase 3 Finance.

Sources :
  CMB       CSV exports + soldes.yaml  → data/inbox/cmb/
  Fortuneo  CSV export  + soldes.yaml  → data/inbox/fortuneo/
  Revolut   CSV export                 → data/inbox/revolut/
  Linxea    XLSX export                → data/inbox/linxea/

Usage :
    python3 -m core.finance_collector
    python3 -m core.finance_collector --month 2026-05
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, datetime
from pathlib import Path
from typing import NamedTuple

from src.core.tz import today_local

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    import yaml
except ImportError:
    raise SystemExit("pyyaml manquant — pip install pyyaml") from None

try:
    import openpyxl
except ImportError:
    raise SystemExit("openpyxl manquant — pip install openpyxl") from None

INBOX = ROOT_DIR / "data" / "inbox"
CATEGORIES_FILE = ROOT_DIR / "data" / "categories.yaml"

_SEP = "─" * 54
_DOUBLE = "═" * 54


# ── Types ──────────────────────────────────────────────────────────────────────


class Transaction(NamedTuple):
    date_op: date
    libelle: str
    montant: float  # positif = crédit, négatif = débit
    source: str  # "cmb", "revolut", "fortuneo"
    categorie: str = "non_categorise"


# ── Catégorisation ─────────────────────────────────────────────────────────────


def _load_categories() -> dict[str, list[str]]:
    if not CATEGORIES_FILE.exists():
        return {}
    with CATEGORIES_FILE.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _categorise(libelle: str, rules: dict[str, list[str]]) -> str:
    lib_up = libelle.upper()
    for categorie, mots in rules.items():
        for mot in mots:
            if mot.upper() in lib_up:
                return categorie
    return "non_categorise"


# ── Helpers ────────────────────────────────────────────────────────────────────


def _parse_float_fr(s: str) -> float:
    """Parse '1 234,56' ou '1234.56' → float."""
    s = str(s).strip().strip('"').replace("\xa0", "").replace(" ", "")
    if not s:
        return 0.0
    return float(s.replace(",", "."))


def _parse_date_fr(s: str) -> date:
    s = str(s).strip().strip('"')
    return datetime.strptime(s, "%d/%m/%Y").date()


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ── Parseur CMB ────────────────────────────────────────────────────────────────


def _parse_cmb_csv(path: Path, rules: dict) -> list[Transaction]:
    txs: list[Transaction] = []
    with path.open(encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f, delimiter=";", quotechar='"')
        next(reader, None)
        for row in reader:
            if len(row) < 5:
                continue
            try:
                d = _parse_date_fr(row[0])
                lib = row[2].strip().strip('"')
                debit = _parse_float_fr(row[3])
                credit = _parse_float_fr(row[4])
                montant = credit - debit
            except (ValueError, IndexError):
                continue
            txs.append(Transaction(d, lib, montant, "cmb", _categorise(lib, rules)))
    return txs


def load_cmb(month: str | None = None) -> dict:
    rules = _load_categories()
    cmb_dir = INBOX / "cmb"
    soldes_raw = _load_yaml(cmb_dir / "soldes.yaml")

    soldes = soldes_raw.get("comptes", {})
    soldes["_date"] = soldes_raw.get("date", "?")
    total = sum(v.get("solde", 0.0) for k, v in soldes.items() if not k.startswith("_"))

    all_txs: list[Transaction] = []
    for f in sorted(cmb_dir.glob("*.csv")):
        if f.name.startswith("EXEMPLE_"):
            continue
        all_txs.extend(_parse_cmb_csv(f, rules))

    # Déduplication
    seen: set[tuple] = set()
    unique: list[Transaction] = []
    for tx in all_txs:
        key = (tx.date_op, tx.libelle, tx.montant)
        if key not in seen:
            seen.add(key)
            unique.append(tx)
    unique.sort(key=lambda t: t.date_op, reverse=True)

    txs_mois = _filter_month(unique, month)
    return {"soldes": soldes, "total": total, "txs": unique, "txs_mois": txs_mois}


# ── Parseur Fortuneo ───────────────────────────────────────────────────────────


def _parse_fortuneo_csv(path: Path, rules: dict) -> list[Transaction]:
    txs: list[Transaction] = []
    with path.open(encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f, delimiter=";")
        next(reader, None)
        for row in reader:
            if len(row) < 5:
                continue
            try:
                d = _parse_date_fr(row[0])
                lib = row[2].strip()
                debit = _parse_float_fr(row[3])
                credit = _parse_float_fr(row[4])
                montant = credit - debit
            except (ValueError, IndexError):
                continue
            txs.append(Transaction(d, lib, montant, "fortuneo", _categorise(lib, rules)))
    return txs


def load_fortuneo(month: str | None = None) -> dict:
    rules = _load_categories()
    fort_dir = INBOX / "fortuneo"
    soldes_raw = _load_yaml(fort_dir / "soldes.yaml")
    pea = soldes_raw.get("pea", {})

    all_txs: list[Transaction] = []
    for f in sorted(fort_dir.glob("*.csv")):
        if f.name.startswith("EXEMPLE_"):
            continue
        all_txs.extend(_parse_fortuneo_csv(f, rules))
    all_txs.sort(key=lambda t: t.date_op, reverse=True)

    txs_mois = _filter_month(all_txs, month)
    return {
        "valeur_liquidative": pea.get("valeur_liquidative", 0.0),
        "versements_cumules": pea.get("versements_cumules", 0.0),
        "note": pea.get("note", ""),
        "date": soldes_raw.get("date", "?"),
        "txs": all_txs,
        "txs_mois": txs_mois,
    }


# ── Parseur Revolut ────────────────────────────────────────────────────────────

_REVOLUT_PRODUCTS_FR = {
    "Current": "Compte courant",
    "Deposit": "Compte d'épargne",
    "Savings": "Pockets",
}

_REVOLUT_CATS = {
    "revenus": ["Top-up by", "Payment from", "Salary"],
    "variables": ["Card Payment", "Google Pay"],
    "epargne_investissement": ["To EUR Compte d", "To pocket EUR", "To Savings"],
    "virements_internes_revolut": [
        "From pocket",
        "From Savings",
        "From EUR Compte",
        "Pocket Withdrawal",
    ],
}


def _categorise_revolut(tx_type: str, description: str) -> str:
    combo = f"{tx_type} {description}".upper()
    for cat, mots in _REVOLUT_CATS.items():
        for mot in mots:
            if mot.upper() in combo:
                return cat
    if tx_type == "Interest":
        return "revenus"
    if tx_type == "Fee":
        return "fixes"
    if tx_type in ("Card Payment",):
        return "variables"
    if tx_type == "Transfer":
        return "non_categorise"
    return "non_categorise"


def load_revolut(month: str | None = None) -> dict:
    rev_dir = INBOX / "revolut"
    all_txs: list[Transaction] = []
    balances_by_product: dict[str, tuple[float, str]] = {}  # product → (balance, date)

    for f in sorted(rev_dir.glob("*.csv")):
        if f.name.startswith("EXEMPLE_"):
            continue
        with f.open(encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh)
            rows = [r for r in reader if r.get("State") == "COMPLETED"]

        for row in rows:
            product = row.get("Product", "")
            try:
                d = datetime.strptime(row["Completed Date"][:10], "%Y-%m-%d").date()
                amount = float(row["Amount"])
                balance = float(row["Balance"])
                desc = row.get("Description", "").replace("&#39;", "'")
                tx_type = row.get("Type", "")
                currency = row.get("Currency", "EUR")
                if currency != "EUR":
                    continue
            except (ValueError, KeyError):
                continue

            cat = _categorise_revolut(tx_type, desc)

            # Transferts internes Revolut (entre produits) : on ne garde que le débit
            # depuis Current pour éviter le double comptage credit+débit
            is_internal = cat in ("epargne_investissement", "virements_internes_revolut")
            if is_internal and amount > 0:
                # C'est le côté "crédit" d'un virement interne → ignoré
                pass
            else:
                all_txs.append(Transaction(d, desc, amount, f"revolut:{product}", cat))

            # Garde la balance la plus récente par produit
            existing = balances_by_product.get(product)
            if existing is None or d >= datetime.strptime(existing[1], "%Y-%m-%d").date():
                balances_by_product[product] = (balance, d.isoformat())

    all_txs.sort(key=lambda t: t.date_op, reverse=True)
    txs_mois = _filter_month(all_txs, month)
    total = sum(b for b, _ in balances_by_product.values())

    return {
        "balances": balances_by_product,
        "total": total,
        "txs": all_txs,
        "txs_mois": txs_mois,
    }


# ── Parseur Linxea XLSX ────────────────────────────────────────────────────────


def load_linxea() -> dict:
    linxea_dir = INBOX / "linxea"
    xlsx_files = list(linxea_dir.glob("*.xlsx"))
    if not xlsx_files:
        return {"total": 0.0, "lignes": [], "date": "?"}

    xlsx = sorted(xlsx_files)[-1]  # le plus récent
    wb = openpyxl.load_workbook(xlsx, data_only=True)
    ws = wb.active

    lignes = []
    date_export = "?"
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            continue  # header
        if not any(row):
            continue
        categorie = str(row[5] or "")
        sous_cat = str(row[6] or "")
        nom_support = str(row[7] or "")
        nb_parts = float(row[9] or 0)
        cotation = float(row[10] or 0)
        date_cot = str(row[11] or "")
        valeur = float(row[12] or 0)
        pv = float(row[13] or 0)
        perf_ytd = str(row[15] or "")

        if date_cot and date_cot not in ("01/01/0001", ""):
            date_export = date_cot

        lignes.append(
            {
                "categorie": categorie,
                "sous_cat": sous_cat,
                "support": nom_support,
                "parts": nb_parts,
                "cotation": cotation,
                "valeur": valeur,
                "plus_value": pv,
                "perf_ytd": perf_ytd,
            }
        )

    total = sum(ligne["valeur"] for ligne in lignes)
    return {"total": total, "lignes": lignes, "date": date_export}


# ── Filtre mensuel ─────────────────────────────────────────────────────────────


def _filter_month(txs: list[Transaction], month: str | None) -> list[Transaction]:
    if month:
        y, m = int(month[:4]), int(month[5:7])
    else:
        today = today_local()
        y, m = today.year, today.month
    return [t for t in txs if t.date_op.year == y and t.date_op.month == m]


# ── Affichage ──────────────────────────────────────────────────────────────────

_CATS_FR = {
    "revenus": "Revenus",
    "fixes": "Dépenses fixes",
    "variables": "Dépenses variables",
    "epargne_investissement": "Épargne / Investissement",
    "virements_internes": "Virements internes (famille)",
    "virements_internes_revolut": "Virements Revolut → Pockets",
    "non_categorise": "Non catégorisé",
}


def _fmt(v: float, sign: bool = True) -> str:
    prefix = "+" if sign and v > 0 else ""
    return f"{prefix}{v:>10.2f} €"


def display_all(month: str | None = None) -> dict:
    mois_label = month or today_local().strftime("%Y-%m")
    cmb = load_cmb(month)
    fortuneo = load_fortuneo(month)
    revolut = load_revolut(month)
    linxea = load_linxea()

    # ── Net Worth ──────────────────────────────────────────────────────────────
    net_worth = cmb["total"] + fortuneo["valeur_liquidative"] + revolut["total"] + linxea["total"]

    print(f"\n{_DOUBLE}")
    print(f"  PATRIMOINE TOTAL — {mois_label}")
    print(_SEP)

    # CMB
    sol = cmb["soldes"]
    print(f"\n  CMB  (au {sol.get('_date', '?')})")
    for k, acc in sol.items():
        if k.startswith("_"):
            continue
        note = f"  ← {acc.get('note', '')}" if acc.get("note") else ""
        print(f"    {acc['nom']:<30} {acc.get('solde', 0):>9.2f} €{note}")
    print(f"    {'Total CMB':<30} {cmb['total']:>9.2f} €")

    # Revolut
    print(
        f"\n  Revolut  (au {list(revolut['balances'].values())[0][1] if revolut['balances'] else '?'})"
    )
    for prod, (bal, _) in revolut["balances"].items():
        label = _REVOLUT_PRODUCTS_FR.get(prod, prod)
        print(f"    {label:<30} {bal:>9.2f} €")
    print(f"    {'Total Revolut':<30} {revolut['total']:>9.2f} €")

    # Fortuneo PEA
    print(f"\n  PEA Fortuneo  (au {fortuneo['date']})")
    if fortuneo["valeur_liquidative"] == 0.0:
        print("    ⚠️  Valeur liquidative à renseigner dans fortuneo/soldes.yaml")
    else:
        print(f"    {'PEA — valeur liquidative':<30} {fortuneo['valeur_liquidative']:>9.2f} €")

    # Linxea AV
    print(f"\n  Linxea AV  (au {linxea['date']})")
    for ligne in linxea["lignes"]:
        print(
            f"    {ligne['support'][:36]:<36}  {ligne['valeur']:>7.2f} €  PV {ligne['plus_value']:+.2f} €  {ligne['perf_ytd']}"
        )
    print(f"    {'Total AV':<30} {linxea['total']:>9.2f} €")

    print(f"\n{_SEP}")
    print(f"  {'NET WORTH TOTAL':<30} {net_worth:>9.2f} €")
    print(_DOUBLE)

    # ── Flux du mois ───────────────────────────────────────────────────────────
    all_txs_mois = cmb["txs_mois"] + revolut["txs_mois"] + fortuneo["txs_mois"]
    if all_txs_mois:
        print(f"\n  FLUX — {mois_label}  ({len(all_txs_mois)} opérations)")
        print(_SEP)

        by_cat: dict[str, list[Transaction]] = {}
        for tx in all_txs_mois:
            by_cat.setdefault(tx.categorie, []).append(tx)

        totaux: dict[str, float] = {}
        for cat_key in [
            "revenus",
            "fixes",
            "variables",
            "epargne_investissement",
            "virements_internes",
            "virements_internes_revolut",
            "non_categorise",
        ]:
            txs_cat = by_cat.get(cat_key, [])
            if not txs_cat:
                continue
            total_cat = sum(t.montant for t in txs_cat)
            totaux[cat_key] = total_cat
            label = _CATS_FR.get(cat_key, cat_key)
            print(f"\n  {label}  {_fmt(total_cat)}")
            for tx in sorted(txs_cat, key=lambda t: abs(t.montant), reverse=True):
                src = tx.source.split(":")[0].upper()
                lib = tx.libelle[:34]
                print(f"    {tx.date_op}  [{src:<7}]  {lib:<34}  {_fmt(tx.montant)}")

        # Sorties réelles = tout sauf revenus et mouvements internes Revolut
        _internes = {"virements_internes_revolut", "epargne_investissement"}
        flux_entrant = totaux.get("revenus", 0.0)
        flux_sortant_reel = sum(v for k, v in totaux.items() if k not in {"revenus"} | _internes)
        flux_alloue = sum(totaux.get(k, 0.0) for k in _internes)
        print(f"\n{_SEP}")
        print(f"  Revenus                          {_fmt(flux_entrant)}")
        print(f"  Dépenses réelles                 {_fmt(flux_sortant_reel)}")
        print(f"  Allocations Revolut (internes)   {_fmt(flux_alloue)}")
        print(f"  Solde net (hors Revolut interne) {_fmt(flux_entrant + flux_sortant_reel)}")
        print(_DOUBLE)

    return {
        "net_worth": net_worth,
        "cmb_total": cmb["total"],
        "revolut_total": revolut["total"],
        "fortuneo_pea": fortuneo["valeur_liquidative"],
        "linxea_av": linxea["total"],
        "revenus_mois": sum(t.montant for t in all_txs_mois if t.categorie == "revenus"),
        "fixes_mois": sum(t.montant for t in all_txs_mois if t.categorie == "fixes"),
        "variables_mois": sum(t.montant for t in all_txs_mois if t.categorie == "variables"),
        "epargne_mois": sum(
            t.montant for t in all_txs_mois if t.categorie == "epargne_investissement"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Résumé financier complet depuis les exports.")
    parser.add_argument("--month", default=None, help="Mois YYYY-MM (défaut : mois en cours)")
    args = parser.parse_args()
    display_all(args.month)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
