"""Timezone helpers — toujours Europe/Paris."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Paris")


def now_paris() -> datetime:
    """Heure courante en heure de Paris, naive (sans tzinfo) pour compatibilité."""
    return datetime.now(TZ).replace(tzinfo=None)


def today_paris():
    """Date courante en fuseau horaire de Paris."""
    return datetime.now(TZ).date()
