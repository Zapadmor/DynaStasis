-- Compteur d'entraînements (numéro « Entraînement #X », aligné sur un compteur externe type Strava).
-- Activités Intervals.icu, une par ligne (la synchro n'en gardait que la somme par jour) : permet de les compter
-- et, plus tard, de les associer à une séance saisie sur mobile (workout_sessions.intervals_activity_id).
CREATE TABLE IF NOT EXISTS intervals_activities (
    id            TEXT PRIMARY KEY,            -- identifiant Intervals.icu
    start_local   TEXT NOT NULL,               -- début, heure locale ISO (AAAA-MM-JJTHH:MM:SS)
    date_entry    TEXT NOT NULL,
    type          TEXT,
    name          TEXT,
    moving_time_s REAL,
    training_load REAL,
    fetched_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_intervals_activities_date ON intervals_activities(date_entry);
-- Point de départ du compteur, saisi localement (`python main.py training-counter set ...`) : aucune valeur
-- personnelle dans le dépôt. Une seule ligne.
CREATE TABLE IF NOT EXISTS training_counter (
    id               INTEGER PRIMARY KEY CHECK (id = 1),
    baseline_count   INTEGER NOT NULL,         -- valeur du compteur externe avant le premier entraînement compté
    baseline_date    TEXT    NOT NULL,         -- activités Intervals.icu comptées APRÈS cette date
    first_session_id INTEGER NOT NULL          -- séances saisies comptées à partir de cet identifiant
);
