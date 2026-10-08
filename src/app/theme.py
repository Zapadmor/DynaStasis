from __future__ import annotations

import re
import tomllib
from pathlib import Path

_THEMES_DIR = Path(__file__).resolve().parents[2] / ".streamlit" / "themes"
_CURRENT_FILE = _THEMES_DIR / ".current"
_CONFIG_FILE = Path(__file__).resolve().parents[2] / ".streamlit" / "config.toml"

_COLOR_FIELDS = ["primaryColor", "backgroundColor", "secondaryBackgroundColor", "textColor"]

_FALLBACK = {
    "primaryColor": "#ffb703",
    "backgroundColor": "#023047",
    "secondaryBackgroundColor": "#012535",
    "textColor": "#8ecae6",
}


def _load() -> dict[str, str]:
    try:
        name = _CURRENT_FILE.read_text(encoding="utf-8").strip()
        toml_path = _THEMES_DIR / f"{name}.toml"
        raw = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        return raw.get("theme", _FALLBACK)
    except Exception:
        return _FALLBACK


def _load_by_name(name: str) -> dict[str, str]:
    try:
        toml_path = _THEMES_DIR / f"{name}.toml"
        raw = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        return raw.get("theme", _FALLBACK)
    except Exception:
        return _FALLBACK


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _luminance(hex_color: str) -> float:
    r, g, b = _hex_to_rgb(hex_color)
    vals = []
    for c in (r, g, b):
        s = c / 255.0
        vals.append(s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4)
    return 0.2126 * vals[0] + 0.7152 * vals[1] + 0.0722 * vals[2]


# ── Public accessors ──────────────────────────────────────────────────────────


def primary() -> str:
    return _load().get("primaryColor", _FALLBACK["primaryColor"])


def bg() -> str:
    return _load().get("backgroundColor", _FALLBACK["backgroundColor"])


def secondary_bg() -> str:
    return _load().get("secondaryBackgroundColor", _FALLBACK["secondaryBackgroundColor"])


def text() -> str:
    return _load().get("textColor", _FALLBACK["textColor"])


def is_dark() -> bool:
    return _luminance(bg()) < 0.18


def contrast_text(hex_color: str) -> str:
    """Return '#ffffff' or a dark color depending on the background luminance."""
    try:
        lum = _luminance(hex_color)
    except Exception:
        return "#ffffff"
    return "#ffffff" if lum < 0.35 else "#1a1a1a"


def plotly_layout() -> dict:
    t = _load()
    bg_color = t.get("backgroundColor", _FALLBACK["backgroundColor"])
    text_color = t.get("textColor", _FALLBACK["textColor"])
    return {
        "paper_bgcolor": bg_color,
        "plot_bgcolor": bg_color,
        "font": {"color": text_color, "family": "Satoshi, sans-serif"},
        "margin": {"t": 30, "b": 30, "l": 10, "r": 10},
    }


def _hex_with_alpha(hex_color: str, alpha: float) -> str:
    """Convert a hex color + alpha [0-1] to an rgba() string Plotly accepts."""
    r, g, b = _hex_to_rgb(hex_color)
    return f"rgba({r},{g},{b},{alpha})"


def axis_style(show_grid: bool = True) -> dict:
    text_color = _load().get("textColor", _FALLBACK["textColor"])
    style: dict = {
        "tickfont": {"color": text_color, "size": 11},
        "title_font": {"color": text_color},
        "linecolor": _hex_with_alpha(text_color, 0.27),  # ~44/255
        "showgrid": show_grid,
    }
    if show_grid:
        style["gridcolor"] = _hex_with_alpha(text_color, 0.13)  # ~22/255
    return style


# ── Theme management ──────────────────────────────────────────────────────────


def list_themes() -> list[str]:
    return sorted(p.stem for p in _THEMES_DIR.glob("*.toml"))


def current_theme_name() -> str:
    try:
        return _CURRENT_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return "deep_space"


def _rewrite_config_colors(colors: dict[str, str]) -> None:
    text = _CONFIG_FILE.read_text(encoding="utf-8")
    for field in _COLOR_FIELDS:
        if field not in colors:
            continue
        pattern = rf'^({re.escape(field)}\s*=\s*)"[^"]*"'
        replacement = rf'\1"{colors[field]}"'
        text = re.sub(pattern, replacement, text, flags=re.MULTILINE)
    _CONFIG_FILE.write_text(text, encoding="utf-8")


def apply_theme(name: str) -> None:
    toml_path = _THEMES_DIR / f"{name}.toml"
    raw = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    colors = {k: v for k, v in raw.get("theme", {}).items() if k in _COLOR_FIELDS}
    _rewrite_config_colors(colors)
    _CURRENT_FILE.write_text(name, encoding="utf-8")


def create_theme(name: str, colors: dict[str, str]) -> str:
    safe_name = re.sub(r"[^a-z0-9_-]", "_", name.lower().strip())
    if not safe_name:
        raise ValueError("Nom de thème invalide.")
    toml_path = _THEMES_DIR / f"{safe_name}.toml"
    lines = ["[theme]\n"]
    for field in _COLOR_FIELDS:
        val = colors.get(field, "#000000")
        lines.append(f'{field:<28} = "{val}"\n')
    toml_path.write_text("".join(lines), encoding="utf-8")
    return safe_name


def delete_theme(name: str) -> None:
    all_themes = list_themes()
    if len(all_themes) <= 1:
        raise ValueError("Impossible de supprimer le seul thème restant.")
    toml_path = _THEMES_DIR / f"{name}.toml"
    toml_path.unlink(missing_ok=True)
    if current_theme_name() == name:
        remaining = [t for t in all_themes if t != name]
        if remaining:
            apply_theme(remaining[0])


def color_swatches_html(colors: dict[str, str]) -> str:
    labels = {
        "primaryColor": "Primaire",
        "backgroundColor": "Fond",
        "secondaryBackgroundColor": "Fond sec.",
        "textColor": "Texte",
    }
    parts = []
    for field in _COLOR_FIELDS:
        c = colors.get(field, "#888")
        label = labels.get(field, field)
        parts.append(
            f'<span title="{label}: {c}" style="display:inline-block;width:30px;height:30px;'
            f"background:{c};border-radius:6px;margin-right:6px;"
            f'border:1px solid rgba(128,128,128,.35);vertical-align:middle;"></span>'
        )
    return "".join(parts)
