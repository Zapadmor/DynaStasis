-- Index des tables de séances : sans eux chaque lecture (« Préc. », historique, suppression en cascade)
-- relit toute la table (38 s pour la requête « Préc. » sur ~5 800 séries).
CREATE INDEX IF NOT EXISTS idx_wss_session_ex ON workout_session_sets(session_ex_id);
CREATE INDEX IF NOT EXISTS idx_wse_session ON workout_session_exercises(session_id);
CREATE INDEX IF NOT EXISTS idx_wse_exercise ON workout_session_exercises(exercise_id);
