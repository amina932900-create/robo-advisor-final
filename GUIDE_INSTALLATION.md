# Guide d'installation et de mise en ligne (Mac)

Environ 45 minutes la première fois. Chaque étape se termine par un contrôle ✅.

## 1. Python

Installer Python 3.12 ou 3.13 depuis python.org, puis double-cliquer sur **Install Certificates.command** (dossier Python des Applications).

```bash
python3 --version
```
✅ `Python 3.12.x` ou `3.13.x`.

## 2. Le code dans le dépôt GitHub

1. GitHub Desktop : **File > Clone repository** sur le dépôt du projet.
2. **Remplacer tout le contenu** du dossier par celui du zip de la version finale (supprimer les anciens fichiers V6 :
   `ecran_accueil.py`, `ecran_portefeuille.py`, `ecran_pro.py`, `tests/banc_streamlit.py`, etc.).
   `Cmd + Maj + .` affiche les dossiers cachés `.streamlit` et le fichier `.gitignore` : vérifier qu'ils sont copiés.

✅ GitHub Desktop liste les fichiers modifiés.

## 3. Librairies et tests

```bash
cd ~/Documents/GitHub/robo-advisor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
```
✅ `123 passed`. Les tests utilisent des cours fictifs : ils vérifient les règles, pas les marchés.

## 4. Les vrais cours (indispensable avant la soutenance)

```bash
python telecharger_prix.py --maj-univers
```
Le script télécharge depuis 2005 les cours des ETF, des fonds actifs et des actions européennes du satellite, et écrit
`data/prix_snapshot.csv`. Corriger dans `data/univers.csv` tout ticker marqué `AUCUNE DONNÉE` (recherche par ISIN sur
finance.yahoo.com), relancer, puis **pousser `data/prix_snapshot.csv` sur GitHub**.

✅ Le menu de gauche du site affiche « 💾 Cours : copie locale des cours réels » (et non « cours fictifs »).

## 5. Clé Gemini (e-mail rédigé par IA, facultatif)

1. aistudio.google.com > **Get API key**.
2. `cp .streamlit/secrets.toml.example .streamlit/secrets.toml`, coller la clé, garder `ROBO_DONNEES = "local"`.
3. `secrets.toml` est dans `.gitignore` : ne jamais le pousser.

✅ Page Documents > Rédiger l'e-mail : la mention indique « IA : gemini-… ». Sans clé, un modèle sobre est utilisé ; tout chiffre
inventé par l'IA est refusé.

## 6. Le modèle Excel avec macro (facultatif, une personne avec Excel)

Suivre `vba/LISEZMOI.md`, puis pousser `data/modele.xlsm`. La page Documents propose alors un `.xlsm`.

## 7. Lancer en local

```bash
streamlit run app.py
```
✅ Le tableau de bord affiche 6 clients de démonstration (fictifs), dont des revues annuelles à faire.

## 8. Mise en ligne (Streamlit Community Cloud)

1. GitHub Desktop : tout cocher **sauf** `secrets.toml`, Commit, Push, Pull Request vers `main`.
2. share.streamlit.io > l'application existante > **Settings > Secrets** : coller le contenu de `secrets.toml`
   (au minimum `ROBO_DONNEES = "local"`). **Reboot app**.

✅ L'adresse publique ouvre le tableau de bord ; le menu indique la copie locale des cours réels.

## En cas de problème

| Symptôme | Solution |
| --- | --- |
| « Cours : cours fictifs » | `data/prix_snapshot.csv` absent : étape 4 |
| Dossiers disparus | Normal après un redémarrage du serveur gratuit : les clients de démonstration sont recréés ; exporter/importer les autres en JSON |
| Le site plante au démarrage | Manage app > logs ; le plus souvent une librairie absente de `requirements.txt` |
