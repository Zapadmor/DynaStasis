# Configuration

Trois niveaux, tous facultatifs :

| Fichier | Contenu | Versionné ? |
|---|---|---|
| `~/.config/dynastasie/secrets.env` | clés d'API des sources | non (hors dépôt) |
| `config/user.toml` | fuseau horaire, modes, seuils et poids du score, piliers | non (ignoré par git et par Docker) |
| table `profil_contenu` | textes personnels : plan de carrière, phases d'entraînement… | non (dans la base) |

## secrets.env

```bash
mkdir -p ~/.config/dynastasie
cp secrets.env.example ~/.config/dynastasie/secrets.env
chmod 600 ~/.config/dynastasie/secrets.env
```

Chemin personnalisable avec `DYNASTASIS_ENV_FILE`. Convention : la variable est `SECTION_CLE` en majuscules. Ordre de résolution : variables d'environnement, puis ce fichier.

### Intervals.icu (sport, HRV, sommeil, pas)

1. Créez un compte sur [intervals.icu](https://intervals.icu) et connectez votre montre ou Strava.
2. *Settings → Developer Settings* : générez une clé d'API ; l'identifiant d'athlète (`i123456`) est dans l'URL de vos réglages.
3. Renseignez `INTERVALS_ICU_ATHLETE_ID` et `INTERVALS_ICU_API_KEY`, puis `python main.py vigueur`.

Après une absence : `python main.py vigueur --full --lookback 365`.

### Strava (records personnels)

1. Créez une application sur <https://www.strava.com/settings/api> (domaine de rappel : `127.0.0.1`, le port 8080 doit être libre pendant l'autorisation).
2. Renseignez `STRAVA_CLIENT_ID` et `STRAVA_CLIENT_SECRET`.
3. `python main.py strava-auth` ouvre l'autorisation (scope `activity:read_all`) et enregistre les jetons, ensuite renouvelés automatiquement.

### Temps d'écran Android (ADB)

Activez le *Débogage sans fil* ([documentation Android](https://developer.android.com/tools/adb#connect-to-a-device-over-wi-fi)), renseignez `SAMSUNG_ADB_HOST` (adresse IP du téléphone) et `SAMSUNG_ADB_PORT` (5555 par défaut), puis `python main.py logos`. `adb` doit être installé. L'image Docker par défaut ne l'inclut **pas** : construisez la variante `adb` avec `DYNASTASIS_TARGET=adb docker compose up -d --build` (ou `docker build --target adb .`). Sans `adb`, `main.py logos` l'indique et propose la saisie manuelle.

**Sans téléphone** : `python main.py logos --manual` demande le temps d'écran total et les applications principales.

Les applications comptées comme « distractives » sont les lignes de la table `apps_distrayantes` (colonne `package`) ; éditez-la dans la page *Système → SQL*.

### Calendrier

`CALENDAR_SRC` : adresse du calendrier Google à intégrer (Google Agenda → Paramètres du calendrier → *Intégrer l'agenda*). Vide, l'onglet *Emploi du temps* reste muet.

### Finances

Aucun secret. Déposez vos exports CSV/XLSX dans `data/inbox/<banque>/` (une analyse par banque : voir l'en-tête de `src/collectors/finance_collector.py`), avec un `soldes.yaml` par source, plus `data/budget.yaml` (budget théorique) et `data/categories.yaml` (catégorisation) ; `data/` est ignoré par git. Puis `python main.py finance`. Sans ces fichiers, l'onglet Finance de la page Forge reste utilisable en saisie manuelle.

## user.toml

```bash
cp config/user.toml.example config/user.toml
```

Chemin personnalisable avec `DYNASTASIS_CONFIG`. Le fichier est lu au démarrage de l'application (redémarrez après modification) ; les seuils sont recopiés dans la base à chaque `init-db`/démarrage, car les vues SQL du score les utilisent. Toute clé absente garde sa valeur par défaut ; une clé inconnue ou invalide arrête le démarrage avec un message explicite.

| Section | Rôle |
|---|---|
| `[general] timezone` | fuseau IANA (`Europe/Paris`, `America/Montreal`…) : « aujourd'hui », chrono focus, calendrier |
| `[interface] widget_url` | widget externe (iframe) en bas de la barre latérale ; vide = aucun |
| `[piliers] actifs` | pages affichées et axes du radar |
| `[engagement]` | critère optionnel : `actif`, `libelle` (nom affiché), `libelle_jours` |
| `[modes.<code>]` | rythmes de vie : `label`, `focus_jour_min`, `focus_semaine_min`, `tag_pro`, `couleur` |
| `[seuils.jour]`, `[seuils.semaine]` | seuils des 6 critères quotidiens et des 10 critères hebdomadaires |
| `[poids]` | poids de chaque critère dans le score hebdomadaire ; `0` le désactive |

### Modes

Un mode décrit un rythme (études, entreprise, vacances…) avec ses propres objectifs de focus. La clé de la section (`ecole`, `entreprise`) est le **code stocké en base** : ne la renommez plus une fois des semaines enregistrées ; le libellé affiché (`label`) se change librement. Le premier mode s'applique aux semaines sans séquence. `tag_pro = true` propose le sous-tag « Forge — Entreprise » dans ce mode. Si vous retirez un mode utilisé par d'anciennes semaines, elles retombent sur les seuils par défaut (`focus_defaut_min`).

### Critère « engagement »

Une pratique régulière à suivre à part (bénévolat, club, association, service…). Validé quand le focus taggé « Forge — *libellé* » atteint `engagement_min` **ou** que le nombre de jours d'engagement saisis dans l'audit hebdomadaire atteint `engagement_jours`. Avec `actif = false`, il disparaît du score, du formulaire d'audit et des tags.

### Score pondéré

`score = 100 × Σ(critère validé × poids) / Σ(poids)`. Avec les poids par défaut (tous à 1), chaque critère vaut 10 points. Mettre un poids à `0` retire le critère et renormalise le score. Les scores sont recalculés à la volée : changer un seuil modifie **rétroactivement** tout l'historique affiché (les scores stockés par la cascade sont rafraîchis à la prochaine saisie).

## Contenu de profil

Les textes personnels vivent dans la base (table `profil_contenu`), jamais dans le code. Les écrans affichent un état vide tant qu'une clé n'est pas renseignée.

```bash
python main.py profile export mon_profil.json
python main.py profile import mon_profil.json
```

| Clé | Contenu |
|---|---|
| `logos.cursus_titre` | titre de l'onglet Cursus |
| `logos.plan_carriere` | plan (titre, sections, blocs `bullets`/`paragraphs`/`cards`/`table`, citation) |
| `vigueur.macro_cycle` | liste de phases `{Phase, Début, Fin, Focus}` |
| `vigueur.objectif_course` / `vigueur.vo2max_actuel` | objectif affiché / VO2max de repli |
| `forge.objectif_pro_titre` | titre de l'objectif suivi en mode pro |
| `audit.forge_pro_labels`, `audit.alignement_*` | libellés du formulaire d'audit |

`python main.py seed-demo` donne un exemple complet de chaque clé (voir `src/core/demo.py`).
