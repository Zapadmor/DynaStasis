-- Séance mobile : durées mesurées (EMOM), exercices statiques, temps d'entraînement au journal.
-- exercise_library.unit : 'reps' (défaut) ou 'sec' (exercice statique : `reps` = secondes tenues).
ALTER TABLE exercise_library ADD COLUMN unit TEXT NOT NULL DEFAULT 'reps';
-- Temps mis pour effectuer la série dans sa minute (EMOM), et numéro de la minute dans le bloc.
ALTER TABLE workout_session_sets ADD COLUMN duration_s REAL;
ALTER TABLE workout_session_sets ADD COLUMN emom_minute INTEGER;
-- Durée de la séance (première à dernière action) ; somme du jour recopiée dans vigueur_entries.workout_min,
-- colonne que la synchro Intervals.icu n'écrase pas.
ALTER TABLE workout_sessions ADD COLUMN duration_min REAL;
ALTER TABLE vigueur_entries ADD COLUMN workout_min REAL;
