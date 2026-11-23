# Macro VBA du fichier Excel

Le site tourne sur un serveur sans Excel : il ne peut pas exécuter de macro. Il remplit donc un **modèle .xlsm**
qui contient déjà la macro ; la macro se lance quand le conseiller ouvre le fichier.

## Créer le modèle (une seule fois, sur un ordinateur avec Excel)

1. Ouvrir Excel, nouveau classeur vide, **Enregistrer sous** `modele.xlsm` (Classeur Excel prenant en charge les macros).
2. `Alt + F11` (Mac : `Option + F11`) pour ouvrir l'éditeur VBA.
3. **Fichier > Importer un fichier…** : choisir `vba/MiseEnForme.bas`.
4. Double-cliquer sur **ThisWorkbook** et coller le contenu de `vba/ThisWorkbook.txt`.
5. Enregistrer, fermer, copier `modele.xlsm` dans le dossier `data/` du dépôt et le pousser sur GitHub.

Dès que `data/modele.xlsm` existe, la page Documents propose un fichier `.xlsm` (sinon `.xlsx`, sans macro).

## Ce que fait la macro

- `MiseEnForme` (à l'ouverture) : masque le quadrillage, police et pied de page, mise en page paysage sur une page de large,
  couleurs des statuts de conformité, anneau d'allocation sur l'onglet Synthèse.
- `ExporterPDF` (Alt+F8) : exporte le classeur en PDF à côté du fichier.

À l'ouverture, Excel demande d'**activer le contenu** : c'est normal pour un fichier avec macro.
