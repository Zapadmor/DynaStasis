-- Charge d'entraînement recalculée localement (HRSS, puissance ou allure), une ligne par activité.
-- Additive : rien ne la lit par défaut, la source de vérité reste intervals_activities.training_load.
CREATE TABLE IF NOT EXISTS charge_locale (
    activity_id  TEXT PRIMARY KEY,             -- identifiant Intervals.icu, comme intervals_activities.id
    date_entry   TEXT NOT NULL,
    charge       REAL NOT NULL,
    methode      TEXT NOT NULL,                -- hrss | puissance_estimee | allure_estimee | aucune
    confiance    TEXT NOT NULL,                -- haute | moyenne | faible | nulle
    estime       INTEGER NOT NULL DEFAULT 0,   -- 1 si la charge repose sur un seuil ou un recalage estimé
    version_algo TEXT NOT NULL,
    calcule_le   TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_charge_locale_date ON charge_locale(date_entry);
