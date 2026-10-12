"""Configuration utilisateur (`config/user.toml`) : fuseau horaire, modes, seuils et poids du score,
critère « engagement », piliers actifs.

Le fichier est facultatif : sans lui, les valeurs par défaut ci-dessous s'appliquent. Chemin
personnalisable via `DYNASTASIS_CONFIG`. `config/user.toml.example` reprend ces défauts (un test
vérifie qu'ils restent identiques). Les seuils et les modes sont recopiés en base à chaque
`init_db()` (tables `score_config` et `modes_config`) car les vues SQL du score les lisent.
"""

from __future__ import annotations

import os
import sqlite3
import tomllib
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "user.toml"

CRITERES = [
    "entrainement",
    "seances",
    "pas",
    "sommeil",
    "charge_fraicheur",
    "ecran",
    "deep_focus",
    "projets_fond",
    "engagement",
    "cloture",
]

DEFAULTS: dict[str, Any] = {
    "general": {"timezone": "Europe/Paris"},
    "interface": {"widget_url": ""},
    "piliers": {"actifs": None},  # None : tous les piliers déclarés dans src/pillars/
    "engagement": {
        "actif": True,
        "libelle": "Engagement",
        "libelle_jours": "Jours d'engagement",
    },
    "modes": {
        "ecole": {
            "label": "École",
            "focus_jour_min": 240,
            "focus_semaine_min": 1500,
            "tag_pro": False,
            "couleur": "#219ebc",
        },
        "entreprise": {
            "label": "Entreprise",
            "focus_jour_min": 150,
            "focus_semaine_min": 900,
            "tag_pro": True,
            "couleur": "#ffb703",
        },
    },
    "seuils": {
        "jour": {
            "sport_min": 60,
            "sommeil_min": 450,
            "pas": 10000,
            "focus_strat_min": 30,
            "ecran_max_min": 30,
            "focus_defaut_min": 90,
        },
        "semaine": {
            "seance_duree_min": 30,
            "entrainement_min": 420,
            "seances": 6,
            "pas": 70000,
            "sommeil_min": 450,
            "tsb_min": -25,
            "tsb_decharge_min": -5,
            "ecran_max_min": 210,
            "projets_fond_min": 120,
            "engagement_min": 45,
            "engagement_jours": 1,
            "focus_defaut_min": 630,
        },
    },
    "poids": dict.fromkeys(CRITERES, 1),
}


class ConfigError(ValueError):
    """Fichier de configuration invalide."""


def _merge(base: dict, override: dict, path: str = "") -> dict:
    """Fusion récursive ; les sections libres (`modes`) sont remplacées si le fichier les définit."""
    result = deepcopy(base)
    for key, value in override.items():
        where = f"{path}{key}"
        if key not in base:
            raise ConfigError(f"Clé inconnue dans la configuration : {where}")
        if where == "modes":
            result["modes"] = {code: dict(spec) for code, spec in value.items()}
        elif isinstance(value, dict) and isinstance(base.get(key), dict):
            result[key] = _merge(base[key], value, where + ".")
        else:
            result[key] = value
    return result


def defaults() -> dict[str, Any]:
    """Valeurs par défaut ; les piliers actifs viennent du registre `src/pillars/`."""
    from src import pillars  # noqa: PLC0415

    cfg = deepcopy(DEFAULTS)
    cfg["piliers"]["actifs"] = pillars.keys()
    return cfg


def config_path() -> Path:
    return Path(os.environ.get("DYNASTASIS_CONFIG") or CONFIG_PATH)


@lru_cache(maxsize=1)
def load() -> dict[str, Any]:
    """Configuration fusionnée avec les défauts (mise en cache ; voir `reload`)."""
    path = config_path()
    data: dict[str, Any] = {}
    if path.is_file():
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"{path} : TOML invalide ({exc})") from exc
    cfg = _merge(defaults(), data)
    _validate(cfg)
    return cfg


def reload() -> dict[str, Any]:
    load.cache_clear()
    return load()


