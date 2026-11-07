"""API de saisie mobile : reçoit une séance de la PWA et l'écrit dans la base DynaStasis.

Lancement : `uvicorn src.api.main:app --host 0.0.0.0 --port 8000`
Le jeton `DYNASTASIS_API_TOKEN` est obligatoire : sans lui, /api/* répond 503 (échec fermé).
"""

from __future__ import annotations

import hmac
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.schemas import WorkoutIn, WorkoutOut
from src.collectors import workout_db
from src.core import training_counter
from src.database.connection import db_session, latest_version
from src.services import workouts

STATIC_DIR = Path(__file__).parent / "static"


def require_token(authorization: str | None = Header(default=None)) -> None:
    expected = os.environ.get("DYNASTASIS_API_TOKEN", "")
    if not expected:
        raise HTTPException(503, "DYNASTASIS_API_TOKEN non configuré sur le serveur")
    given = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(given.encode(), expected.encode()):
        raise HTTPException(401, "Jeton invalide")


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Refuse de démarrer sur une base non migrée (la migration est faite par l'app Streamlit)."""
    with db_session() as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version < latest_version():
        raise RuntimeError(
            f"Base en version {version}, {latest_version()} attendue : lancez `python main.py init-db`"
            " ou démarrez d'abord le service streamlit."
        )
    yield


app = FastAPI(title="DynaStasis — saisie mobile", docs_url=None, redoc_url=None, lifespan=lifespan)

_origins = [o.strip() for o in os.environ.get("DYNASTASIS_API_ORIGINS", "").split(",") if o.strip()]
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

api_deps = [Depends(require_token)]


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.post("/api/workouts", response_model=WorkoutOut, dependencies=api_deps)
def post_workout(workout: WorkoutIn) -> WorkoutOut:
    payload = workout.model_dump()
    workouts.numeroter_series(payload)
    try:
        with db_session() as conn:  # une seule transaction : commit en sortie, rollback sur erreur
            session_id, duplicate = workout_db.import_session(conn, payload)
    except workout_db.UnknownExerciseError as exc:
        raise HTTPException(422, f"Exercice(s) inconnu(s) : {', '.join(exc.names)}") from exc
    with db_session() as conn:
        row = conn.execute(
            "SELECT duration_min, session_volume_kg FROM workout_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        number = training_counter.session_number(conn, session_id)
    return WorkoutOut(
        id=session_id,
        duplicate=duplicate,
        duration_min=row[0] if row else None,
        number=number,
        volume_kg=row[1] if row else None,
    )


@app.get("/api/history", dependencies=api_deps)
def history(limit: int = Query(20, ge=1, le=200)) -> list[dict]:
    return workout_db.get_sessions(limit)


@app.get("/api/exercises", dependencies=api_deps)
def exercises() -> dict:
    with db_session() as conn:
        return {
            "exercises": [
                dict(r)
                for r in conn.execute(
                    "SELECT name, category, load_formula, unit, bw_fraction FROM exercise_library ORDER BY name"
                )
            ],
            "previous": workout_db.last_sets_by_exercise(conn),
            "last_bodyweight_kg": workout_db.last_bodyweight(conn),
        }


@app.get("/api/templates", dependencies=api_deps)
def templates() -> list[dict]:
    with db_session() as conn:
        return workout_db.get_templates_for_pwa(conn)


# En dernier : la PWA statique sur « / » ne doit pas masquer /api.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
