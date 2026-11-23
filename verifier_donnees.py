"""
verifier_donnees.py — Contrôle de data/univers.csv avant la soutenance.

    python verifier_donnees.py            # affiche ce qui reste à vérifier et les erreurs de format
    python verifier_donnees.py --liste    # (ré)écrit data/a_verifier.csv : une ligne par donnée manquante, avec où la trouver

Formats attendus : sri = 1 à 7 (lu dans le DIC : « classe de risque X sur 7 ») ; sfdr = 6, 8 ou 9
(« Autre » / « Other » chez BlackRock = article 6) ; pea = oui / non ; encours_meur = nombre (millions d'euros) ;
date_creation = AAAA-MM-JJ ; ter = décimal (0.0020 pour 0,20 %). Une donnée introuvable reste TODO : ne jamais l'inventer.
"""

import sys
from pathlib import Path

import pandas as pd

DOSSIER = Path(__file__).resolve().parent
UNIVERS = DOSSIER / "data" / "univers.csv"
SORTIE = DOSSIER / "data" / "a_verifier.csv"
CHAMPS = ["sri", "sfdr", "pea", "encours_meur", "date_creation", "replication", "ter"]


def ou_trouver(l, champ) -> str:
    nom = l["nom"].lower()
    if champ in ("sri", "sfdr"):
        if "ishares" in nom:
            return "blackrock.com/fr > fiche du fonds (ISIN) > Documents > Document d'informations clés ; SFDR dans « Caractéristiques »"
        if "amundi" in nom:
            return "amundietf.fr > fiche du fonds (ISIN) > Documents > DIC ; SFDR sur la fiche"
        if "bnp" in nom:
            return "bnpparibas-am.com > recherche par ISIN > DIC"
        if "xtrackers" in nom:
            return "etf.dws.com > fiche du fonds (ISIN) > DIC"
        if "scpi" in nom:
            return "sofidy.com > Immorente > Documents > DIC"
        if "fonds en euros" in nom:
            return "SRI propre à chaque contrat : choisir un contrat de référence ou laisser 1 (capital garanti) en le justifiant"
        return "site de la société de gestion > DIC"
    return "justetf.com/fr/etf-profile.html?isin=" + l["isin"] + " (ou fiche Fortuneo / émetteur)"


def responsable(l) -> str:
    return "Haochen" if l["classe"] in ("obligations", "monetaire", "scpi") else "Aly"


def main(liste: bool) -> None:
    u = pd.read_csv(UNIVERS, dtype=str, keep_default_na=False)
    manques, erreurs = [], []
    for _, l in u.iterrows():
        for c in CHAMPS:
            v = l[c]
            if v == "TODO":
                if c == "ter" and l["sous_classe"] == "fonds_euros":
                    continue
                manques.append({"responsable": responsable(l), "isin": l["isin"], "nom": l["nom"], "champ": c, "ou_trouver": ou_trouver(l, c)})
            elif v:
                ok = {"sri": lambda x: x in list("1234567"), "sfdr": lambda x: x in ("6", "8", "9", "n/a"),
                      "pea": lambda x: x in ("oui", "non"), "encours_meur": lambda x: x.replace(".", "", 1).isdigit(),
                      "date_creation": lambda x: len(x) == 10 and x[4] == "-" and x[7] == "-",
                      "ter": lambda x: x.replace(".", "", 1).isdigit() and float(x) < 0.05}.get(c, lambda x: True)(v)
                if not ok:
                    erreurs.append(f"{l['isin']} {c} = {v!r} (format attendu : voir l'en-tête du script)")
    print(f"{len(manques)} donnée(s) à vérifier, {len(erreurs)} erreur(s) de format.")
    for e in erreurs:
        print("  ERREUR", e)
    par = pd.DataFrame(manques)
    if not par.empty:
        print(par.groupby(["responsable", "champ"]).size().to_string())
    if liste:
        par.to_csv(SORTIE, index=False)
        print(f"Liste écrite : {SORTIE}")


if __name__ == "__main__":
    main("--liste" in sys.argv)
