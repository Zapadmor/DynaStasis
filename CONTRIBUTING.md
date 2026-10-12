# Contribuer

Merci de votre intérêt ! Ce document décrit l'environnement de développement et le flux de contribution.

## Environnement

```bash
python3 -m venv env && source env/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pre-commit install                 # reformate et vérifie à chaque commit
python main.py seed-demo           # base de démo pour tester l'interface
DYNASTASIS_DB=data/demo/dynastasie-demo.db python main.py app
```

Python 3.12 (`.python-version`). N'utilisez jamais vos vraies données dans les tests, fixtures ou captures : travaillez sur la base de démo.

## Avant chaque commit

```bash
ruff check src bots scripts main.py tests
ruff format src bots scripts main.py tests
vulture src bots main.py --min-confidence 80      # code mort
pytest -q                                          # ajouter --cov pour la couverture
```

La CI rejoue exactement ces contrôles, plus la construction de l'image Docker. Les hooks `pre-commit` reformatent les fichiers : si un commit échoue après reformatage, ajoutez les fichiers modifiés (`git add`) et recommencez.

## Tests

- Les tests utilisent des bases SQLite temporaires (fixtures `db` et `demo_db` de `tests/conftest.py`) ; aucun test ne touche `db/dynastasie.db`.
- Un service se teste par ses fonctions pures puis avec la fixture `db` ; un repository avec la fixture `conn` (voir `tests/test_services_*.py`).
- Les pages Streamlit se testent avec `streamlit.testing.v1.AppTest` (voir `tests/test_pages.py`, `tests/test_sans_source.py`).
- Une règle de scoring ou une migration modifiée doit s'accompagner d'un test.

## Architecture du code

Trois couches, du rendu vers les données (détail dans [docs/architecture.md](docs/architecture.md#couches)) :

- **vue** (`src/app/views/`) : rendu Streamlit et saisie ; ni SQL ni règle métier ;
- **service** (`src/services/`) : règles de gestion ; ouvre `db_session()` et appelle les repositories ; les calculs purs sont des fonctions à part, testables sans base ;
- **repository** (`src/repositories/`) : SQL pur, `conn` en premier argument, renvoie des `dict` ; pas de Streamlit, pas de `commit`.

Les vues volumineuses sont des paquets (un module par onglet, `__init__.py` expose `render`). Pour **ajouter un pilier**, voir [docs/piliers.md](docs/piliers.md#ajouter-un-pilier). Pour déplacer du code existant vers ces couches, faites deux commits : un de déplacement pur, un de nettoyage.

## Migrations de base

`db/schema.sql` est le schéma de base ; toute évolution de **table** passe par une migration numérotée, sans modifier les migrations déjà publiées.

1. Créez `db/migrations/NNN_description.sql` (numéro suivant, sans trou). Si le SQL ne suffit pas (reconstruction de table, conversion de données), un fichier `NNN_description.py` définissant `apply(conn)` est accepté.
2. Rendez-la **idempotente** : un `ALTER TABLE ... ADD COLUMN` déjà appliqué est ignoré, un renommage se garde par un test d'existence.
3. Ajoutez un test dans `tests/test_migrations.py` (base vide → dernière version, ancienne base → dernière version).
4. Essayez-la sur une **copie** de votre base réelle : `DYNASTASIS_DB=/chemin/copie.db python main.py init-db`, puis comparez effectifs et scores.

Les vues sont recréées à chaque démarrage : modifier une vue ne demande pas de migration.

## Flux de contribution

1. Une branche par sujet, depuis `main` : `feat/...`, `fix/...`, `docs/...`, `chore/...`, `test/...`.
2. Commits atomiques au format `type(portée): message` en français, à l'impératif ou au présent :
   `feat(demo): ajoute la commande seed-demo`, `fix(journal): colonne Score homogène`, `docs(readme): précise le démarrage Docker`.
   Types : `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `ci`, `perf`.
3. Ouvrez une pull request vers `main` avec un résumé et la manière dont vous avez vérifié.
4. La CI doit être verte ; la fusion se fait par *squash*, la branche est supprimée.
5. Jamais de push direct sur `main`, de *force-push* ni de réécriture d'historique.

## Conventions de code

- Écrivez dans le style du module que vous modifiez (commentaires et noms en français pour le domaine, anglais pour l'infrastructure).
- Pas de donnée personnelle dans le code, les tests, les docs ou les messages de commit ; le contenu personnel vit dans la base (`profil_contenu`) ou dans `config/user.toml`.
- Les seuils et libellés configurables vont dans `src/core/user_config.py` **et** `config/user.toml.example` (un test vérifie qu'ils restent identiques).
- Dépendances : modifiez `requirements.in` (ou `requirements-dev.in`) puis régénérez le lockfile avec `pip-compile --strip-extras -o requirements.txt requirements.in`.

## Documentation

Mettez à jour `docs/` et `CHANGELOG.md` (section « Non publié ») quand le comportement visible change. Les captures d'écran doivent venir de la base de démo.