def _validate(cfg: dict) -> None:
    try:
        ZoneInfo(cfg["general"]["timezone"])
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ConfigError(f"Fuseau horaire inconnu : {cfg['general']['timezone']!r}") from exc
    from src import pillars  # noqa: PLC0415

    inconnus = set(cfg["piliers"]["actifs"]) - set(pillars.keys())
    if inconnus:
        raise ConfigError(f"Piliers inconnus : {sorted(inconnus)} (valides : {pillars.keys()})")
    if not cfg["modes"]:
        raise ConfigError("Au moins un mode est requis dans [modes.*].")
    for code, spec in cfg["modes"].items():
        if not code.replace("_", "").isalnum():
            raise ConfigError(f"Code de mode invalide : {code!r} (lettres, chiffres, _)")
        for key in ("label", "focus_jour_min", "focus_semaine_min"):
            if key not in spec:
                raise ConfigError(f"[modes.{code}] : clé « {key} » manquante")
    for name, poids in cfg["poids"].items():
        if float(poids) < 0:
            raise ConfigError(f"Poids négatif pour {name}")


# ── Accesseurs ────────────────────────────────────────────────────────────────
def timezone() -> ZoneInfo:
    return ZoneInfo(load()["general"]["timezone"])


@dataclass(frozen=True)
class Mode:
    code: str
    label: str
    focus_jour_min: float
    focus_semaine_min: float
    tag_pro: bool
    couleur: str | None


def modes() -> dict[str, Mode]:
    return {
        code: Mode(
            code=code,
            label=spec["label"],
            focus_jour_min=float(spec["focus_jour_min"]),
            focus_semaine_min=float(spec["focus_semaine_min"]),
            tag_pro=bool(spec.get("tag_pro", False)),
            couleur=spec.get("couleur"),
        )
        for code, spec in load()["modes"].items()
    }


def default_mode() -> str:
    """Mode appliqué à une semaine sans séquence : le premier de la configuration."""
    return next(iter(load()["modes"]))


def mode_label(code: str | None) -> str:
    """Libellé affiché d'un mode (le code lui-même s'il n'est plus configuré)."""
    code = code or default_mode()
    mode = modes().get(code)
    return mode.label if mode else code


def widget_url() -> str:
    """URL d'un widget (iframe) affiché en bas de la barre latérale ; vide = aucun."""
    return str(load()["interface"]["widget_url"]).strip()


def pilier_actif(pilier: str) -> bool:
    return pilier in load()["piliers"]["actifs"]


def engagement_actif() -> bool:
    return bool(load()["engagement"]["actif"])


def engagement_libelle() -> str:
    return str(load()["engagement"]["libelle"])


def engagement_libelle_jours() -> str:
    return str(load()["engagement"]["libelle_jours"])


def poids() -> dict[str, float]:
    """Poids des 10 critères du score hebdo (0 = critère désactivé)."""
    result = {name: float(value) for name, value in load()["poids"].items()}
    if not engagement_actif():
        result["engagement"] = 0.0
    return result


def critere_actif(critere: str) -> bool:
    return poids().get(critere, 0.0) > 0


def score_params() -> dict[str, float]:
    """Paramètres à plat pour la table `score_config` (clé = `jour_*`, `sem_*`, `poids_*`)."""
    cfg = load()
    params: dict[str, float] = {}
    for key, value in cfg["seuils"]["jour"].items():
        params[f"jour_{key}"] = float(value)
    for key, value in cfg["seuils"]["semaine"].items():
        params[f"sem_{key}"] = float(value)
    for name, value in poids().items():
        params[f"poids_{name}"] = value
    return params


def sync_to_db(conn: sqlite3.Connection) -> None:
    """Recopie seuils, poids et modes dans `score_config` / `modes_config` (lus par les vues)."""
    conn.execute("DELETE FROM score_config")
    conn.executemany(
        "INSERT INTO score_config (cle, valeur) VALUES (?, ?)", list(score_params().items())
    )
    conn.execute("DELETE FROM modes_config")
    conn.executemany(
        "INSERT INTO modes_config (code, libelle, focus_jour_min, focus_semaine_min, tag_pro, ordre) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            (m.code, m.label, m.focus_jour_min, m.focus_semaine_min, int(m.tag_pro), i)
            for i, m in enumerate(modes().values())
        ],
    )
