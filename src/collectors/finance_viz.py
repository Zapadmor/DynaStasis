"""
Générateur Sankey mensuel + tableau de bord financier.

Lit data/budget.yaml (budget théorique) et data/inbox/*/soldes.yaml (soldes réels).
Produit data/inbox/finance_dashboard.html — ouvrir dans un navigateur.

Usage :
    python3 -m core.finance_viz
"""

from __future__ import annotations

import sys
from pathlib import Path

from src.core.tz import today_local

_SRC_DIR = Path(__file__).resolve().parents[1]  # src/
ROOT_DIR = Path(__file__).resolve().parents[2]  # project root
for _p in [str(ROOT_DIR), str(_SRC_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    import yaml
except ImportError:
    raise SystemExit("pyyaml manquant — pip install pyyaml") from None

try:
    import plotly.graph_objects as go
except ImportError:
    raise SystemExit("plotly manquant — pip install plotly") from None

from src.styles import (
    HTML as _HTML,
)
from src.styles import (
    SANKEY_LINK_ALPHA as _LINK_ALPHA,
)
from src.styles import (
    SANKEY_NODE_COLORS as _COL,
)
from src.styles import (
    TRANSPARENT,
    TREEMAP_COLORS,
    WHITE,
)

BUDGET_FILE = ROOT_DIR / "data" / "budget.yaml"
OUTPUT = ROOT_DIR / "data" / "inbox" / "finance_dashboard.html"


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_soldes() -> dict:
    """Soldes réels — soldes.yaml de chaque source + Linxea XLSX (via finance_collector)."""
    inbox = ROOT_DIR / "data" / "inbox"
    cmb = _load_yaml(inbox / "cmb" / "soldes.yaml")
    fortuneo = _load_yaml(inbox / "fortuneo" / "soldes.yaml")
    revolut = _load_yaml(inbox / "revolut" / "soldes.yaml")

    cmb_cptes = cmb.get("comptes", {})
    rev_cptes = revolut.get("comptes", {})

    try:
        import warnings

        from core.finance_collector import load_linxea as _lx

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            linxea = _lx()
        lignes = linxea.get("lignes", [])
        linxea_date = linxea.get("date", "?")
    except Exception:
        lignes = []
        linxea_date = "?"

    linxea_fe = sum(
        ligne["valeur"] for ligne in lignes if "euros" in ligne.get("support", "").lower()
    )
    linxea_uc = sum(
        ligne["valeur"] for ligne in lignes if "euros" not in ligne.get("support", "").lower()
    )

    return {
        "date": cmb.get("date", "?"),
        "linxea_date": linxea_date,
        # CMB
        "cmb_cheques": cmb_cptes.get("cheques", {}).get("solde", 0.0),
        "cmb_lj": cmb_cptes.get("livret_jeune", {}).get("solde", 0.0),
        "cmb_lep": cmb_cptes.get("lep", {}).get("solde", 0.0),
        # Revolut
        "rev_cheques": rev_cptes.get("cheques", {}).get("solde", 0.0),
        "rev_epargne": rev_cptes.get("épargne", {}).get("solde", 0.0),
        "rev_pocket": rev_cptes.get("pocket", {}).get("solde", 0.0),
        # Fortuneo
        "fortuneo_pea": fortuneo.get("pea", {}).get("valeur_liquidative", 0.0),
        # Linxea
        "linxea_uc": linxea_uc,
        "linxea_fe": linxea_fe,
    }


# ── Construction du Sankey ─────────────────────────────────────────────────────


def _build_sankey(budget: dict) -> go.Figure:
    revenus = budget["revenus"]
    depenses = budget["depenses"]

    total_rev = sum(r["montant"] for r in revenus)

    # Nœuds
    labels = []
    colors = []

    def _add(label: str, color: str) -> int:
        labels.append(label)
        colors.append(color)
        return len(labels) - 1

    # Sources revenus
    rev_ids = [_add(f"{r['nom']}<br>{r['montant']:.2f} €", _COL["revenus"]) for r in revenus]

    # Nœud budget central
    budget_id = _add(f"Budget<br>{total_rev:.2f} €", _COL["budget"])

    # Catégories de dépenses
    cat_map = {
        "logement": (_COL["logement"], "Logement"),
        "vie_quotidienne": (_COL["vie"], "Vie quotidienne"),
        "abonnements": (_COL["abos"], "Abonnements"),
        "transports": (_COL["transports"], "Transports"),
        "investissements": (_COL["invest"], "Investissements"),
    }
    cat_ids: dict[str, int] = {}
    cat_totals: dict[str, float] = {}

    for key, (col, label) in cat_map.items():
        bloc = depenses.get(key, {})
        total = sum(p["montant"] for p in bloc.get("postes", []))
        cat_totals[key] = total
        cat_ids[key] = _add(f"{label}<br>{total:.2f} €", col)

    # Sous-nœuds investissements
    invest_postes = depenses.get("investissements", {}).get("postes", [])
    invest_sub_ids = []
    for p in invest_postes:
        if "PEA" in p["nom"]:
            invest_sub_ids.append(_add(f"PEA Fortuneo<br>{p['montant']:.2f} €", _COL["pea"]))
        elif "Fonds euros" in p["nom"]:
            invest_sub_ids.append(_add(f"AV — Fonds euros<br>{p['montant']:.2f} €", _COL["av_fe"]))
        elif "UC" in p["nom"]:
            invest_sub_ids.append(
                _add(f"AV — UC diversifiés<br>{p['montant']:.2f} €", _COL["av_uc"])
            )

    # Liens
    sources, targets, values, link_colors = [], [], [], []

    def _link(s: int, t: int, v: float, cat: str = "default") -> None:
        sources.append(s)
        targets.append(t)
        values.append(v)
        link_colors.append(_LINK_ALPHA.get(cat, _LINK_ALPHA["default"]))

    # Revenus → Budget
    for i, r in enumerate(revenus):
        _link(rev_ids[i], budget_id, r["montant"], "revenus")

    # Budget → Catégories
    _cat_alpha = {
        "logement": "logement",
        "vie_quotidienne": "vie",
        "abonnements": "abos",
        "transports": "transports",
        "investissements": "invest",
    }
    for key, cat_id in cat_ids.items():
        _link(budget_id, cat_id, cat_totals[key], _cat_alpha.get(key, "default"))

    # Investissements → Sous-postes
    invest_id = cat_ids["investissements"]
    for i, p in enumerate(invest_postes):
        if i < len(invest_sub_ids):
            _link(invest_id, invest_sub_ids[i], p["montant"], "invest")

    fig = go.Figure(
        go.Sankey(
            arrangement="snap",
            node=dict(
                pad=18,
                thickness=22,
                line=dict(color="white", width=0.5),
                label=labels,
                color=colors,
                hovertemplate="%{label}<extra></extra>",
            ),
            link=dict(
                source=sources,
                target=targets,
                value=values,
                color=link_colors,
                hovertemplate="%{source.label} → %{target.label}<br>%{value:.2f} €<extra></extra>",
            ),
        )
    )
    fig.update_layout(
        title=dict(
            text=f"Flux budgétaire mensuel — {budget.get('mois_reference', '')}",
            font=dict(size=16, family="Satoshi, sans-serif"),
            x=0.01,
        ),
        font=dict(size=12, family="Satoshi, sans-serif"),
        paper_bgcolor=TRANSPARENT,
        height=520,
        margin=dict(l=20, r=20, t=60, b=20),
    )
    return fig


# ── Treemap patrimonial ───────────────────────────────────────────────────────

_TREEMAP_CATS: dict[str, dict] = {
    "Liquidités": {
        "color": TREEMAP_COLORS["Liquidités"],
        "keys": ["cmb_cheques", "rev_cheques", "rev_pocket"],
        "labels": ["CMB Chèques", "Revolut Personnel", "Revolut Pockets"],
    },
    "Livrets": {
        "color": TREEMAP_COLORS["Livrets"],
        "keys": ["cmb_lj", "cmb_lep", "rev_epargne"],
        "labels": ["CMB Livret Jeune", "CMB LEP", "Revolut Épargne"],
    },
    "Actions": {
        "color": TREEMAP_COLORS["Actions"],
        "keys": ["fortuneo_pea", "linxea_uc"],
        "labels": ["PEA Fortuneo", "AV Linxea UC"],
    },
    "Fonds euros": {
        "color": TREEMAP_COLORS["Fonds euros"],
        "keys": ["linxea_fe"],
        "labels": ["AV Linxea Fonds euros"],
    },
    "Immobilier": {
        "color": TREEMAP_COLORS["Immobilier"],
        "keys": [],
        "labels": [],
    },
}


def _build_treemap(soldes: dict) -> go.Figure:
    """Treemap du patrimoine groupé par classe d'actifs."""
    labels: list[str] = ["Patrimoine"]
    parents: list[str] = [""]
    values: list[float] = [0.0]
    colors: list[str] = [TREEMAP_COLORS["root"]]
    customdata: list[str] = [""]

    total = 0.0
    for cat_name, cat in _TREEMAP_CATS.items():
        items = [
            (lbl, soldes.get(k, 0.0)) for k, lbl in zip(cat["keys"], cat["labels"], strict=False)
        ]
        cat_total = sum(v for _, v in items)
        if cat_total == 0.0:
            continue
        total += cat_total
        labels.append(cat_name)
        parents.append("Patrimoine")
        values.append(cat_total)
        colors.append(cat["color"])
        customdata.append(f"{cat_total:,.0f} €")
        for lbl, val in items:
            if val == 0.0:
                continue
            labels.append(lbl)
            parents.append(cat_name)
            values.append(val)
            colors.append(cat["color"])
            customdata.append(f"{val:,.0f} €")

    values[0] = total

    fig = go.Figure(
        go.Treemap(
            labels=labels,
            parents=parents,
            values=values,
            branchvalues="total",
            marker=dict(colors=colors, line=dict(width=3, color=TREEMAP_COLORS["root"])),
            customdata=customdata,
            texttemplate=(
                "<b>%{label}</b><br>"
                "%{customdata}<br>"
                "<span style='font-size:11px;opacity:.8'>%{percentRoot:.1%}</span>"
            ),
            hovertemplate=("<b>%{label}</b><br>%{customdata}<br>%{percentRoot:.1%}<extra></extra>"),
            textfont=dict(size=13, family="Inter, sans-serif", color="white"),
            textposition="middle center",
            root_color=TREEMAP_COLORS["root"],
            maxdepth=2,
        )
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor=TRANSPARENT,
        height=380,
    )
    return fig


# ── HTML complet ───────────────────────────────────────────────────────────────


def _build_html(budget: dict, fig_sankey: go.Figure, fig_treemap: go.Figure, soldes: dict) -> str:
    sankey_div = fig_sankey.to_html(full_html=False, include_plotlyjs=False, div_id="sankey")
    treemap_div = fig_treemap.to_html(full_html=False, include_plotlyjs=False, div_id="treemap")

    revenus = budget["revenus"]
    depenses = budget["depenses"]
    total_rev = sum(r["montant"] for r in revenus)

    # Calculs soldes
    net_worth = (
        soldes["cmb_cheques"]
        + soldes["cmb_lj"]
        + soldes["cmb_lep"]
        + soldes["rev_cheques"]
        + soldes["rev_epargne"]
        + soldes["rev_pocket"]
        + soldes["fortuneo_pea"]
        + soldes["linxea_uc"]
        + soldes["linxea_fe"]
    )
    pea_note = soldes["fortuneo_pea"] == 0

    # Tuiles soldes — helper pour générer une tuile
    def _tile(label: str, val: float, note: str = "", accent: str = "") -> str:
        accent_style = f"border-left: 3px solid {accent};" if accent else ""
        note_html = f'<div class="solde-note">{note}</div>' if note else ""
        return (
            f'<div class="solde-item" style="{accent_style}">'
            f'<div class="solde-label">{label}</div>'
            f'<div class="solde-val">{val:,.2f} €</div>'
            f"{note_html}</div>"
        )

    tiles = (
        _tile("CMB Chèques", soldes["cmb_cheques"], accent=TREEMAP_COLORS["Liquidités"])
        + _tile("CMB Livret Jeune", soldes["cmb_lj"], accent=TREEMAP_COLORS["Livrets"])
        + _tile("CMB LEP", soldes["cmb_lep"], accent=TREEMAP_COLORS["Livrets"])
        + _tile("Revolut Personnel", soldes["rev_cheques"], accent=TREEMAP_COLORS["Liquidités"])
        + _tile("Revolut Épargne", soldes["rev_epargne"], accent=TREEMAP_COLORS["Livrets"])
        + _tile("Revolut Pockets", soldes["rev_pocket"], accent=TREEMAP_COLORS["Liquidités"])
        + _tile(
            "PEA Fortuneo",
            soldes["fortuneo_pea"],
            note="À renseigner dans fortuneo/soldes.yaml" if pea_note else "",
            accent=TREEMAP_COLORS["Actions"],
        )
        + _tile("AV Linxea UC", soldes["linxea_uc"], accent=TREEMAP_COLORS["Actions"])
        + _tile("AV Linxea Fonds euros", soldes["linxea_fe"], accent=TREEMAP_COLORS["Fonds euros"])
    )

    return (
        f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Finance Dashboard — {budget.get("mois_reference", "")}</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>
<style>
  :root {{
    --bg:         {_HTML["bg"]};
    --card:       {_HTML["card"]};
    --text:       {_HTML["text"]};
    --muted:      {_HTML["text_muted"]};
    --border:     {_HTML["border"]};
    --item-bg:    {_HTML["item_bg"]};
    --total-bg:   {_HTML["total_bg"]};
    --accent:     {_HTML["accent"]};
    --pct:        {_HTML["pct"]};
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: Satoshi, system-ui, sans-serif; background: var(--bg); color: var(--text); padding: 28px 20px; max-width: 1100px; margin: 0 auto; }}
  h1   {{ font-size: 1.4rem; font-weight: 700; margin-bottom: 4px; letter-spacing: -.02em; }}
  h2   {{ font-size: .72rem; font-weight: 600; color: var(--muted); margin: 0 0 14px; text-transform: uppercase; letter-spacing: .08em; }}
  .card {{ background: var(--card); border-radius: 16px; padding: 22px 26px; margin-bottom: 14px; box-shadow: 0 1px 3px rgba(0,0,0,.06), 0 4px 16px rgba(0,0,0,.04); }}
  .subtitle {{ color: var(--pct); font-size: .78rem; margin-bottom: 16px; }}

  /* Soldes */
  .soldes-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 10px; }}
  .solde-item  {{ border-radius: 10px; padding: 14px 16px; background: var(--item-bg); border: 1px solid var(--border); }}
  .solde-label {{ font-size: .72rem; color: var(--muted); font-weight: 500; margin-bottom: 4px; text-transform: uppercase; letter-spacing: .05em; }}
  .solde-val   {{ font-size: 1.2rem; font-weight: 700; color: var(--text); }}
  .solde-note  {{ font-size: .68rem; color: var(--accent); margin-top: 4px; font-weight: 500; }}
  .total-row   {{ grid-column: 1 / -1; background: var(--total-bg); border: none; }}
  .total-row .solde-label {{ color: rgba(255,255,255,.5); }}
  .total-row .solde-val   {{ color: {WHITE}; font-size: 1.4rem; }}

  /* Budget table */
  table {{ width: 100%; border-collapse: collapse; font-size: .88rem; }}
  th    {{ text-align: left; padding: 8px 10px; color: var(--muted); font-weight: 500; font-size: .72rem; text-transform: uppercase; letter-spacing: .05em; border-bottom: 1px solid var(--border); }}
  td    {{ padding: 10px 10px; border-bottom: 1px solid var(--border); }}
  td:first-child {{ font-weight: 500; }}
  tr:last-child td {{ border-bottom: none; font-weight: 700; background: var(--item-bg); border-radius: 6px; }}
  .right {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .pct   {{ color: var(--pct); font-size: .82rem; }}

</style>
</head>
<body>

<div style="display:flex; align-items:baseline; justify-content:space-between; flex-wrap:wrap; gap:8px; margin-bottom:4px;">
  <h1>Finance Dashboard</h1>
</div>
<p class="subtitle">Généré le {today_local().isoformat()} — mois de référence : {budget.get("mois_reference", "")}</p>

<!-- Treemap patrimoine -->
<div class="card">
  <h2>Répartition patrimoniale</h2>
  <p class="subtitle">Par classe d'actifs — cliquer pour détailler · modifier via <code>data/inbox/*/soldes.yaml</code></p>
  {treemap_div}
</div>

<!-- Soldes réels -->
<div class="card">
  <h2>Comptes &amp; soldes</h2>
  <p class="subtitle">CMB au {soldes["date"]} · Linxea au {soldes["linxea_date"]} · Revolut en temps réel</p>
  <div class="soldes-grid">
    {tiles}
    <div class="solde-item total-row">
      <div class="solde-label">Net Worth total</div>
      <div class="solde-val">{net_worth:,.2f} €</div>
    </div>
  </div>
</div>

<!-- Sankey -->
<div class="card">
  <h2>Flux budgétaire mensuel</h2>
  <p class="subtitle">Budget théorique — modifier via <code>data/budget.yaml</code></p>
  {sankey_div}
</div>

<!-- Tableau budget -->
<div class="card">
  <h2>Répartition budget mensuel</h2>
  <table>
    <thead>
      <tr><th>Catégorie</th><th class="right">Montant</th><th class="right pct">% revenus</th></tr>
    </thead>
    <tbody>
"""
        + "".join(
            f"<tr><td>{bloc.get('emoji', '')} {bloc.get('label', '')}</td>"
            f"<td class='right'>{sum(p['montant'] for p in bloc.get('postes', [])):.2f} €</td>"
            f"<td class='right pct'>{sum(p['montant'] for p in bloc.get('postes', [])) / total_rev * 100:.1f} %</td></tr>"
            for bloc in depenses.values()
        )
        + f"""
      <tr><td><strong>Total</strong></td><td class="right"><strong>{total_rev:.2f} €</strong></td><td class="right pct"><strong>100 %</strong></td></tr>
    </tbody>
  </table>
</div>

</body>
</html>"""
    )


# ── Main ───────────────────────────────────────────────────────────────────────


def main() -> int:
    budget = _load_yaml(BUDGET_FILE)
    if not budget:
        raise SystemExit("data/budget.yaml introuvable ou vide.")

    soldes = _load_soldes()
    fig_sankey = _build_sankey(budget)
    fig_treemap = _build_treemap(soldes)
    html = _build_html(budget, fig_sankey, fig_treemap, soldes)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"Dashboard généré : {OUTPUT}")
    print("Ouvrir dans le navigateur : http://localhost:8090/finance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
