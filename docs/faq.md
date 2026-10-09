# FAQ

**Dois-je configurer des clés d'API pour essayer ?**
Non. `python main.py seed-demo` charge des données fictives, et l'application fonctionne sans aucune source.

**Mes données quittent-elles ma machine ?**
Non, sauf les appels que vous activez vous-même (Intervals.icu, Strava) et le widget facultatif `[interface] widget_url`. Tout est stocké dans un fichier SQLite local.

**Je n'ai pas de montre ni de compte Intervals.icu.**
Les critères Vigueur resteront à zéro. Vous pouvez désactiver ces critères (`poids = 0`) ou masquer la page (`[piliers]`), le score se renormalise.

**Comment suivre mon temps d'écran sans Android ?**
`python main.py logos --manual` : saisie du total et des applications principales.

**Comment changer le fuseau horaire ou les seuils ?**
Dans `config/user.toml` ([configuration](configuration.md)), puis redémarrez l'application.

**Mon score a changé tout seul après une modification de seuil.**
C'est voulu : les scores sont recalculés à la volée sur tout l'historique. Les semaines gelées ne comptent pas.

**Je veux renommer « École » / « Entreprise ».**
Changez `label` dans `[modes.*]`. Ne changez pas la clé de section (le code) si des semaines existent déjà.

**Je ne suis pas concerné par le critère « engagement ».**
`[engagement] actif = false` : il disparaît du score, du formulaire d'audit et des tags.

**Comment repartir de zéro ?**
Arrêtez l'application, supprimez `db/dynastasie.db` (après sauvegarde), puis `python main.py init-db`.

**Comment migrer vers une nouvelle version ?**
`git pull`, puis relancez : les migrations s'appliquent au démarrage. Sauvegardez `db/dynastasie.db` avant une montée de version.

**`seed-demo` peut-il écraser mes données ?**
Non : il refuse d'écraser `db/dynastasie.db` et toute base qui contient des données non issues de la démo, sauf option explicite `--base-reelle`.

**Où signaler un problème ?**
Dans les *issues* du dépôt ; voir [CONTRIBUTING](../CONTRIBUTING.md).
