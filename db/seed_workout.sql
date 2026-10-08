-- Seed: bibliothèque d'exercices + templates
-- Idempotent — INSERT OR IGNORE safe à ré-exécuter

-- Bibliothèque canonique (9 exercices)
INSERT OR IGNORE INTO exercise_library (name, category, load_formula) VALUES
    ('Pull Up',        'Pulling', 'bw_plus_weight'),
    ('Dips',           'Pushing', 'bw_plus_weight'),
    ('Push Up',        'Pushing', 'bw_plus_weight'),
    ('Squat',          'Legs',    'weight'),
    ('Bench press',    'Pushing', 'weight'),
    ('Overhead press', 'Pushing', 'weight'),
    ('Skullcrusher',   'Arms',    'weight'),
    ('Grip rotation',  'Arms',    'weight'),
    ('Landmine press', 'Pushing', 'weight');

-- Renames idempotents (si ré-appliqué sur ancienne DB)
UPDATE exercise_library SET name = 'Dips'            WHERE name = 'Dips';
UPDATE exercise_library SET name = 'Squat'           WHERE name = 'Squat (Barbell)';
UPDATE exercise_library SET name = 'Overhead press'  WHERE name = 'Overhead Press (Barbell)';
UPDATE exercise_library SET name = 'Bench press'     WHERE name = 'Bench Press (Barbell)';
UPDATE exercise_library SET name = 'Skullcrusher'    WHERE name = 'Skullcrusher (Barbell)';

INSERT OR IGNORE INTO workout_templates (name) VALUES ('Force MAX');

-- workout_template_exercises (positions 1-3)
INSERT OR IGNORE INTO workout_template_exercises (template_id, exercise_id, position)
SELECT t.id, e.id, 1
FROM workout_templates t, exercise_library e
WHERE t.name = 'Force MAX' AND e.name = 'Pull Up';

INSERT OR IGNORE INTO workout_template_exercises (template_id, exercise_id, position)
SELECT t.id, e.id, 2
FROM workout_templates t, exercise_library e
WHERE t.name = 'Force MAX' AND e.name = 'Dips';

INSERT OR IGNORE INTO workout_template_exercises (template_id, exercise_id, position)
SELECT t.id, e.id, 3
FROM workout_templates t, exercise_library e
WHERE t.name = 'Force MAX' AND e.name = 'Skullcrusher';

-- Nettoyage avant re-seed (idempotent)
DELETE FROM workout_template_sets WHERE tmpl_exercise_id IN (
    SELECT te.id FROM workout_template_exercises te
    JOIN workout_templates t ON te.template_id = t.id WHERE t.name = 'Force MAX'
);

-- Sets Pull Up (tmpl_exercise position 1)
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 0, 'W', 0,  15 FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Force MAX' AND e.name = 'Pull Up';

INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 1, 'W', 20, 10 FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Force MAX' AND e.name = 'Pull Up';

INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 2, 'W', 30,  7 FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Force MAX' AND e.name = 'Pull Up';

INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 3, '1', 55,  2 FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Force MAX' AND e.name = 'Pull Up';

INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 4, '2', 50,  3 FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Force MAX' AND e.name = 'Pull Up';

INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 5, '3', 50,  3 FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Force MAX' AND e.name = 'Pull Up';

INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 6, '4', 50,  3 FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Force MAX' AND e.name = 'Pull Up';

INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 7, 'F',  0, 20 FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Force MAX' AND e.name = 'Pull Up';

-- Sets Dips (tmpl_exercise position 2)
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 0, '1',  0, 20 FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Force MAX' AND e.name = 'Dips';

INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 1, '2', 50,  4 FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Force MAX' AND e.name = 'Dips';

INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 2, '3', 60,  4 FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Force MAX' AND e.name = 'Dips';

INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 3, '4', 65,  3 FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Force MAX' AND e.name = 'Dips';

INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 4, '5', 65,  3 FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Force MAX' AND e.name = 'Dips';

-- Sets Reverse Grip Concentration Curl (position 3)
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 0, '1', 12, 120 FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Force MAX' AND e.name = 'Skullcrusher';

-- ─────────────────────────────────────────────
-- Template "Endurance"
-- ─────────────────────────────────────────────

INSERT OR IGNORE INTO workout_templates (name) VALUES ('Endurance');

INSERT OR IGNORE INTO workout_template_exercises (template_id, exercise_id, position, emom_interval_sec)
SELECT t.id, e.id, 1, 60
FROM workout_templates t, exercise_library e
WHERE t.name = 'Endurance' AND e.name = 'Pull Up';

INSERT OR IGNORE INTO workout_template_exercises (template_id, exercise_id, position, emom_interval_sec)
SELECT t.id, e.id, 2, 60
FROM workout_templates t, exercise_library e
WHERE t.name = 'Endurance' AND e.name = 'Dips';

INSERT OR IGNORE INTO workout_template_exercises (template_id, exercise_id, position, emom_interval_sec)
SELECT t.id, e.id, 3, 60
FROM workout_templates t, exercise_library e
WHERE t.name = 'Endurance' AND e.name = 'Push Up';

INSERT OR IGNORE INTO workout_template_exercises (template_id, exercise_id, position, emom_interval_sec)
SELECT t.id, e.id, 4, NULL
FROM workout_templates t, exercise_library e
WHERE t.name = 'Endurance' AND e.name = 'Skullcrusher';

