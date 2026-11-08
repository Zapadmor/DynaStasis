# Coût physiologique de la force (axe force) et readiness

Code : `src/core/charge/force.py` (coût d'une séance), `src/core/charge/readiness.py` (deux axes + HRV).
Tests : `tests/test_charge_force.py`, `tests/test_charge_readiness.py`.

**Statut : modèle de travail, non validé.** Aucune vérité terrain locale (ni CMJ, ni capteur de vitesse,
ni mesure d'HRV post-séance rattachée à une séance). Toutes les constantes ci-dessous sont des
**hypothèses**, sauf indication contraire. Les valeurs sont en « UA » (unités arbitraires), pas
comparables telles quelles à un TSS d'endurance.

## 1. Ce qui est reconstruit

Les formules de `Quantification Charge Entraînement Force.md` (sections 1.2 et 5.3) sont des images
(`![][imageNN]`) illisibles. Reconstruit depuis le texte : la **structure** « masse systémique ×
tonnage pondéré par l'intensité relative × multiplicateur exponentiel de VL × modérateur subjectif ».
Le texte ne chiffre ni l'exposant de l'intensité, ni la constante `k` de l'exponentielle, ni le
modérateur : ce sont des choix de l'implémentation. Le modérateur subjectif n'est pas repris (le RPE
sert déjà à estimer la VL, l'appliquer deux fois serait un double compte).

## 2. Modèle

Par série de travail validée (les séries `W` d'échauffement sont ignorées) :

```
coût_série = charge_systémique × reps × rep_factor × I^2 × M(VL) × 10 / 1000
```

- **Charge systémique** : `load_kg` stocké (lest + poids du corps × `bw_fraction`). Repli : recalcul
  depuis `weight_kg`, `bodyweight_kg`, `load_formula`, `bw_fraction`. Écart avec le doc (De Leva :
  0,955 traction, 0,98 dips, 0,88 squat) : la bibliothèque porte `bw_fraction` (1,0 pour la plupart) ;
  l'écart est de 2 à 5 % sur la charge d'une traction ou d'un dip. Non corrigé (choix de l'utilisateur).
- **Intensité relative `I = charge / e1RM`**, bornée à [0,30 ; 1]. e1RM = Epley `charge × (1 + (reps+RIR)/30)`,
  meilleure série de l'exercice **dans la séance** (reps <= 12), ou `e1rm_kg` fourni par l'appelant.
  Limite majeure : un e1RM estimé dans la séance rend `I` dépendant des seules répétitions (3x5 léger
  et 3x5 lourd ont le même `I`) ; c'est le tonnage en kg qui distingue les deux. Fournir un e1RM
  historique (maximum glissant par exercice) corrigerait cela. Poids `I^2` : hypothèse.
- **Multiplicateur `M(VL)`** = `(1 + 0,25 × min(VL, 20 %)/20 %) × exp(5 × max(0, VL − 20 %))`.
  Valeurs : VL 0 / 10 / 20 / 30 / 40 / 50 % -> 1,0 / 1,12 / 1,25 / 2,06 / 3,4 / 5,6.
  Le seuil de 20 % vient du doc ; `k = 5` et le gain de 25 % sont des choix.
- **Source de VL, par ordre** : (1) `vl` mesuré ou durées concentriques (`VL ≈ 1 − t_première/t_dernière`,
  proxy temporel du second document, trajectoire supposée constante) ; (2) RPE : `RIR = 10 − RPE`, puis
  table RIR -> VL (RIR 0 / 2 / 4 = 40 / 22,5 / 12,5 %, milieux des fourchettes du doc ; RIR 6 -> 5 % et
  RIR 10 -> 0 % **extrapolés**) ; (3) série de type `F` : échec supposé (RIR 0) ; le sens de `F` n'est
  documenté nulle part dans la base, **hypothèse** ; (4) RIR par défaut 3 (VL ≈ 17,5 %).
  La table RIR -> VL du doc concerne des charges lourdes ; elle est appliquée à toutes les charges.
- **Dernier repli, sRPE** : si aucune série ne produit de coût, `durée (min) × RPE de séance × 0,14`
  (RPE par défaut 6). Sans durée : 0, méthode `aucune`.
- **Isométrie** (`unit = sec`, ou `rep_factor = 0` avec `duration_s`) : durée sous tension (s), coût
  `3 UA/min × (RPE/10 ou 0,7)^2`. Pas de FTI (aucune force mesurée). `rep_factor = 0` sans durée : exclu du
  volume et signalé (`iso_sans_duree`).
- **EMOM** : demi-vie de resynthèse de la PCr 30 s (doc : 21-57 s, ~72 % resynthétisés en 55 s ; 30 s
  reproduit ce chiffre). Déficit `D <- (D + 1) × 2^(-repos/30)` ; coût multiplié par `1 + 0,5 × D`, **seulement**
  pour les séries sans RPE ni VL (sinon l'effort est déjà capté). Intervalle par défaut 60 s.
- **Sortie** : `force_load(session) -> float` ; `force_load_detail` renvoie valeur, méthode (`vbt`, `rpe`,
  `type_f`, `defaut`, `mixte`, `isometrie`, `srpe`, `aucune`), confiance (élevé si >= 80 % du coût vient de
  VL mesurée ; moyen si >= 50 % vient de VL ou RPE ; sinon faible), part « neurale » (sans `M`), durée
  isométrique, drapeaux d'anomalie.

Exemples (e1RM fixé à 100, UA) : 1x95 % RPE 9 -> 1,9 ; 15x65 % RPE 9 -> 9,0 ; 10x1 à 95 % RPE 6 -> 9,9.
Sans information d'effort, 10x1 à 95 % -> 10,4 contre 5,0 pour 15x65 % (le poids `I^2` valorise la
série lourde, conformément à la critique du sRPE en section 5.1 du doc). Cette cohérence est **construite**
par le choix de `I^2`, elle n'est pas une validation.

## 3. Readiness (`readiness.py`)

Deux axes séparés (décision de l'utilisateur), chacun avec CTL/ATL en moyennes exponentielles
`x <- x + (charge − x)(1 − e^(−1/τ))`, amorcées à la charge moyenne des 14 premiers jours.

| Axe       | τ CTL | τ ATL | Statut                                                                          |
| --------- | ----- | ----- | ------------------------------------------------------------------------------- |
| Endurance | 42 j  | 7 j   | convention usuelle (Banister / Intervals.icu)                                   |
| Force     | 28 j  | 2 j   | **hypothèses** : ATL 2 j -> 37 % restant à 48 h, 22 % à 72 h (doc : 48-72 h) ; CTL 28 j **sans source** |

- `forme` = moyenne pondérée de `(CTL − ATL)/CTL` par axe (> 0 : reposé) ; un axe sans charge est exclu.
- `fatigue` = max des `ATL/CTL` : axe limitant (une fatigue neurale ne doit pas être diluée par une
  endurance reposée). Alternative : moyenne.
- HRV : `ln(HRV)` moyennée sur 4 j (doc, section 5.2, Plews), z-score face à une base glissante de 28 j
  (écart-type plancher 0,05). Sans base (< 7 mesures) ou sans HRV : readiness = charge seule.
- `readiness` = `50 + 50 × (0,6 × clip(forme/0,5) + 0,4 × clip(z/2))`. Poids et échelles : hypothèses.
- Entrées : séries journalières de charge endurance et force, HRV. Aucune dépendance à `endurance.py`.
  Les deux charges n'ont pas la même échelle ; seul le **ratio** `ATL/CTL` de chaque axe est combiné.

## 4. Évaluation sur les séances réelles (copie en lecture seule, agrégats uniquement)

244 séances (654 jours de période), 5 832 séries dont 5 535 de travail validées.

- **Couverture de l'effort : nulle.** 0 série avec RPE, 0 avec durée, 0 avec minute EMOM. Aucune VL.
  Conséquence : 184 séances sur 244 sont évaluées en `defaut`/faible, 26 en `mixte` (par défaut + type `F`),
  12 en `type_f`, 10 en `srpe`, 12 en `aucune`. **Aucune séance n'a de confiance moyenne ou élevée.** Le coût
  actuel est donc essentiellement un tonnage pondéré par les répétitions : le multiplicateur de VL n'apporte
  rien tant que RPE/VL ne sont pas saisis. 408 séries sont de type `F` (7 %), 292 `W`.
- **Distribution** (séances avec coût > 0, n = 232, UA) : min 0,4 ; P10 13,5 ; P25 28,7 ; **médiane 48,4** ;
  P75 74,5 ; P90 107 ; P99 194 ; max 232. La médiane proche de 50 est fortuite : `UA_PAR_TONNE = 10` a été
  fixé a priori, pas ajusté. 12 séances à coût nul (aucune série validée). Médiane de 12 séries valorisées par séance.
  Part « neurale » (sans multiplicateur) : médiane 82 % du coût (les multiplicateurs par défaut pèsent peu).
- **Séances aberrantes / suspectes** :
  - 21 séances avec au moins une série à plus de 30 répétitions (190 séries ; jusqu'à plus de 200 reps, sur des
    exercices au poids du corps ou à très faible lest) : plafonnées à 30 reps, signalées `reps>cap`. Ce sont
    soit des saisies erronées, soit de vraies séries très longues, que le modèle (Epley, table RIR/VL) ne
    couvre pas : à vérifier à la main.
  - 10 séances « fantômes » (aucune série validée, mais heure de début et de fin) tombent en repli sRPE avec
    RPE supposé 6 : valeur peu fiable, à écarter ou à exclure si l'on préfère un 0.
  - Volume stocké `session_volume_kg` : il ne correspond (à 5 %) au volume recalculé depuis les séries et la
    bibliothèque actuelle que pour environ 51 séances sur 222 (même le tonnage brut, sans `rep_factor`,
    donne ce chiffre). Hypothèse : valeurs figées avant des changements de `rep_factor`/`bw_fraction` ou
    anciennes saisies. Corrélation de Pearson entre volume stocké et coût : 0,55.
  - 296 séries de travail validées ont une charge nulle (cause non vérifiée, probablement un exercice à charge
    libre saisi à 0) : coût nul pour ces séries.
- **Double comptage séance PWA / activité Intervals** : 30 séances portent un `intervals_activity_id`,
  mais **aucune des activités rattachées n'est présente** dans `intervals_activities` (5 activités seulement
  stockées, des courses et une randonnée, toutes non rattachées). Il n'y a donc pas de double comptage dans
  ces tables. En revanche `vigueur_entries.tss` est positif sur 165 de 244 jours (dont 35 jours sur 39 qui ont
  une séance) : si la charge d'endurance journalière est dérivée de ce TSS, il peut contenir l'estimation
  par Intervals.icu des séances de musculation. **Je ne sais pas** si c'est le cas : la décomposition du TSS
  par activité n'est pas dans la base. La fonction signale `activite_intervals_liee` mais ne corrige rien.
- **HRV** : 213 jours sur 244 ont une valeur `hrv` (87 %). Le z-score est calculable, mais sans CMJ ni
  autre mesure de performance on ne peut pas vérifier que `readiness` prédit quoi que ce soit.

## 5. Limites

- Aucune vérité terrain : pas de CMJ, pas de capteur de vitesse, aucune relation mesurée entre coût et
  récupération. Tout seuil ou constante est une hypothèse, pas un résultat.
- Le doc cite des études sur des charges lourdes (squat, développé) ; l'extrapolation aux tractions,
  dips, exercices de préhension et séries très longues n'est pas établie.
- Le coût dépend du kg absolu : comparer un exercice de bras à un squat en kg n'a pas de sens physiologique
  (option : normaliser par e1RM, ce qui revient à compter des séries-équivalents).
- La valeur par défaut (RIR 3) fait de la quasi-totalité des séances des estimations « faible confiance ».
  Le gain principal viendrait de la saisie du RPE (ou RIR) par série dans la PWA, qui existe dans le schéma.

## 6. Choix laissés à l'utilisateur

1. **Normalisation du tonnage** : kg absolus (actuel, simple, favorise les gros mouvements) ou rapporté à
   l'e1RM de chaque exercice (comparable entre exercices, mais exige un e1RM historique fiable).
2. **Séances sans effort saisi** : RIR 3 par défaut (actuel), valeur plus prudente (RIR 2), ou exclusion
   de la charge du modèle avec confiance « nulle ».
3. **τ de l'axe force** : 2/28 j (actuel), 3/35 j (plus lissé), ou calibrage ultérieur sur CMJ si un test
   hebdomadaire est ajouté.
4. **Double comptage du TSS** : soustraire de la charge d'endurance les activités de musculation, ou ne
   prendre en endurance que les activités de course/vélo.
