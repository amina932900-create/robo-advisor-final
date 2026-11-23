# Robo-advisor patrimonial — version finale

Projet de M2 Banque-Finance (Paris 1 Panthéon-Sorbonne). **Outil d'aide à la décision du conseiller en gestion de patrimoine**,
pour des clients de 100 000 € à 1 000 000 €. Aucun argent n'est investi : c'est une simulation pédagogique.

## Le parcours

1. Le client remplit et **signe** le questionnaire papier (généré par l'outil, 32 questions numérotées).
2. Le conseiller le **saisit** ; à droite de l'écran, **le profil se construit en direct**.
3. L'outil produit une **recommandation entièrement justifiée** : chaque chiffre a son « Pourquoi ? », et le **fil de décision**
   remonte, étape par étape, jusqu'à la réponse signée du client qui l'explique.
4. Le conseiller peut **ajuster** (profil abaissé, ±10 points, autre enveloppe) : tout se recalcule à l'instant, un réglage trop
   risqué est refusé avec sa raison, et **chaque dérogation exige un motif écrit** (sinon la conformité bloque).
5. Il édite la **déclaration d'adéquation** à faire signer, l'**Excel** de travail (macro VBA), et un **e-mail au client rédigé
   par IA** dont tous les chiffres sont vérifiés.
6. Le **tableau de bord** suit les clients : déclarations à signer, revues annuelles, alertes de rééquilibrage avec les ordres en euros.

## Les règles, en bref

| Étape | Règle |
| --- | --- |
| Profil | 4 notes sur 5 (tolérance, horizon, capacité à subir des pertes, connaissances) ; profil = la plus petite ; abaissable, jamais relevé |
| Allocation | Grille de 5 profils ; fourchettes de volatilité attendue 2-4 / 4-7 / 7-10 / 10-13 / 13-16 % ; SRI max 2 / 3 / 3 / 4 / 4 |
| Enveloppe | Retraite ou transmission → assurance-vie ; horizon > 5 ans et profil ≥ 4 → PEA (+ compte-titres) ; sinon assurance-vie ; le souhait du client prime |
| Cœur | ETF actions et obligations, monétaire, fonds en euros (assurance-vie, 30 % max) |
| Satellite | SCPI (assurance-vie, horizon > 8 ans) ; fonds actif 5 % ; actions européennes en direct pour les profils 4-5 (PEA ou compte-titres, connaissances ≥ 4) : un titre par secteur, le moins volatil de son secteur |
| Choix des supports | Filtres (enveloppe, version ISR, exclusions) puis classement : encours > 500 M€, réplication physique, 5 ans d'historique, frais les plus bas. **Aucun tirage au sort** |
| Contraintes | 30 % max par ligne, haut rendement ≤ 10 %, émergents ≤ 15 %, thématique ≤ 10 %, ligne < 1 % regroupée |
| Conformité | Jusqu'à 15 contrôles (MiFID II) ; un contrôle bloquant empêche l'émission de la déclaration |

Une seule mesure du risque fait foi : la **volatilité attendue** (hypothèses Amundi CMA 2026 + corrélations de long terme). Les cours
historiques servent à l'information (simulation rétrospective, rejeu des crises), au critère du satellite et au suivi de la dérive.

## Organisation des fichiers

| Fichier | Rôle |
| --- | --- |
| `app.py` | Point d'entrée : navigation, style |
| `commun.py` | Dossier courant, calculs mis en cache, composants visuels (fil de décision, jauges…) |
| `ecran_tableau.py` | Tableau de bord du cabinet |
| `ecran_questionnaire.py` | Saisie du questionnaire signé, profil en direct, revue |
| `ecran_recommandation.py` | Recommandation, « Pourquoi ? », ajustements motivés, rééquilibrage, émission et signature |
| `ecran_analyses.py` | Projection Monte Carlo, crises et machine à remonter le temps, frontière efficiente, fiscalité, durabilité |
| `ecran_livrables.py` | Déclaration PDF, Excel, e-mail IA, questionnaire vierge, export du dossier |
| `ecran_methodologie.py` | Règles, hypothèses, qualité des données, limites |
| `calcul_profil.py` | Les 32 questions numérotées et le calcul du profil, avec la justification de chaque note |
| `calcul_portefeuille.py` | Grille, enveloppe, choix des ETF, satellite, construction, fil de décision, rééquilibrage |
| `calcul_analyses.py` | Hypothèses, risque attendu, Markowitz, simulation, stress tests, fiscalité 2026, durabilité |
| `calcul_marches.py` | Cours (local / direct / démo) et indicateurs historiques |
| `calcul_conformite.py` | Contrôles d'adéquation, dossiers clients, clients de démonstration |
| `donnees.py` | Lecture de l'univers (`data/univers.csv`, `data/univers_titres.csv`) |
| `livrables.py` | PDF, Excel, e-mail IA avec garde-fou, questionnaire vierge |
| `telecharger_prix.py` | Crée `data/prix_snapshot.csv` (vrais cours) |
| `vba/` | Macro de mise en forme de l'Excel et mode d'emploi |
| `tests/` | 123 tests automatiques (`python -m pytest -q`) |

## Lancer

```
pip install -r requirements.txt
streamlit run app.py
```

Réglages (secrets Streamlit, voir `.streamlit/secrets.toml.example`) : `GEMINI_API_KEY` (e-mail rédigé par IA ; sans clé, un modèle
sobre est utilisé) et `ROBO_DONNEES` = `local` (par défaut : vrais cours de `data/prix_snapshot.csv`), `direct` (Yahoo Finance) ou `demo`.
Sans `data/prix_snapshot.csv`, l'outil passe en cours fictifs et l'affiche dans le menu.

## Sources et limites

- Hypothèses de marché : Amundi Investment Institute, *Capital Market Assumptions*, août 2026 (10 ans).
- Fiscalité 2026 : flat tax 31,4 % ; PEA 18,6 % après 5 ans ; assurance-vie 17,2 % de prélèvements sociaux (exclue de la hausse de CSG).
- Univers : justETF, DIC, Fortuneo ; tout champ non vérifié reste « TODO », jamais inventé ; un SRI manquant est estimé et signalé par *.
- Projet pédagogique : ceci n'est pas un conseil en investissement.
