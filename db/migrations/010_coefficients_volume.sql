-- Volume d'une séance mobile : coefficients par exercice.
-- rep_factor : conversion des reps d'un mouvement complexe (muscle-up, grips) ; 1.0 = aucune conversion.
--   Aucune source scientifique de conversion trouvée : valeur fixée à la main ou calculée sur tes données
--   (scripts/suggest_rep_factor.py). N'agit que sur le volume, pas sur load_kg.
ALTER TABLE exercise_library ADD COLUMN rep_factor REAL NOT NULL DEFAULT 1.0;
-- bw_fraction : part du poids du corps réellement soulevée (formule bw_plus_weight). Pompes ~0.7
--   (Suprak et al. 2011, ~64-75 % selon la position) ; le lest s'ajoute en entier.
ALTER TABLE exercise_library ADD COLUMN bw_fraction REAL NOT NULL DEFAULT 1.0;
UPDATE exercise_library SET bw_fraction = 0.7 WHERE name = 'Push Up';
