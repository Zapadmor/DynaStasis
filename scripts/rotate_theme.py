#!/usr/bin/env python3
"""Rotate Streamlit theme — runs daily at 20:00 via cron.

Themes live in .streamlit/themes/<name>.toml.
Each theme defines only the 4 color fields — font and weights are never touched.
Selection is random, excluding the current active theme.
"""

import random
import re
import tomllib
from pathlib import Path

PROJECT = Path(__file__).parent.parent
THEMES_DIR = PROJECT / ".streamlit" / "themes"
CONFIG = PROJECT / ".streamlit" / "config.toml"
STATE = THEMES_DIR / ".current"

COLOR_FIELDS = ["primaryColor", "backgroundColor", "secondaryBackgroundColor", "textColor"]


def _load_themes() -> list[Path]:
    themes = sorted(THEMES_DIR.glob("*.toml"))
    return [t for t in themes if not t.name.startswith(".")]


def _pick_random(themes: list[Path]) -> Path:
    current = STATE.read_text().strip() if STATE.exists() else ""
    available = [t for t in themes if t.stem != current] or themes
    return random.choice(available)


def _rewrite_colors(colors: dict) -> None:
    text = CONFIG.read_text()
    for field in COLOR_FIELDS:
        if field not in colors:
            continue
        pattern = rf'^({re.escape(field)}\s*=\s*)"[^"]*"'
        replacement = rf'\1"{colors[field]}"'
        text = re.sub(pattern, replacement, text, flags=re.MULTILINE)
    CONFIG.write_text(text)


def main() -> None:
    themes = _load_themes()
    if not themes:
        raise SystemExit(f"[rotate_theme] No themes found in {THEMES_DIR}")

    chosen = _pick_random(themes)
    with open(chosen, "rb") as f:
        data = tomllib.load(f)

    if "theme" not in data:
        raise SystemExit(f"[rotate_theme] Missing [theme] section in {chosen.name}")

    _rewrite_colors(data["theme"])
    STATE.write_text(chosen.stem)
    print(f"[rotate_theme] Active theme → {chosen.stem}")


if __name__ == "__main__":
    main()
