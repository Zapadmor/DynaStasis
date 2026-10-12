"""Gabarits des audits trimestriel et annuel (champs, indications, couleurs)."""

from __future__ import annotations

from src.app.components import GRAY, PALETTE

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────────────────────────────────────

_SAISONS = ["Hiver", "Printemps", "Été", "Automne"]
_SAISON_PAR_MOIS = {
    12: "Hiver",
    1: "Hiver",
    2: "Hiver",
    3: "Printemps",
    4: "Printemps",
    5: "Printemps",
    6: "Été",
    7: "Été",
    8: "Été",
    9: "Automne",
    10: "Automne",
    11: "Automne",
}

# ─────────────────────────────────────────────────────────────────────────────
# TEMPLATE AUDIT TRIMESTRIEL
# ─────────────────────────────────────────────────────────────────────────────

_TRIM_PARTIES = [
    {
        "key": "p1",
        "title": "Partie 1 — Bilan & Prise de Conscience",
        "color": PALETTE["amber"],
        "champs": [
            (
                "p1_accomplissements",
                "1.1 Les accomplissements récents",
                "Qu'as-tu accompli ces derniers mois ? Liste tout ce qui te vient à l'esprit "
                "(projets, examens, compétences, réalisations). Comment te sens-tu après ?",
            ),
            (
                "p1_burnout",
                "1.2 Le Burnout et les Écueils",
                "Qu'est-ce qui t'a le plus épuisé mentalement ou physiquement ? "
                "Quelles tâches as-tu commencé à éviter ou à procrastiner ?",
            ),
            (
                "p1_energie",
                "1.3 Énergie et Motivation",
                "Quand as-tu eu l'impression d'être dans ton élément pour la dernière fois ? "
                "Quelle activité te fait oublier le temps et te recharge ?",
            ),
        ],
    },
    {
        "key": "p2",
        "title": "Partie 2 — Vision & Intentions",
        "color": PALETTE["blue_green"],
        "champs": [
            (
                "p2_direction",
                "2.1 La Direction",
                "Imagine-toi dans 2 ans et demi, à la fin de ton diplôme. "
                "Que veux-tu avoir appris (au-delà des cours) ? Expérimenté ? "
                "Quel type de personne veux-tu être devenu ?",
            ),
            (
                "p2_piliers",
                "2.2 Les Piliers",
                "Quels sont les 3 à 5 domaines les plus importants pour ton équilibre "
                "et ton épanouissement actuels ? (Santé physique, mentale, réseau social, "
                "projet professionnel, compétences techniques, soft skills, famille, etc.)",
            ),
            (
                "p2_intentions",
                "2.3 Les Intentions pour la saison",
                "Pour chaque pilier identifié, écris une intention simple et positive "
                "pour les 3 prochains mois.\n"
                "Exemple : « Mon intention est de retrouver de l'énergie et une meilleure récupération. »",
            ),
        ],
    },
    {
        "key": "p3",
        "title": "Partie 3 — Concrétisation & Obstacles",
        "color": PALETTE["sky_blue"],
        "champs": [
            (
                "p3_concretisation",
                "3.1 Définition de Succès",
                "Pour chaque intention, que pourrais-tu concrètement faire, même de manière très petite, "
                "pour la réaliser ? Liste des actions tangibles.",
            ),
            (
                "p3_frictions",
                "3.2 Analyse des Frictions — Le Pire Jour",
                "Prends 2-3 actions concrètes. Imagine une journée horrible : tu es fatigué, "
                "il pleut, tu n'as aucune motivation, 3 cours obligatoires + projet de groupe. "
                "Qu'est-ce qui t'empêcherait, ce jour-là, de faire chaque action ?",
            ),
            (
                "p3_echelle",
                "3.3 Échelle de Pénibilité (1–10)",
                "Sur une échelle de 1 (très facile) à 10 (insurmontable), évalue la pénibilité "
                "pour démarrer chaque action dans ton pire jour. "
                "L'objectif du système sera de faire tomber ces scores en dessous de 3.",
            ),
        ],
    },
    {
        "key": "p4",
        "title": "Partie 4 — Règles du Système",
        "color": GRAY,
        "champs": [
            (
                "p4_solutions",
                "4.1 Solutions Temporaires vs Définitives",
                "As-tu des rustines actuelles pour pallier tes problèmes ? "
                "(Comme la sieste pour le manque de sommeil.) "
                "Quelle serait la solution idéale et durable pour chacune ?",
            ),
            (
                "p4_non_negotiable",
                "4.2 Le Non-Négociable",
                "Quelle est la seule habitude que tu pourrais t'engager à tenir, "
                "peu importe les circonstances, parce qu'elle a un effet "
                "démesurément positif sur ton état ?",
            ),
        ],
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# TEMPLATE AUDIT ANNUEL
# ─────────────────────────────────────────────────────────────────────────────

_ANNUEL_MODULES = [
    {
        "key": "m1",
        "title": "Module 1 — Socle Somatique & Régulation Nerveuse",
        "objectif": (
            "Évaluer la disponibilité physiologique, la capacité de récupération et les "
            "mécanismes d'adaptation face au stress chronique (charge allostatique)."
        ),
        "color": PALETTE["blue_green"],
        "indicators": [
            (
                "m1_note_recuperation",
                "Qualité de la récupération",
                "Sommeil réparateur, énergie constante le matin sans dépendance excessive "
                "aux stimulants. Ex : réveils nocturnes fréquents en Q2, 3 cafés/jour.",
            ),
            (
                "m1_note_signaux",
                "Écoute des signaux d'alarme",
                "Capacité à détecter et ralentir face aux tensions musculaires, céphalées, "
                "inconforts digestifs. Ex : tendance à ignorer les maux de tête jusqu'à l'arrêt forcé.",
            ),
            (
                "m1_note_soupapes",
                "Sobriété des soupapes de décompression",
                "Capacité à réguler le stress sans recourir systématiquement aux écrans, "
                "sucre, alcool ou achats. Ex : scroller 45 min chaque soir après les réunions tendues.",
            ),
            (
                "m1_note_respiration",
                "Respiration & présence",
                "Fréquence des pauses réelles dans la journée (déconnexion sensorielle, "
                "silence, marche). Ex : cohérence cardiaque 3x/semaine en moyenne.",
            ),
        ],
        "questions": [
            (
                "m1_cout_allostasie",
                "Le coût de l'allostasie",
                "À quel moment de l'année ai-je fonctionné « à découvert » sur mes réserves "
                "physiques, et quel en a été le prix direct sur mon humeur et ma lucidité ?",
            ),
            (
                "m1_sources_ressourcement",
                "Les véritables sources de ressourcement",
                "Quelles sont les 2 seules activités qui m'ont redonné une énergie durable "
                "cette année (vs divertissement passif qui engourdit sans réparer) ?",
            ),
        ],
    },
    {
        "key": "m2",
        "title": "Module 2 — Clarté Intrinsèque & Dynamique du Flow",
        "objectif": (
            "Distinguer les accomplissements motivés par la recherche de statut externe "
            "(désir mimétique) de ceux portés par vos moteurs intrinsèques profonds."
        ),
        "color": PALETTE["amber"],
        "indicators": [
            (
                "m2_note_flow",
                "Fréquence du Flow",
                "Immersion totale dans des tâches exigeantes où le temps s'efface au profit "
                "de la concentration. Ex : présent sur la conception, absent sur l'admin.",
            ),
            (
                "m2_note_fierte",
                "Fierté authentique",
                "Sentiment de fierté lié à la maîtrise et au chemin parcouru, indépendant du "
                "regard et des likes extérieurs. Ex : un projet réussi dans l'ombre a plus comblé qu'un prix visible.",
            ),
            (
                "m2_note_effort",
                "Justesse de l'effort",
                "Alignement entre la dépense d'énergie et la valeur perçue (peu de résistance "
                "stérile). Ex : forte friction sur les réunions sans ordre du jour clair.",
            ),
            (
                "m2_note_priorites",
                "Cohérence des priorités",
                "Mes 3 priorités déclarées correspondent aux 3 postes de dépenses de temps "
                "réels. Ex : famille déclarée n°1, mais seulement 30 min dispo/jour.",
            ),
        ],
        "questions": [
            (
                "m2_flow_moment1",
                "Moment d'absorption & vitalité élevée (1)",
                "Moment / projet, et compétences mobilisées.",
            ),
            (
                "m2_flow_moment2",
                "Moment d'absorption & vitalité élevée (2)",
                "Moment / projet, et compétences mobilisées.",
            ),
            (
                "m2_friction_tache1",
                "Friction disproportionnée / procrastination lourde (1)",
                "Tâche / projet, et cause racine (manque de sens ou déficit de compétence ?).",
            ),
            (
                "m2_friction_tache2",
                "Friction disproportionnée / procrastination lourde (2)",
                "Tâche / projet, et cause racine.",
            ),
        ],
    },
    {
        "key": "m3",
        "title": "Module 3 — Écologie Relationnelle & Frontières Psychologiques",
        "objectif": (
            "Évaluer la qualité du cercle d'influence, le niveau de sécurité psychologique "
            "et la netteté des limites personnelles (boundaries)."
        ),
        "color": PALETTE["sky_blue"],
        "indicators": [
            (
                "m3_note_securite",
                "Sécurité psychologique",
                "Présence de relations où l'on peut exprimer vulnérabilité, erreurs ou "
                "désaccords sans risque de rétorsion. Ex : deux amis proches et un mentor en transparence totale.",
            ),
            (
                "m3_note_limites",
                "Fermeté des limites",
                "Capacité à refuser des demandes inopportunes sans se justifier excessivement "
                "ni culpabiliser. Ex : tendance à accepter des urgences de collègues en soirée.",
            ),
            (
                "m3_note_etancheite",
                "Étanchéité émotionnelle",
                "Capacité à faire preuve d'empathie sans absorber la détresse ou l'amertume "
                "d'autrui. Ex : facilement contaminé par le pessimisme des réunions d'équipe.",
            ),
            (
                "m3_note_mutualite",
                "Mutualité & équilibre",
                "Réciprocité dans l'investissement relationnel (temps, soutien, écoute, "
                "générosité). Ex : relation à sens unique depuis plusieurs mois.",
            ),
        ],
        "questions": [
            (
                "m3_oui_complaisance1",
                "« Oui » par complaisance (1)",
                "Situation précise où j'ai dit « oui » par peur du conflit ou besoin d'approbation.",
            ),
            (
                "m3_oui_complaisance2",
                "« Oui » par complaisance (2)",
                "Situation précise où j'ai dit « oui » par peur du conflit ou besoin d'approbation.",
            ),
            (
                "m3_arbitrage_nourrir",
                "Arbitrage relationnel — à nourrir",
                "Quelles sont les 2 relations à nourrir en priorité absolue cette année ?",
            ),
            (
                "m3_arbitrage_reguler",
                "Arbitrage relationnel — à réguler",
                "Quelle relation faut-il réguler drastiquement l'exposition ?",
            ),
        ],
    },
    {
        "key": "m4",
        "title": "Module 4 — Flexibilité Cognitive & Traitement de l'Échec",
        "objectif": (
            "Mesurer la capacité à transformer les erreurs en apprentissages structurés "
            "sans basculer dans le déni externe ou la dévalorisation personnelle."
        ),
        "color": GRAY,
        "indicators": [
            (
                "m4_note_locus",
                "Locus de contrôle interne",
                "Focalisation sur les variables maîtrisables (actions, attitudes) plutôt que "
                "sur la météo ou la faute des autres. Ex : rares plaintes passives, solutions rapides.",
            ),
            (
                "m4_note_autocompassion",
                "Autocompassion pragmatique",
                "Absence d'autocritique destructive en cas d'erreur ; discours interne factuel "
                "et bienveillant. Ex : tendance encore vive au syndrome de l'imposteur après un raté.",
            ),
            (
                "m4_note_courage",
                "Courage de confrontation",
                "Vitesse à regarder en face les vérités inconfortables (statistiques, finances, "
                "tensions de couple). Ex : délai de 3 mois avant de clarifier une anomalie financière.",
            ),
            (
                "m4_note_plasticite",
                "Plasticité d'opinion",
                "Facilité à changer d'avis et à désapprendre face à de nouvelles données "
                "contradictoires. Ex : abandon rapide d'une stratégie obsolète sans regret d'ego.",
            ),
        ],
        "questions": [
            (
                "m4_fait_brut",
                "Le fait brut (sans jugement)",
                "Qu'est-ce qui s'est réellement produit factuellement, lors d'un revers majeur de l'année ?",
            ),
            (
                "m4_interpretation_initiale",
                "L'interprétation initiale",
                "Quelle histoire négative me suis-je racontée sur moi-même ?",
            ),
            (
                "m4_variable_controle",
                "La variable de contrôle",
                "Quel facteur dépendant à 100% de moi n'a pas été actionné à temps ?",
            ),
            (
                "m4_regle_systemique",
                "La règle systémique dérivée",
                "Quelle modification de processus garantit que cette erreur ne se répète plus ?",
            ),
        ],
    },
]

_ANNUEL_M5 = {
    "title": "Module 5 — Feuille de Route & Intentions d'Implémentation",
    "objectif": (
        "Convertir les prises de conscience en architectures comportementales concrètes "
        "selon la théorie de l'autodétermination et les habitudes atomiques."
    ),
    "color": PALETTE["tiger"],
    "piliers": [
        ("m5_autonomie_objectif", "m5_autonomie_indicateur", "Autonomie (ma liberté de choix)"),
        (
            "m5_maitrise_objectif",
            "m5_maitrise_indicateur",
            "Maîtrise (l'artisanat & la compétence)",
        ),
        (
            "m5_contribution_objectif",
            "m5_contribution_indicateur",
            "Contribution (l'impact externe)",
        ),
    ],
    "si_alors": [
        (
            "m5_habitude_declencheur",
            "m5_habitude_comportement",
            "Micro-habitude clé (<10 min)",
            "Dès que [heure / événement précis du matin]…",
            "J'exécute immédiatement [action minimale non négociable]…",
        ),
        (
            "m5_distraction_declencheur",
            "m5_distraction_comportement",
            "Gestion de la distraction",
            "Si je ressens l'envie réflexe d'ouvrir [application parasite]…",
            "Alors je m'oblige à [pause somatique de 3 respirations / téléphone hors de la pièce]…",
        ),
        (
            "m5_regulation_declencheur",
            "m5_regulation_comportement",
            "Régulation hebdomadaire",
            "Chaque [jour fixe, ex : dimanche 18h00]…",
            "Je bloque 15 minutes pour auditer mes 3 métriques de la semaine passée…",
        ),
    ],
}
