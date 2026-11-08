"""Axe endurance : charge par séance (HRSS, puissance, allure) et modèle Forme/Fatigue.

Contrat partagé (implémenté en phase 2) :
- `hrss(streams, params) -> float`
- `pmc(daily_loads, seed) -> pandas.DataFrame[ctl, atl, tsb]`
"""

from __future__ import annotations
