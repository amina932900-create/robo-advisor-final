# Fiches de soutenance — version finale

**Le pitch (30 secondes).** Nous avons construit l'outil d'un conseiller en gestion de patrimoine, pas un robot pour particuliers.
Le client signe un questionnaire ; le conseiller le saisit et obtient une recommandation dont **chaque chiffre se justifie**,
jusqu'à la réponse signée qui l'explique. Il peut ajuster, mais chaque dérogation est motivée et tracée ; un réglage trop risqué
est refusé. À la fin : la déclaration d'adéquation à signer, l'Excel de travail, un e-mail au client rédigé par IA et vérifié.

**La démo (5 minutes).** Tableau de bord → client RA-2025-021 (chef d'entreprise, ESG) : profil, « Pourquoi ? », fil de décision
(survoler un « Q.. ») → bouger le curseur actions : recalcul instantané, contrôle bloquant tant que le motif n'est pas saisi →
Projection et risques : machine à remonter le temps sur 2008 → Documents : déclaration PDF et e-mail. Puis « Nouveau dossier » :
saisir quelques réponses et montrer le profil qui se construit en direct.

---

## Amina — Règles de conseil, construction du portefeuille, Excel et IA
Fichiers : `calcul_portefeuille.py`, `livrables.py` (Excel, e-mail), `vba/`.

- **Cœur-satellite** : ETF et fonds en euros au cœur ; SCPI, fonds actif et actions en direct en satellite.
- **Aucun hasard** : filtres puis classement des ETF par critères publiés (encours, réplication, historique, frais).
- **Fil de décision** : 9 étapes, chacune avec sa règle, ses données, sa source et les questions du client citées.
- **Dérogations** : profil abaissable jamais relevable, ±10 points, enveloppe ; motif obligatoire, sinon contrôle bloquant.
- **IA** : elle reformule des chiffres déjà calculés ; tout nombre absent des données est refusé (modèle sobre en secours).

*Questions probables* — Pourquoi des ETF et pas des actions ? (diversification, compatibilité assurance-vie, données vérifiables ;
les actions existent en satellite pour les profils experts). Pourquoi 30 % max par ligne ? (risque d'émetteur et de gérant).

## Peter — Questionnaire, profil, déclaration d'adéquation
Fichiers : `calcul_profil.py`, `ecran_questionnaire.py`, `livrables.py` (PDF).

- 32 questions numérotées, identiques sur le papier signé et à l'écran ; 3 questions conditionnelles.
- Profil = plus petite des 4 notes ; tolérance = moyenne de 4 réponses arrondie prudemment ; chaque note est justifiée.
- Alertes de cohérence (rendement espéré contre perte acceptée, âge et horizon, retraits supérieurs à 4 %).
- Déclaration d'adéquation : profil, recommandation, risques, frais, fil de décision complet, contrôles, signatures.

*Questions probables* — Pourquoi la plus petite note ? (règle prudente : une seule fragilité suffit à limiter le risque).
Le client peut-il forcer un profil plus risqué ? (non : MiFID II interdit de recommander un produit inadapté).

## Aly — Actions, marchés, satellite et rééquilibrage
Fichiers : `calcul_marches.py`, `telecharger_prix.py`, satellite de `calcul_portefeuille.py`.

- Cours réels (copie locale), indicateurs historiques, rejeu des crises (« machine à remonter le temps »).
- Satellite : un titre européen par secteur, le moins volatil de son secteur sur 3 ans, coté en euros (pas de risque de change).
- Rééquilibrage : poids actuels après dérive depuis la signature, alerte au-delà de 5 points, ordres en euros par classe.

*Questions probables* — Pourquoi la volatilité historique ne sert-elle pas au profil ? (elle dépend de la période ; la conformité
repose sur une mesure prospective et sourcée, la volatilité attendue).

## Haochen — Obligations, hypothèses, simulation et fiscalité
Fichiers : `calcul_analyses.py`, `ecran_analyses.py`.

- Hypothèses Amundi CMA 2026, corrélations de long terme : une seule volatilité attendue pour tout l'outil.
- Grille recalée : fourchettes de volatilité et SRI max cohérents avec le modèle et les seuils PRIIPs.
- Monte Carlo 10 000 trajectoires, nets de tous les frais (frais du contrat hors fonds en euros), retraits, euros d'aujourd'hui.
- Fiscalité 2026 : même portefeuille dans les trois enveloppes ; en PEA, seules les lignes éligibles.

*Questions probables* — Pourquoi la frontière efficiente n'est-elle pas atteinte ? (contraintes de conseil assumées : 30 % par ligne,
satellite, préférences ; l'écart est chiffré). Pourquoi l'assurance-vie si le compte-titres rapporte plus net ? (fonds en euros,
transmission, souhait du client : l'outil le dit explicitement).

## Damien — Interface et intégration
Fichiers : `app.py`, `commun.py`, `ecran_*.py`, `tests/`.

- Interface conseiller : tableau de bord, profil en direct, « Pourquoi ? » sur chaque chiffre, recalcul instantané.
- Français et anglais ; 123 tests automatiques, dont l'affichage de chaque écran pour chaque client de démonstration.
- Dossiers pseudonymes (RA-…), journal d'audit, export/import JSON (le serveur gratuit efface le disque au redémarrage).

*Questions probables* — Pourquoi Streamlit ? (Python de bout en bout, gratuit, déployé en un clic ; les calculs sont séparés de
l'interface et testés indépendamment).
