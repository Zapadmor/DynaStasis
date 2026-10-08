"""
Accès unifié aux secrets DynaStasis — indépendant de Streamlit.

Convention : le secret (section, key) correspond à la variable d'environnement
``SECTION_KEY`` en majuscules (ex. ("intervals_icu", "api_key") → INTERVALS_ICU_API_KEY).

Ordre de résolution :
  1. os.environ                    — Docker (env_file), systemd, CI
  2. fichier d'environnement       — hors dépôt, chmod 600
       $DYNASTASIS_ENV_FILE ou ~/.config/dynastasie/secrets.env
  3. .streamlit/secrets.toml       — héritage (déprécié, à supprimer)
  4. default
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

_LEGACY_TOML = Path(__file__).resolve().parents[1] / ".streamlit" / "secrets.toml"
_DEFAULT_ENV_FILE = Path.home() / ".config" / "dynastasie" / "secrets.env"

_env_file_cache: dict[str, str] | None = None
_toml_cache: dict[str, Any] | None = None


def env_file_path() -> Path:
    return Path(os.environ.get("DYNASTASIS_ENV_FILE") or _DEFAULT_ENV_FILE)


def _var_name(section: str, key: str) -> str:
    return f"{section}_{key}".upper()


def _load_env_file() -> dict[str, str]:
    global _env_file_cache
    if _env_file_cache is not None:
        return _env_file_cache
    values: dict[str, str] = {}
    path = env_file_path()
    if path.is_file():
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values[name.strip()] = value
    _env_file_cache = values
    return values


def _load_legacy_toml() -> dict[str, Any]:
    global _toml_cache
    if _toml_cache is not None:
        return _toml_cache
    _toml_cache = {}
    if _LEGACY_TOML.exists():
        import tomllib

        with open(_LEGACY_TOML, "rb") as f:
            _toml_cache = tomllib.load(f)
    return _toml_cache


def get_secret(section: str, key: str, default: str = "") -> str:
    """Retourne le secret identifié par (section, key)."""
    name = _var_name(section, key)

    value = os.environ.get(name)
    if value:
        return value

    value = _load_env_file().get(name)
    if value:
        return value

    legacy = _load_legacy_toml().get(section, {}).get(key)
    if legacy is not None:
        return str(legacy)

    return default


def set_secret(section: str, key: str, value: str) -> Path:
    """Écrit/met à jour une variable dans le fichier d'environnement (chmod 600)."""
    global _env_file_cache
    name = _var_name(section, key)
    path = env_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    new_line = f"{name}={value}"
    for i, line in enumerate(lines):
        if line.partition("=")[0].strip() == name:
            lines[i] = new_line
            break
    else:
        lines.append(new_line)

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    _env_file_cache = None
    return path
