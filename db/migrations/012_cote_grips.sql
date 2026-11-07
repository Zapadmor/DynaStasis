-- Côté d'une série unilatérale (grips, un bras) : 'D' (droite), 'G' (gauche) ou NULL (bilatéral).
ALTER TABLE workout_session_sets ADD COLUMN side TEXT;
