-- Saisie mobile (PWA) : identifiant client pour l'envoi idempotent, RPE par série.
ALTER TABLE workout_sessions ADD COLUMN client_uuid TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_ws_client_uuid ON workout_sessions(client_uuid) WHERE client_uuid IS NOT NULL;
ALTER TABLE workout_session_sets ADD COLUMN rpe REAL;
