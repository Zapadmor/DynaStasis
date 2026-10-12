"""Requêtes sur les comptes, soldes, positions et transactions."""

from __future__ import annotations

import sqlite3


def soldes_courants(conn: sqlite3.Connection) -> list[dict]:
    """Dernier solde connu de chaque compte actif."""
    return [
        dict(r)
        for r in conn.execute(
            """SELECT c.source, c.type_compte, c.classe_actif, sc.solde
               FROM soldes_comptes sc JOIN comptes c ON sc.compte_id=c.id
               WHERE sc.date_snapshot=(
                   SELECT MAX(date_snapshot) FROM soldes_comptes s2 WHERE s2.compte_id=sc.compte_id
               ) AND c.actif=1"""
        )
    ]


def flags_investissement(conn: sqlite3.Connection, mois: str) -> dict | None:
    """Cases cochées à la main dans les semaines du mois (« AAAA-MM »)."""
    row = conn.execute(
        """SELECT SUM(investissement_pea) pea,
                  SUM(av_fonds_euros)     av_fe,
                  SUM(av_uc_diversifies)  av_uc
           FROM semaines_audit WHERE week_start LIKE ?""",
        (f"{mois}%",),
    ).fetchone()
    return dict(row) if row else None


def maj_flags_investissement(
    conn: sqlite3.Connection, week_id: int, pea: bool, av_fe: bool, av_uc: bool
) -> None:
    conn.execute(
        """UPDATE semaines_audit
           SET investissement_pea=?, av_fonds_euros=?, av_uc_diversifies=?,
               updated_at=datetime('now')
           WHERE id=?""",
        (int(pea), int(av_fe), int(av_uc), week_id),
    )


def transactions_epargne(conn: sqlite3.Connection, mois: str) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            """SELECT libelle, montant FROM transactions
               WHERE date_op LIKE ? AND categorie='epargne_investissement'""",
            (f"{mois}%",),
        )
    ]


def nb_comptes(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM comptes").fetchone()[0]


def inserer_comptes(conn: sqlite3.Connection, comptes: list[tuple]) -> None:
    conn.executemany(
        "INSERT INTO comptes (source, type_compte, libelle, classe_actif) VALUES (?,?,?,?)",
        comptes,
    )


def comptes_actifs(conn: sqlite3.Connection) -> list[dict]:
    """Comptes actifs avec la date de leur dernier solde (le plus récent d'abord)."""
    return [
        dict(r)
        for r in conn.execute(
            "SELECT c.id, c.source, c.type_compte, c.libelle, c.classe_actif, "
            "MAX(sc.date_snapshot) AS last_snap "
            "FROM comptes c "
            "LEFT JOIN soldes_comptes sc ON sc.compte_id = c.id "
            "WHERE c.actif = 1 "
            "GROUP BY c.id "
            "ORDER BY c.source, c.type_compte, last_snap DESC"
        )
    ]


def dernier_solde(conn: sqlite3.Connection, compte_id: int) -> float | None:
    row = conn.execute(
        "SELECT solde FROM soldes_comptes WHERE compte_id=? ORDER BY date_snapshot DESC LIMIT 1",
        (compte_id,),
    ).fetchone()
    return float(row["solde"]) if row else None


def enregistrer_solde(
    conn: sqlite3.Connection, compte_id: int, solde: float, date_snapshot: str
) -> None:
    conn.execute(
        """INSERT INTO soldes_comptes (compte_id, date_snapshot, solde)
           VALUES (?, ?, ?)
           ON CONFLICT(compte_id, date_snapshot) DO UPDATE SET solde=excluded.solde""",
        (compte_id, date_snapshot, solde),
    )


def positions_recentes(conn: sqlite3.Connection, compte_id: int) -> list[dict]:
    """Positions du dernier relevé d'un compte d'investissement."""
    return [
        dict(r)
        for r in conn.execute(
            """SELECT * FROM positions_investissement
               WHERE compte_id=? AND date_snapshot=(
                   SELECT MAX(date_snapshot) FROM positions_investissement p2
                   WHERE p2.compte_id=?
               )
               ORDER BY support""",
            (compte_id, compte_id),
        )
    ]


def total_positions(conn: sqlite3.Connection, compte_id: int, date_snapshot: str) -> float:
    return conn.execute(
        "SELECT COALESCE(SUM(valeur),0) FROM positions_investissement "
        "WHERE compte_id=? AND date_snapshot=?",
        (compte_id, date_snapshot),
    ).fetchone()[0]


def enregistrer_position(
    conn: sqlite3.Connection,
    date_snapshot: str,
    compte_id: int,
    support: str,
    nb_parts: float | None,
    cotation: float | None,
    valeur: float,
    plus_value: float | None,
    perf_ytd: str | None,
    categorie: str | None,
    frais_pct: float | None,
) -> None:
    conn.execute(
        """INSERT INTO positions_investissement
           (date_snapshot, compte_id, support, nb_parts, cotation, valeur,
            plus_value, perf_ytd, categorie, frais_pct)
           VALUES (?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(date_snapshot, compte_id, support) DO UPDATE SET
               nb_parts=excluded.nb_parts, cotation=excluded.cotation,
               valeur=excluded.valeur, plus_value=excluded.plus_value,
               perf_ytd=excluded.perf_ytd, categorie=excluded.categorie,
               frais_pct=excluded.frais_pct""",
        (
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
        ),
    )
