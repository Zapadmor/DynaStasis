"""Données de démonstration (100 % fictives) pour essayer DynaStasis sans aucune source externe.

`seed_demo()` crée une base dédiée, dates relatives à aujourd'hui, générée de façon déterministe
(même graine → mêmes valeurs). Elle est idempotente : une base déjà marquée « démo » est recréée ;
une base qui contient d'autres données n'est jamais touchée sans confirmation explicite.
"""

from __future__ import annotations

import random
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from src.core import user_config
from src.core.focus_manager import TAGS
from src.core.profile import set_profile
from src.core.tz import today_local
from src.database import connection
from src.services import projets
from src.services.semaines import get_or_create_week_id, trigger_cascade_week

MARKER_KEY = "demo.marker"
DEFAULT_DEMO_DB = Path(__file__).resolve().parents[2] / "data" / "demo" / "dynastasie-demo.db"
NB_WEEKS = 12
SEED = 20260101

# Applications fictives (paquets Android inventés) ; les deux premières comptent comme « distractives ».
APPS = [
    ("com.demo.video", "Vidéos", True),
    ("com.demo.social", "Réseau social", True),
    ("com.demo.notes", "Notes", False),
    ("com.demo.mail", "Messagerie", False),
]


class DemoSeedError(RuntimeError):
    """La base cible ne peut pas être (re)créée sans risque."""


def _is_same_file(a: Path, b: Path) -> bool:
    return a.resolve() == b.resolve()


def _prepare_target(path: Path, allow_real_db: bool) -> None:
    """Supprime la base cible si c'est une base de démo ; refuse toute autre base non vide."""
    real_db = Path(__file__).resolve().parents[2] / "db" / "dynastasie.db"
    if _is_same_file(path, real_db) and not allow_real_db:
        raise DemoSeedError(
            f"{path} est la base réelle : refus de la remplacer par des données fictives. "
            "Choisissez une autre cible (--db) ou confirmez avec --base-reelle."
        )
    if not path.exists():
        return
    is_demo = False
    has_data = False
    try:
        with sqlite3.connect(path) as conn:
            try:
                is_demo = (
                    conn.execute(
                        "SELECT 1 FROM profil_contenu WHERE cle = ?", (MARKER_KEY,)
                    ).fetchone()
                    is not None
                )
                has_data = (
                    conn.execute("SELECT 1 FROM semaines_audit LIMIT 1").fetchone() is not None
                )
            except sqlite3.OperationalError:
                pass  # base vide ou sans schéma
    except sqlite3.DatabaseError as exc:
        raise DemoSeedError(f"{path} n'est pas une base SQLite lisible : {exc}") from exc
    if has_data and not is_demo and not allow_real_db:
        raise DemoSeedError(
            f"{path} contient déjà des données qui ne sont pas des données de démo : "
            "refus de les écraser (utilisez une autre cible avec --db)."
        )
    for suffix in ("", "-wal", "-shm"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)


def seed_demo(db_path: Path | str | None = None, *, allow_real_db: bool = False) -> Path:
    """Crée ou recrée la base de démo et retourne son chemin."""
    path = Path(db_path) if db_path else DEFAULT_DEMO_DB
    _prepare_target(path, allow_real_db)

    previous = connection.DB_PATH
    connection.DB_PATH = path
    try:
        connection.init_db()
        _Seeder(today_local()).run()
    finally:
        connection.DB_PATH = previous
    return path


