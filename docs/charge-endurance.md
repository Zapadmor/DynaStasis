# Charge d'endurance locale : reconstruction et comparaison à Intervals.icu

Rapport de la phase 2. Agrégats uniquement : aucun identifiant d'activité, aucune date, aucune valeur
physiologique personnelle. Les données de travail (flux, .fit) restent hors du dépôt.

Périmètre : 268 activités sur environ 8 mois, 247 avec une charge Intervals non nulle, 21 sans FC donc sans charge.
Le code est dans `src/core/charge/endurance.py` ; il n'est appelé par aucune page ni synchro.
**La source de vérité reste Intervals.icu** : rien n'est basculé.

## 1. Faits vérifiés sur l'export Intervals

- Pour les 247 activités chargées, `icu_training_load == hr_load` (±1) ; `power_load` est vide ; `pace_load` n'existe que
  pour 6 activités ; aucun seuil de course (FTP ou allure seuil) n'est défini pour la course.
- **L'ATL d'Intervals suit exactement l'EWMA des notes** (écart max 7e-6 avec `wellness`).
- **Le CTL d'Intervals ne la suit pas** si l'on y met toute la charge : écart RMSE 7,65 points, max 11,4, sur 244 jours.
  Cause identifiée : la charge « CTL » du `wellness` (`ctlLoad`) est la somme des charges des activités **hors types
  `Workout` et `WeightTraining`** (0 écart sur 244 jours), alors que la charge « ATL » (`atlLoad`) les inclut toutes.
  Avec cette règle, le rejeu reproduit `vigueur_entries` à 0,003 point (CTL, ATL).
  Je ne sais pas si c'est un réglage de l'athlète ou un comportement par défaut d'Intervals ; c'est une constatation sur
  cet export, pas une règle des notes de référence.