-- Nettoyage avant re-seed (idempotent)
DELETE FROM workout_template_sets WHERE tmpl_exercise_id IN (
    SELECT te.id FROM workout_template_exercises te
    JOIN workout_templates t ON te.template_id = t.id WHERE t.name = 'Endurance'
);

-- Sets Pull Up (Endurance)
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 0, '1', 0, 11
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Pull Up';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 1, '2', 0, 11
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Pull Up';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 2, '3', 0, 11
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Pull Up';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 3, '4', 0, 11
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Pull Up';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 4, '5', 0, 11
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Pull Up';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 5, '6', 0, 11
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Pull Up';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 6, '7', 0, 11
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Pull Up';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 7, '8', 0, 11
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Pull Up';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 8, '9', 0, 11
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Pull Up';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 9, '10', 0, 11
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Pull Up';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 10, '11', 0, 11
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Pull Up';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 11, '12', 0, 11
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Pull Up';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 12, '13', 0, 11
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Pull Up';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 13, '14', 0, 11
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Pull Up';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 14, '15', 0, 11
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Pull Up';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 15, '16', 0, 11
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Pull Up';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 16, '17', 0, 11
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Pull Up';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 17, '18', 0, 11
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Pull Up';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 18, '19', 0, 11
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Pull Up';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 19, '20', 0, 11
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Pull Up';

-- Sets Dips (Endurance)
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 0, '1', 0, 15
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Dips';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 1, '2', 0, 15
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Dips';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 2, '3', 0, 15
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Dips';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 3, '4', 0, 15
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Dips';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 4, '5', 0, 15
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Dips';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 5, '6', 0, 15
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Dips';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 6, '7', 0, 15
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Dips';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 7, '8', 0, 15
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Dips';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 8, '9', 0, 15
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Dips';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 9, '10', 0, 15
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Dips';

-- Sets Push Up (Endurance)
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 0, '1', 0, 20
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Push Up';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 1, '2', 0, 20
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Push Up';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 2, '3', 0, 20
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Push Up';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 3, '4', 0, 20
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Push Up';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 4, '5', 0, 20
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Push Up';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 5, '6', 0, 20
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Push Up';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 6, '7', 0, 20
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Push Up';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 7, '8', 0, 20
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Push Up';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 8, '9', 0, 20
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Push Up';
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 9, '10', 0, 20
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Push Up';

-- Sets Skullcrusher (Endurance)
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 0, '1', 12, 120
FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Endurance' AND e.name = 'Skullcrusher';

-- ─────────────────────────────────────────────
-- Template "Force endurance"
-- ─────────────────────────────────────────────

INSERT OR IGNORE INTO workout_templates (name) VALUES ('Force endurance');

INSERT OR IGNORE INTO workout_template_exercises (template_id, exercise_id, position)
SELECT t.id, e.id, 1
FROM workout_templates t, exercise_library e
WHERE t.name = 'Force endurance' AND e.name = 'Pull Up';

INSERT OR IGNORE INTO workout_template_exercises (template_id, exercise_id, position)
SELECT t.id, e.id, 2
FROM workout_templates t, exercise_library e
WHERE t.name = 'Force endurance' AND e.name = 'Dips';

INSERT OR IGNORE INTO workout_template_exercises (template_id, exercise_id, position)
SELECT t.id, e.id, 3
FROM workout_templates t, exercise_library e
WHERE t.name = 'Force endurance' AND e.name = 'Skullcrusher';

-- Nettoyage avant re-seed (idempotent)
DELETE FROM workout_template_sets WHERE tmpl_exercise_id IN (
    SELECT te.id FROM workout_template_exercises te
    JOIN workout_templates t ON te.template_id = t.id WHERE t.name = 'Force endurance'
);

-- Sets Pull Up (Force endurance)
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 0, 'W',  0, 15 FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Force endurance' AND e.name = 'Pull Up';

INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 1, 'W', 10, 20 FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Force endurance' AND e.name = 'Pull Up';

INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 2, 'W', 20, 11 FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Force endurance' AND e.name = 'Pull Up';

INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 3, '1', 30,  9 FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Force endurance' AND e.name = 'Pull Up';

INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 4, '2', 40,  6 FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Force endurance' AND e.name = 'Pull Up';

INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 5, '3', 40,  6 FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Force endurance' AND e.name = 'Pull Up';

INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 6, '4', 40,  6 FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Force endurance' AND e.name = 'Pull Up';

-- Sets Dips (Force endurance)
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 0, '1', 45,  6 FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Force endurance' AND e.name = 'Dips';

INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 1, '2', 45,  6 FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Force endurance' AND e.name = 'Dips';

INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 2, '3', 40,  6 FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Force endurance' AND e.name = 'Dips';

INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 3, '4', 40,  6 FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Force endurance' AND e.name = 'Dips';

-- Sets Reverse Grip Concentration Curl (Force endurance)
INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, weight_kg, reps)
SELECT te.id, 0, '1', 12, 120 FROM workout_template_exercises te
JOIN workout_templates t ON te.template_id = t.id
JOIN exercise_library e ON te.exercise_id = e.id
WHERE t.name = 'Force endurance' AND e.name = 'Skullcrusher';

