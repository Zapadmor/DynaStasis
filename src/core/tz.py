"""Helpers de fuseau horaire — fuseau configurable (`[general] timezone` de config/user.toml)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from src.core import user_config


def tz() -> ZoneInfo:
    """Fuseau horaire de l'utilisateur."""
    return user_config.timezone()


def now_local() -> datetime:
    """Heure courante dans le fuseau configuré, naive (sans tzinfo) pour compatibilité."""
    return datetime.now(tz()).replace(tzinfo=None)


def today_local():
    """Date courante dans le fuseau configuré."""
    return datetime.now(tz()).date()