- **Convention du TSB** : `vigueur_entries.tsb` = CTL - ATL **du même jour** (écart max 0,98, arrondi à l'entier),
  pas CTL(d-1) - ATL(d-1) comme l'écrivent les notes (écart max 19 points). `pmc()` propose les deux (`tsb_veille`).

## 2. HRSS : variantes testées (246 séances, hors l'aberrante)

Erreur relative à `icu_training_load` : médiane, ratio moyen (local / Intervals), 90e centile, max, part des séances à ±1 point.

| Variante | Médiane | Ratio moyen | P90 | Max | ±1 pt |
| --- | --- | --- | --- | --- | --- |
| A dt = 1 s par échantillon, FC > 0 | 2,73 % | 1,056 | 16,0 % | 234 % | 76,8 % |
| B dt réel brut (trous jusqu'à 43 s inclus) | 2,96 % | 1,064 | 18,5 % | 234 % | 74,8 % |
| C dt réel plafonné à 5 s | 2,62 % | 1,058 | 16,9 % | 234 % | 77,6 % |
| D C + FC repos fixe de l'athlète | 3,81 % | 1,039 | 13,2 % | 232 % | 74,0 % |
| E C + FC repos fixe 55 | 3,80 % | 1,000 | 15,5 % | 223 % | 70,3 % |
| F C + b = 1,67 | 7,78 % | 1,139 | 29,7 % | 255 % | 45,5 % |
| G C + b = 2,0 | 3,39 % | 1,034 | 15,4 % | 228 % | 80,9 % |
| H C + FC max - 5 | 3,19 % | 1,038 | 15,5 % | 229 % | 80,9 % |
| I C + FC max + 5 | 3,02 % | 1,077 | 19,7 % | 239 % | 72,0 % |
| J C + ignorer HRR < 0,2 | 2,67 % | 1,050 | 16,6 % | 233 % | 77,2 % |
| K C + lissage FC 10 s | 2,60 % | 1,057 | 17,0 % | 234 % | 77,6 % |
| L C + échelle moving / recording | 3,05 % | 1,001 | 16,8 % | 183 % | 76,0 % |
| **M C + exclure les secondes à l'arrêt (v < 0,1 m/s)** | **2,34 %** | **1,003** | 16,0 % | **47 %** | **80,5 %** |
| N C + exclure v < 0,5 m/s | 2,82 % | 0,988 | 18,6 % | 56 % | 77,6 % |
| O C + exclure v < 1,0 m/s | 3,08 % | 0,948 | 21,9 % | 98 % | 74,4 % |

Retenue : M (TRIMP de Banister par seconde, b = 1,92, y = 0,64, FC repos de l'activité, FC nulle ignorée, arrêt exclu
si le flux de vitesse existe, normalisé par 1 h à la FC seuil). Sur les séances de charge >= 20, la médiane tombe à 1,6 %.

- Les secondes à l'arrêt font passer le max de 234 % (hors aberrante) à 47 % : Intervals n'intègre pas les pauses,
  mais pas non plus via le simple ratio moving / recording (variante L, moins bonne).
- b = 1,92 est nettement meilleur que 1,67 ; la FC repos propre à l'activité est meilleure qu'une valeur fixe.
- Le reste de l'écart n'est pas expliqué : ratio médian 0,93 sur les randonnées, 0,99 sur la course, quelques marches
  à faible charge (3 à 6 points) où l'arrondi à l'entier d'Intervals pèse beaucoup.
  Les deux sources ne coïncident pas exactement : 68 % des séances à moins de 5 %, 81 % à moins de 10 %.

### Séance aberrante (ratio 0,47)

La FC n'est valide que sur environ 23 % de la séance : cycles réguliers d'environ 33 s de FC valide pour 54 s de
valeur absente (formats FIT et flux concordent). Le HRSS local sur les seules secondes valides vaut 35 pour 74 chez
Intervals ; l'interpolation de tous les trous donne environ 89. Intervals se situe entre les deux.
**Je ne sais pas comment Intervals traite ce cas** : d'autres séances avec 60 à 90 % de FC absente (en début de
séance) sont reproduites au ratio 1, donc un trou intérieur périodique est traité autrement. La FC brute RR (flux
`hrv`) n'est pas dans l'archive. Effet : CTL RMSE 0,69 -> 0,60 et max 1,5 -> 1,47 si cette séance est remplacée par la
valeur Intervals.

## 3. Puissance et allure (courses uniquement : les flux de puissance n'existent que pour Run / TrailRun)

Seuils **estimés** (aucun seuil de course dans Intervals) :

- Puissance critique (CP) : régression travail-durée sur les meilleures puissances moyennes (3, 5, 12, 20 min) de
  toutes les courses avec puissance. Variante 5-20 min : environ 3 % plus basse. Marquée « estimé ».
- Vitesse seuil : points 5 km / 10 km des meilleurs efforts relevés dans les flux (concordent avec
  `vigueur_personal_records` à 0,05 % sur le 5 km, 1,4 % sur le 10 km) -> vitesse critique CS et D', puis
  vitesse « 1 h » = CS + D' / 3600. Marquée « estimé ». Option plus basse : CS seule.
- NP : moyenne glissante 30 s puis moyenne d'ordre 4. NGP : même opération sur la vitesse ajustée à la pente par le
  polynôme de coût de Minetti et al. (2002), qui n'est **pas** le modèle Strava utilisé par Intervals pour son GAP.

Reproductibilité : deux exécutions donnent des valeurs identiques (test sur les trois méthodes).

### Comparaison sur le recouvrement (80 courses avec FC, watts et vitesse)

| Paire | Corrélation | Ratio médian | Dispersion (MAD du ratio) |
| --- | --- | --- | --- |
| puissance / HRSS | 0,54 (Run : 0,61) | 1,27 | 23 % |
| allure / HRSS | 0,68 | 1,55 | 25 % |
| allure / puissance | 0,94 (Run : 0,98) | 1,21 | 2 % |

- Allure et puissance sont quasi redondantes (puissance de montre dérivée de la vitesse et de la pente, selon toute
  vraisemblance : inférence, non vérifiée). Elles ne fournissent donc pas deux avis indépendants.
- Les deux surestiment l'HRSS d'un facteur dépendant des seuils estimés (0,79 en HRSS/TSS puissance, 0,65 en
  HRSS/pace TSS) : ce facteur absorbe l'erreur de seuil. La dispersion résiduelle (17 à 23 %) vient surtout des séances
  faciles de faible charge, où le TSS (en carré de l'intensité) et le TRIMP exponentiel se séparent, et de séances où
  la FC ou la puissance est dégradée. Corrélation du ratio puissance/HRSS avec la durée : 0,16 ; avec la FC moyenne : -0,35.
- Prédiction d'une charge Intervals par la puissance recalée (validation croisée, 1 séance exclue) : erreur absolue
  médiane 7,6 points, 90e centile 38 points. Allure recalée : 6,4 et 35 points. **C'est large** pour des séances de
  charge typique 20-60.

### Comblement des 21 séances sans FC

- 13 sont des courses : 11 estimables par la puissance recalée, 2 par l'allure moyenne (flux presque vides, estimation
  plus grossière). Charges estimées : de 7 à 43 points, 292 points au total (environ 4 % de la charge totale).
- 8 ne sont pas estimables : sortie vélo, 4 séances « Workout » sans signal, 2 randonnées, 1 marche. Il n'y a ni
  puissance ni seuil de marche/randonnée pour les calibrer ; elles restent à 0 (ou à fixer par l'utilisateur).
- Incertitude : de l'ordre de plus ou moins 8 points (médiane) et plus ou moins 38 points (90e centile) par séance,
  d'après la validation croisée ci-dessus, à lire comme une estimation « faible/moyenne confiance ».

## 4. Courbes CTL / ATL / TSB (graine 0, EWMA k = 1 - exp(-1/tau), tau = 42 et 7)

Écarts à `vigueur_entries` sur 244 jours (accord de zone : zones de l'application) :

| Variante | CTL RMSE / max | ATL RMSE / max | TSB RMSE / max | Zone TSB |
| --- | --- | --- | --- | --- |
| Charges Intervals, formule des notes (tout dans le CTL, TSB veille) | 7,65 / 11,4 | 0,003 / 0,005 | 8,39 / 25,6 | 56,0 % |
| Charges Intervals, CTL hors Workout/WeightTraining (contrôle) | 0,003 / 0,005 | 0,003 / 0,005 | 0,41 / 0,98 | 98,4 % |
| HRSS local (même règle de CTL) | 0,69 / 1,55 | 1,39 / 5,42 | 1,08 / 3,81 | 96,3 % |
| HRSS local + comblement | 0,73 / 3,89 | 2,53 / 14,9 | 1,91 / 10,7 | 94,2 % |
| HRSS local, tout dans le CTL | 7,49 / 12,0 | 1,39 / 5,42 | 7,91 / 12,8 | 53,5 % |

- Le contrôle sur les charges Intervals reproduit `vigueur_entries` : l'écart TSB résiduel (0,98) est l'arrondi à
  l'entier ; les 4 jours de désaccord de zone sont des cas limites d'arrondi.
- La ligne « comblement » s'éloigne d'Intervals **par construction** (Intervals compte ces séances à 0) : elle ne se
  valide pas contre lui. Le comblement ajoute environ 4,6 points au CTL final et jusqu'à 15 points d'ATL ponctuels.

## 5. Critère d'acceptation proposé (à valider par l'utilisateur, non modifié)

Écart médian par séance < 5 %, RMSE du CTL < 1 point, TSB dans la même zone plus de 90 % des jours.

- HRSS local, règle de CTL d'Intervals : **atteint** (2,3 %, 0,69 point, 96,3 %).
- HRSS local + comblement : atteint contre Intervals (0,73 point, 94,2 %) mais sans valeur probante, voir ci-dessus.
- HRSS local avec la formule des notes (tout dans le CTL) : **non atteint** (RMSE 7,5). Le critère n'est donc atteint
  que si l'on reproduit l'exclusion des séances de type Workout / WeightTraining du CTL.

## 6. Décisions qui reviennent à l'utilisateur

1. **Règle du CTL** : (a) reproduire Intervals (exclure Workout et WeightTraining du CTL, garder dans l'ATL) -> continuité
   avec les courbes actuelles, mais règle opaque et non documentée ; (b) tout inclure (formule des notes) -> cohérent
   avec la théorie et avec un futur axe force, mais le CTL s'écarte des courbes Intervals actuelles d'environ 7,5 points (RMSE).
2. **Convention du TSB** : même jour (comme l'existant) ou veille (comme les notes).
3. **Seuils estimés** pour puissance et allure : (a) estimation depuis les meilleurs efforts, marquée « estimé »
   (reproductible, mais sensible à la qualité de la meilleure performance) ; (b) saisie manuelle ; (c) ignorer
   puissance et allure, ne combler aucune séance.
4. **Estimateur fusionné** : FC, puis puissance recalée, puis allure recalée (`charge_locale`, non adopté). Avantage :
   plus aucune séance de course à 0. Inconvénients : puissance et allure redondantes, incertitude large par séance,
   et le CTL de référence monte. Alternative : garder la FC seule et signaler les séances sans FC comme « inconnues ».

## 7. Limites

- Une seule personne, un seul capteur de FC dominant, un seul export : pas de validation croisée sur d'autres athlètes.
- Les reproductions du HRSS sont calibrées sur les mêmes 247 séances que celles de l'évaluation (choix de variante) ;
  le risque de sur-ajustement est faible (peu de paramètres) mais non nul.
- Le polynôme de Minetti n'est pas le GAP d'Intervals ; la NGP locale n'est donc pas celle d'Intervals.

## 8. Intégration (sans effet par défaut)

- `endurance.hrss`, `power_tss`, `pace_tss`, `critical_power`, `critical_speed`, `pmc`, `pmc_intervals`, `charge_locale`.
- Migration additive `db/migrations/014_charge_locale.sql` : table `charge_locale` (charge, méthode, confiance, estimé,
  version de l'algorithme). Non appliquée à la base réelle ; `stockage.py` écrit et lit cette table.
- Tests : `tests/test_charge_endurance.py`, données synthétiques uniquement.
