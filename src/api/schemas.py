"""Modèles du payload envoyé par la PWA de séance."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

SetType = Literal["W", "F", "D", "N"]  # N = série de travail ; renumérotée côté serveur

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")


class SetIn(BaseModel):
    set_type: SetType = "N"
    weight_kg: float = Field(0, ge=0, le=1000)
    reps: float = Field(1, ge=0, le=1000)  # secondes (décimales) pour un exercice statique
    side: Literal["D", "G"] | None = None  # série unilatérale (grips, un bras)
    rpe: float | None = Field(None, ge=1, le=10)
    completed: bool = False
    duration_s: float | None = Field(None, ge=0, le=900)  # EMOM : temps mis dans la minute
    emom_minute: int | None = Field(None, ge=1, le=500)


class ExerciseIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    sets: list[SetIn] = Field(max_length=50)
    create: bool = False  # vrai seulement si l'utilisateur crée explicitement un exercice
    # formule de charge, utilisée seulement à la création d'un exercice (`create`)
    load_formula: Literal["weight", "bw_plus_weight"] = "weight"
    unit: Literal["reps", "sec"] = "reps"  # 'sec' : exercice statique, `reps` = secondes tenues
    emom_interval_sec: int | None = Field(None, ge=10, le=900)

    @field_validator("name")
    @classmethod
    def _strip(_cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("nom d'exercice vide")
        return v


class WorkoutIn(BaseModel):
    client_uuid: str = Field(min_length=8, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    template_id: int | None = None
    started_at: str
    finished_at: str | None = None
    worked_from: str | None = None  # première action (START d'un EMOM ou première série validée)
    worked_to: str | None = None  # dernière série validée ou fin d'EMOM
    note: str | None = Field(None, max_length=2000)
    bodyweight_kg: float | None = Field(None, ge=0, le=500)
    exercises: list[ExerciseIn] = Field(min_length=1, max_length=40)

    @field_validator("started_at", "finished_at", "worked_from", "worked_to")
    @classmethod
    def _iso(_cls, v: str | None) -> str | None:
        if v is not None and not _ISO.match(v):
            raise ValueError("date ISO attendue (AAAA-MM-JJTHH:MM)")
        return v

    @model_validator(mode="after")
    def _plage_de_travail(self):
        """Durée d'entraînement cohérente : les deux bornes ensemble, ordonnées, 10 h maximum."""
        if (self.worked_from is None) != (self.worked_to is None):
            raise ValueError("worked_from et worked_to vont ensemble")
        if self.worked_from is not None:
            try:
                delta = datetime.fromisoformat(self.worked_to) - datetime.fromisoformat(
                    self.worked_from
                )
            except ValueError as exc:
                raise ValueError("date ISO invalide") from exc
            if not 0 <= delta.total_seconds() <= 600 * 60:
                raise ValueError("durée d'entraînement hors limites (0 à 600 min)")
        return self


class WorkoutOut(BaseModel):
    id: int
    duplicate: bool
    duration_min: float | None = None
    number: int = 0  # « Entraînement n° X » (rang dans l'historique)
    volume_kg: float | None = None  # somme (poids du corps + lest) x reps des séries validées
