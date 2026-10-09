"""DynaStasie — source unique de vérité pour les couleurs.

Lit les sections [colors.*] de src/styles.toml.
Ne définir aucune valeur hex ou rgba ici : éditer uniquement styles.toml.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from src.core import user_config

_CFG_PATH = Path(__file__).parent / "styles.toml"
with open(_CFG_PATH, "rb") as _f:
    _cfg = tomllib.load(_f)

PALETTE: dict[str, str] = _cfg["colors"]["palette"]

_misc = _cfg["colors"]["misc"]
GRAY = _misc["gray"]
WHITE = _misc["white"]
TRANSPARENT = _misc["transparent"]

# Couleurs des badges de mode : définies par mode dans config/user.toml
MODE_COLORS: dict[str, str] = {
    code: m.couleur for code, m in user_config.modes().items() if m.couleur
}
RANK_COLORS: dict[str, str] = _cfg["colors"]["rank"]
VIGUEUR_COLORS: dict[str, str] = _cfg["colors"]["vigueur"]
SANKEY_NODE_COLORS: dict[str, str] = _cfg["colors"]["sankey_nodes"]
SANKEY_LINK_ALPHA: dict[str, str] = _cfg["colors"]["sankey_links"]
TREEMAP_COLORS: dict[str, str] = _cfg["colors"]["treemap"]
CHART_COLORS: dict[str, str] = _cfg["colors"]["chart"]
SCREEN_APP_COLORS: list[str] = list(_cfg["colors"]["screen_apps"].values())
HTML: dict[str, str] = _cfg["colors"]["html"]