class _Seeder:
    def __init__(self, today: date) -> None:
        self.today = today
        self.rng = random.Random(SEED)
        self.monday = today - timedelta(days=today.weekday())
        self.first_monday = self.monday - timedelta(weeks=NB_WEEKS - 1)
        self.conn: sqlite3.Connection

    # ── orchestration ────────────────────────────────────────────────────────
    def run(self) -> None:
        with connection.db_session() as conn:
            self.conn = conn
            self._modes()
        weeks = [self.first_monday + timedelta(weeks=i) for i in range(NB_WEEKS)]
        week_ids = {m: get_or_create_week_id(m.isoformat()) for m in weeks}
        with connection.db_session() as conn:
            self.conn = conn
            self._vigueur()
            self._habitudes(week_ids)
            self._focus(week_ids)
            self._ecran(week_ids)
            self._semaines(week_ids)
            self._objectifs()
            self._plan_entrainement()
            self._finance(week_ids)
            self._musculation()
            self._cursus()
            self._relations()
            self._apps()
            self._narratif(week_ids)
        self._projet()
        self._profil()
        for wid in week_ids.values():
            trigger_cascade_week(wid)
        set_profile(MARKER_KEY, {"seed": SEED, "genere_le": self.today.isoformat()})

    def _days(self):
        d = self.first_monday
        while d <= self.today:
            yield d
            d += timedelta(days=1)

    # ── modes (séquences école / entreprise) ─────────────────────────────────
    def _modes(self) -> None:
        mid = self.first_monday + timedelta(weeks=6)
        codes = list(user_config.modes())
        codes = (codes + codes)[:2]  # une seule séquence répétée si un seul mode est configuré
        self.conn.executemany(
            "INSERT INTO sequences_mode (numero, lieu, date_debut, date_fin) VALUES (?, ?, ?, ?)",
            [
                (
                    1,
                    codes[0],
                    (self.first_monday - timedelta(weeks=12)).isoformat(),
                    (mid - timedelta(days=1)).isoformat(),
                ),
                (2, codes[1], mid.isoformat(), (mid + timedelta(weeks=20)).isoformat()),
            ],
        )

    # ── VIGUEUR ──────────────────────────────────────────────────────────────
    def _vigueur(self) -> None:
        ctl, atl = 38.0, 40.0
        rows = []
        for d in self._days():
            repos = d.weekday() == 6
            moving = 0 if repos else self.rng.choice([30, 45, 60, 75, 90])
            tss = 0.0 if repos else round(moving * self.rng.uniform(0.8, 1.2), 1)
            ctl += (tss - ctl) / 42
            atl += (tss - atl) / 7
            rows.append(
                (
                    d.isoformat(),
                    round(ctl, 1),
                    round(atl, 1),
                    round(ctl - atl, 1),
                    tss,
                    round(52 + (d - self.first_monday).days * 0.02, 1),
                    0.0 if repos else round(moving / 6.0, 1),
                    float(moving),
                    round(self.rng.uniform(58, 82), 1),
                    round(self.rng.uniform(49, 57), 1),
                    float(self.rng.randint(380, 520)),
                    self.rng.randint(5500, 14500),
                    "demo",
                )
            )
        self.conn.executemany(
            "INSERT INTO vigueur_entries (date_entry, ctl, atl, tsb, tss, vo2max, distance_km, "
            "moving_time_min, hrv, rhr, sleep_min, steps, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        self.conn.execute(
            "INSERT INTO sync_checkpoints (source, last_date) VALUES ('intervals_icu', ?)",
            (self.today.isoformat(),),
        )
        self.conn.executemany(
            "INSERT INTO vigueur_personal_records (distance_m, duree_sec, date_realisation, source) "
            "VALUES (?, ?, ?, 'demo')",
            [
                (5000, 1380, (self.today - timedelta(days=40)).isoformat()),
                (10000, 2940, (self.today - timedelta(days=75)).isoformat()),
            ],
        )

    # ── habitudes et focus ───────────────────────────────────────────────────
    def _habitudes(self, week_ids: dict[date, int]) -> None:
        for d in self._days():
            wid = week_ids[d - timedelta(days=d.weekday())]
            r = self.rng
            self.conn.execute(
                "INSERT INTO habitude_logs (date_log, jour_label, semaine_id, bonne_recup_8h9h, "
                "deep_focus_90min, lecture_10min, sport_marche_45min, jeune_intermittent, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ok')",
                (
                    d.isoformat(),
                    d.strftime("%A"),
                    wid,
                    int(r.random() < 0.55),
                    int(r.random() < 0.5),
                    int(r.random() < 0.7),
                    int(r.random() < 0.6),
                    int(r.random() < 0.4),
                ),
            )

    def _focus(self, week_ids: dict[date, int]) -> None:
        tags = [t for t in TAGS if t != "SYSTEME"]
        numero = 0
        for d in self._days():
            if d.weekday() >= 5:
                continue
            wid = week_ids[d - timedelta(days=d.weekday())]
            start = datetime(d.year, d.month, d.day, 9, 0)
            for _ in range(self.rng.randint(1, 3)):
                duree = self.rng.choice([45, 60, 75, 90, 120])
                end = start + timedelta(minutes=duree)
                numero += 1
                self.conn.execute(
                    "INSERT INTO focus_sessions (numero_session, date_session, heure_debut, "
                    "heure_fin, duree_min, channel, piliers, source, semaine_id) "
                    "VALUES (?, ?, ?, ?, ?, 'demo', ?, 'manual', ?)",
                    (
                        numero,
                        d.isoformat(),
                        start.strftime("%H:%M"),
                        end.strftime("%H:%M"),
                        float(duree),
                        self.rng.choice(tags),
                        wid,
                    ),
                )
                start = end + timedelta(minutes=self.rng.choice([30, 60, 90]))

    # ── temps d'écran ────────────────────────────────────────────────────────
    def _apps(self) -> None:
        self.conn.executemany(
            "INSERT OR IGNORE INTO apps_distrayantes (package) VALUES (?)",
            [(pkg,) for pkg, _, distrayante in APPS if distrayante],
        )

    def _ecran(self, week_ids: dict[date, int]) -> None:
        for d in self._days():
            wid = week_ids[d - timedelta(days=d.weekday())]
            for pkg, nom, distrayante in APPS:
                for _ in range(self.rng.randint(1, 3)):
                    minutes = self.rng.randint(3, 22 if distrayante else 40)
                    start = datetime(d.year, d.month, d.day, self.rng.randint(7, 22), 0)
                    end = start + timedelta(minutes=minutes)
                    self.conn.execute(
                        "INSERT OR IGNORE INTO screen_sessions (package, app_name, session_start, "
                        "session_end, duration_seconds, semaine_id) VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            pkg,
                            nom,
                            start.isoformat(timespec="seconds"),
                            end.isoformat(timespec="seconds"),
                            minutes * 60.0,
                            wid,
                        ),
                    )

    # ── semaines (agrégats hebdomadaires) ────────────────────────────────────
    def _semaines(self, week_ids: dict[date, int]) -> None:
        for monday, wid in week_ids.items():
            start, end = monday.isoformat(), (monday + timedelta(days=7)).isoformat()
            v = self.conn.execute(
                "SELECT AVG(ctl), AVG(atl), AVG(tsb), SUM(tss), MAX(vo2max), SUM(distance_km), "
                "SUM(moving_time_min) FROM vigueur_entries WHERE date_entry >= ? AND date_entry < ?",
                (start, end),
            ).fetchone()
            screen = self.conn.execute(
                "SELECT COALESCE(SUM(duration_seconds), 0) / 60.0 FROM screen_sessions "
                "WHERE substr(session_start, 1, 10) >= ? AND substr(session_start, 1, 10) < ?",
                (start, end),
            ).fetchone()[0]
            top = self.conn.execute(
                "SELECT app_name, ROUND(SUM(duration_seconds) / 60.0) m FROM screen_sessions "
                "WHERE substr(session_start, 1, 10) >= ? AND substr(session_start, 1, 10) < ? "
                "GROUP BY app_name ORDER BY m DESC LIMIT 3",
                (start, end),
            ).fetchall()
            self.conn.execute(
                "UPDATE semaines_audit SET ctl = ?, atl = ?, tsb = ?, tss = ?, vo2max = ?, "
                "distance_km = ?, temps_sport_min = ?, screen_time_min = ?, top_apps_text = ?, "
                "social = ? WHERE id = ?",
                (
                    *(round(x, 1) if x is not None else None for x in v),
                    round(screen, 1),
                    ", ".join(f"{a} {int(m)}" for a, m in top),
                    "Connecté/Ressourcé" if self.rng.random() < 0.7 else "Isolé",
                    wid,
                ),
            )

    def _narratif(self, week_ids: dict[date, int]) -> None:
        for monday, wid in week_ids.items():
            if monday == self.monday or self.rng.random() < 0.25:
                continue
            self.conn.execute(
                "INSERT INTO audit_narrative (semaine_id, jauge_energie, alerte_rouge, "
                "plan_priorite_unique, jours_engagement_semaine, forge_hardskills_sujet) "
                "VALUES (?, ?, 0, ?, ?, ?)",
                (
                    wid,
                    self.rng.randint(5, 9),
                    "Terminer la maquette de l'application",
                    self.rng.choice([0, 0, 1]),
                    "Introduction aux bases de données",
                ),
            )

    # ── objectifs, tâches, plan d'entraînement ───────────────────────────────
    def _objectifs(self) -> None:
        objectifs = [
            ("Courir 10 km en moins de 50 minutes", "VIGUEUR", 1),
            ("Terminer le semestre avec mention", "LOGOS", 1),
            ("Livrer le projet de stage", "FORGE", 1),
            ("Appeler un proche chaque semaine", "RESONNANCE", 2),
            ("Automatiser la sauvegarde hebdomadaire", "SYSTEME", 3),
        ]
        for titre, pilier, prio in objectifs:
            cur = self.conn.execute(
                "INSERT INTO objectifs (titre, pilier, statut, date_cible, priorite) "
                "VALUES (?, ?, 'actif', ?, ?)",
                (titre, pilier, (self.today + timedelta(days=90)).isoformat(), prio),
            )
            for i, libelle in enumerate(
                ("Définir le plan", "Première étape", "Bilan intermédiaire")
            ):
                echeance = self.today + timedelta(days=(i - 1) * 10)
                self.conn.execute(
                    "INSERT INTO taches (titre, objectif_id, priorite, statut, date_echeance) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        libelle,
                        cur.lastrowid,
                        prio,
                        "fait" if i == 0 else "todo",
                        echeance.isoformat(),
                    ),
                )

    def _plan_entrainement(self) -> None:
        for offset in range(-7, 14):
            d = self.today + timedelta(days=offset)
            repos = d.weekday() == 6
            decharge = d >= self.monday + timedelta(weeks=1)
            self.conn.execute(
                "INSERT INTO plan_entrainement (date_jour, titre, mesocycle, type_semaine, is_repos, "
                "saison, source_csv) VALUES (?, ?, ?, ?, ?, 'Automne', 'demo')",
                (
                    d.isoformat(),
                    "Repos" if repos else "Séance endurance",
                    "M1-S4" if decharge else "M1-S3",
                    "decharge" if decharge else "charge",
                    int(repos),
                ),
            )

    # ── finances ─────────────────────────────────────────────────────────────
    def _finance(self, week_ids: dict[date, int]) -> None:
        comptes = [
            ("demo_banque", "courant", "Compte courant", "liquidites", 1800.0),
            ("demo_banque", "livret", "Livret d'épargne", "livrets", 4200.0),
            ("demo_courtier", "pea", "Plan d'épargne actions", "actions", 6500.0),
            ("demo_assureur", "assurance_vie", "Assurance vie", "fonds_euros", 3100.0),
        ]
        ids = []
        for source, type_compte, libelle, classe, solde in comptes:
            cur = self.conn.execute(
                "INSERT INTO comptes (source, type_compte, libelle, classe_actif) "
                "VALUES (?, ?, ?, ?)",
                (source, type_compte, libelle, classe),
            )
            ids.append((cur.lastrowid, solde))
        for i, (monday, wid) in enumerate(week_ids.items()):
            for cid, base in ids:
                self.conn.execute(
                    "INSERT INTO soldes_comptes (compte_id, date_snapshot, solde, semaine_id) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        cid,
                        monday.isoformat(),
                        round(base * (1 + 0.004 * i) + self.rng.uniform(-40, 40), 2),
                        wid,
                    ),
                )
        compte_courant = ids[0][0]
        modeles = [
            ("Salaire", 1650.0, "revenus"),
            ("Loyer", -520.0, "fixes"),
            ("Abonnement téléphone", -12.99, "fixes"),
            ("Courses supermarché", -64.2, "variables"),
            ("Restaurant", -28.5, "variables"),
            ("Virement vers le PEA", -150.0, "epargne_investissement"),
        ]
        for mois in range(2):
            for jour, (libelle, montant, cat) in enumerate(modeles):
                d = self.today.replace(day=1) - timedelta(days=30 * mois) + timedelta(days=jour * 4)
                self.conn.execute(
                    "INSERT OR IGNORE INTO transactions (date_op, libelle, montant, source, "
                    "compte_id, categorie) VALUES (?, ?, ?, 'demo', ?, ?)",
                    (d.isoformat(), libelle, montant, compte_courant, cat),
                )
        self.conn.executemany(
            "INSERT INTO positions_investissement (date_snapshot, compte_id, categorie, support, "
            "nb_parts, cotation, valeur, plus_value, perf_ytd, frais_pct) "
            "VALUES (?, ?, 'ETF', ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    self.today.isoformat(),
                    ids[2][0],
                    "ETF Monde (fictif)",
                    40,
                    95.0,
                    3800.0,
                    310.0,
                    "6.2%",
                    0.2,
                ),
                (
                    self.today.isoformat(),
                    ids[2][0],
                    "ETF Europe (fictif)",
                    30,
                    90.0,
                    2700.0,
                    120.0,
                    "3.1%",
                    0.25,
                ),
            ],
        )
        mois_ref = self.today.strftime("%Y-%m")
        cur = self.conn.execute(
            "INSERT INTO budgets_mensuels (mois_reference, total_revenus) VALUES (?, 1650)",
            (mois_ref,),
        )
        self.conn.execute(
            "INSERT INTO revenus_budget (budget_id, nom, montant) VALUES (?, 'Salaire', 1650)",
            (cur.lastrowid,),
        )
        self.conn.executemany(
            "INSERT INTO depenses_budget (budget_id, categorie, nom, montant, suivi_mensuel) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (cur.lastrowid, "fixes", "Loyer", 520.0, 0),
                (cur.lastrowid, "fixes", "Téléphone", 12.99, 0),
                (cur.lastrowid, "variables", "Courses", 250.0, 1),
                (cur.lastrowid, "epargne_investissement", "PEA", 150.0, 0),
            ],
        )

    # ── musculation ──────────────────────────────────────────────────────────
    def _musculation(self) -> None:
        exos = [
            ("Squat", "Jambes", "weight"),
            ("Développé couché", "Pectoraux", "weight"),
            ("Tractions", "Dos", "bw_plus_weight"),
        ]
        ex_ids = []
        for nom, cat, formule in exos:
            cur = self.conn.execute(
                "INSERT INTO exercise_library (name, category, load_formula) VALUES (?, ?, ?)",
                (nom, cat, formule),
            )
            ex_ids.append((cur.lastrowid, formule))
        tpl = self.conn.execute(
            "INSERT INTO workout_templates (name) VALUES ('Full body')"
        ).lastrowid
        for pos, (eid, _) in enumerate(ex_ids, start=1):
            te = self.conn.execute(
                "INSERT INTO workout_template_exercises (template_id, exercise_id, position) "
                "VALUES (?, ?, ?)",
                (tpl, eid, pos),
            ).lastrowid
            for idx in range(1, 4):
                self.conn.execute(
                    "INSERT INTO workout_template_sets (tmpl_exercise_id, set_index, set_type, "
                    "weight_kg, reps) VALUES (?, ?, ?, ?, 8)",
                    (te, idx, str(idx), 40.0 + 10 * pos),
                )
        for semaine_avant in (0, 1, 2):
            d = self.monday - timedelta(weeks=semaine_avant) + timedelta(days=1)
            if d > self.today:
                continue
            volume = 0.0
            sid = self.conn.execute(
                "INSERT INTO workout_sessions (date_entry, template_id, name, started_at, finished_at, "
                "bodyweight_kg) VALUES (?, ?, 'Full body', ?, ?, 72.0)",
                (d.isoformat(), tpl, f"{d}T18:00:00", f"{d}T19:00:00"),
            ).lastrowid
            for pos, (eid, formule) in enumerate(ex_ids, start=1):
                se = self.conn.execute(
                    "INSERT INTO workout_session_exercises (session_id, exercise_id, position) "
                    "VALUES (?, ?, ?)",
                    (sid, eid, pos),
                ).lastrowid
                for idx in range(1, 4):
                    poids = 40.0 + 10 * pos + 2.5 * (2 - semaine_avant)
                    charge = poids + (72.0 if formule == "bw_plus_weight" else 0.0)
                    volume += charge * 8
                    self.conn.execute(
                        "INSERT INTO workout_session_sets (session_ex_id, set_index, set_type, "
                        "weight_kg, reps, completed, load_kg) VALUES (?, ?, ?, ?, 8, 1, ?)",
                        (se, idx, str(idx), poids, charge),
                    )
            self.conn.execute(
                "UPDATE workout_sessions SET session_volume_kg = ? WHERE id = ?", (volume, sid)
            )

    # ── cursus, relations ────────────────────────────────────────────────────
    def _cursus(self) -> None:
        self.conn.execute(
            "INSERT INTO logos_gpa (id, tc_gpa, tc_uvs, branche_gpa, branche_uvs, global_gpa, "
            "global_uvs, cible_gpa, cible_uvs, cs_gpa, cs_uvs, tm_gpa, tm_uvs, tsh_gpa, tsh_uvs, "
            "semestres_passes, updated_at) "
            "VALUES (1, 3.4, 12, 3.1, 8, 3.25, 20, 3.5, 60, 3.3, 6, 3.2, 6, 3.0, 4, 3, datetime('now'))"
        )
        catalogue = [
            ("MA01", "Mathématiques 1", "CS", 6),
            ("PH02", "Physique générale", "CS", 6),
            ("IN03", "Algorithmique", "TM", 6),
            ("LA04", "Langue vivante", "TSH", 4),
        ]
        self.conn.executemany(
            "INSERT INTO cours_ecole (semestre, code, intitule, type_uv, credits) "
            "VALUES (NULL, ?, ?, ?, ?)",
            catalogue,
        )
        self.conn.executemany(
            "INSERT INTO cours_ecole (semestre, code, intitule, type_uv, credits, note, en_cours, valide) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("Semestre 1", "MA01", "Mathématiques 1", "CS", 6, "B", 0, 1),
                ("Semestre 2", "PH02", "Physique générale", "CS", 6, "A", 0, 1),
                ("Semestre 3", "IN03", "Algorithmique", "TM", 6, None, 1, 0),
            ],
        )

    def _relations(self) -> None:
        for prenom, liens, prox in (("Alex", "Amis", 80), ("Sam", "Famille", 65)):
            pid = self.conn.execute(
                "INSERT INTO npt_personnes (prenom, liens, proximite) VALUES (?, ?, ?)",
                (prenom, liens, prox),
            ).lastrowid
            self.conn.execute(
                "INSERT INTO npt_notes (personne_id, date_note, contenu) VALUES (?, ?, ?)",
                (pid, self.today.isoformat(), "Penser à reprendre des nouvelles ce week-end."),
            )

    # ── projet, profil ───────────────────────────────────────────────────────
    def _projet(self) -> None:
        pid = projets.creer_projet(
            "Application de suivi de randonnées",
            "Projet fictif : une petite application web pour planifier ses sorties.",
        )
        specs = [
            (
                "Cadrage",
                "Définir le besoin",
                "Valider la liste des fonctionnalités",
                [True, True, True],
            ),
            (
                "Maquettes",
                "Dessiner les écrans principaux",
                "Terminer l'écran de carte",
                [True, False, False],
            ),
            (
                "Réalisation",
                "Développer la première version",
                "Initialiser le dépôt",
                [False, False],
            ),
        ]
        for titre, objectif, suite, taches in specs:
            ph = projets.ajouter_phase(
                pid, titre, objectif, suite, [("Remarque", "Exemple de note de phase.")]
            )
            for i, fait in enumerate(taches, start=1):
                projets.ajouter_tache(ph, f"Tâche {i} — {titre.lower()}", fait)

    def _profil(self) -> None:
        d = self.today
        set_profile("logos.cursus_titre", "Cursus (exemple)")
        set_profile("forge.objectif_pro_titre", "Livrer le projet de stage")
        set_profile("vigueur.objectif_course", "Objectif fictif : 10 km en moins de 50 min")
        set_profile("vigueur.vo2max_actuel", 52.0)
        set_profile(
            "vigueur.macro_cycle",
            [
                {"Phase": "Base", "Début": (d - timedelta(days=60)).isoformat(),
                 "Fin": (d - timedelta(days=15)).isoformat(), "Focus": "Volume aérobie"},
                {"Phase": "Spécifique", "Début": (d - timedelta(days=14)).isoformat(),
                 "Fin": (d + timedelta(days=45)).isoformat(), "Focus": "Allure cible"},
                {"Phase": "Affûtage", "Début": (d + timedelta(days=46)).isoformat(),
                 "Fin": (d + timedelta(days=75)).isoformat(), "Focus": "Fraîcheur"},
            ],
        )  # fmt: skip
        set_profile(
            "logos.plan_carriere",
            {
                "titre": "Plan de carrière (exemple)",
                "sous_titre": "Données fictives de démonstration",
                "meta": ["**Horizon** : 3 ans", "**Domaine** : développement logiciel"],
                "encart": {"titre": "Principe", "texte": "Avancer par petites étapes mesurables."},
                "sections": [
                    {
                        "titre": "Étapes",
                        "intro": ["Trois jalons pour les trois prochaines années."],
                        "blocs": [
                            {
                                "type": "bullets",
                                "items": [
                                    ["Année 1", "Valider le diplôme et un premier stage"],
                                    ["Année 2", "Spécialisation et projet personnel"],
                                    ["Année 3", "Premier poste"],
                                ],
                            },
                            {
                                "type": "table",
                                "titre": "Compétences visées",
                                "rows": [
                                    {"Compétence": "Python", "Niveau": "Avancé"},
                                    {"Compétence": "Bases de données", "Niveau": "Intermédiaire"},
                                ],
                            },
                        ],
                    }
                ],
                "citation": "La régularité bat l'intensité.",
            },
        )
        set_profile(
            "audit.forge_pro_labels",
            ["Livrable 1 — avancement", "Livrable 2 — avancement", "Livrable 3 — avancement"],
        )
