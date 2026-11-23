"""
donnees.py — Lecture de l'univers d'investissement (data/univers.csv et data/univers_titres.csv).

- univers.csv : ETF, fonds en euros, SCPI et fonds actifs (le cœur et le satellite « fonds ») ;
- univers_titres.csv : actions en direct, utilisées seulement pour la poche satellite « actions » (profils 4-5).
  Les obligations en direct de ce fichier ne sont plus utilisées (pas de cours, coupures de 100 000 €).

Règle : aucune donnée inventée. Un champ non vérifié reste « TODO » et l'outil l'affiche comme tel ;
le SRI manquant d'un ETF est ESTIMÉ à partir de la volatilité de sa classe et signalé « estimé ».
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

import pandas as pd

DOSSIER = Path(__file__).resolve().parent
CHEMIN_UNIVERS = DOSSIER / "data" / "univers.csv"
CHEMIN_TITRES = DOSSIER / "data" / "univers_titres.csv"
PLACES_EURO = (".PA", ".DE", ".AS", ".MC", ".MI", ".IR", ".BR", ".HE", ".LS", ".VI")
SECTEURS_SATELLITE = ("action_europe", "action_france")


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.replace({"TODO": None, "": None}), errors="coerce")


@lru_cache(maxsize=1)
def univers() -> pd.DataFrame:
    """Toutes les lignes utilisables, indexées par ISIN (ou identifiant interne)."""
    u = pd.read_csv(CHEMIN_UNIVERS, dtype=str, keep_default_na=False)
    u["type"] = "fonds"
    if CHEMIN_TITRES.exists():
        t = pd.read_csv(CHEMIN_TITRES, dtype=str, keep_default_na=False)
        t = t[(t["type"] == "action") & t["sous_classe"].isin(SECTEURS_SATELLITE)].copy()
        t["classe"] = "actions"
        t["sous_classe"] = "satellite"
        u = pd.concat([u, t], ignore_index=True).fillna("")
    for c in ("secteur", "pays", "tags", "esg", "type"):
        if c not in u.columns:
            u[c] = ""
    u = u.set_index("isin", drop=False)
    u["ter_num"] = _num(u["ter"])
    u["taux_num"] = _num(u["taux_annuel"])
    u["encours_num"] = _num(u["encours_meur"])
    u["sri_num"] = _num(u["sri"])
    creation = pd.to_datetime(u["date_creation"].replace({"TODO": None, "": None}), errors="coerce")
    u["anciennete_ans"] = (pd.Timestamp(date.today()) - creation).dt.days / 365.25
    u["euro"] = u["ticker_yahoo"].map(lambda t: str(t).endswith(PLACES_EURO))
    return u


def ligne(isin: str) -> pd.Series:
    return univers().loc[isin]


def nom(isin: str) -> str:
    return str(univers().loc[isin, "nom"])


def classe(isin: str) -> str:
    return str(univers().loc[isin, "classe"])


def est_titre(isin: str) -> bool:
    return univers().loc[isin, "type"] == "action"


def sri(isin: str) -> tuple[int | None, bool]:
    """(SRI, estimé ?) : SRI lu dans le DIC si renseigné, sinon estimé à partir de la volatilité de la classe."""
    l = univers().loc[isin]
    if l["sri_num"] == l["sri_num"]:
        return int(l["sri_num"]), False
    import calcul_analyses
    if l["sous_classe"] == "fonds_euros":
        return 1, True
    _, vol = calcul_analyses.hypotheses_ligne(isin)
    if l["type"] == "action":
        vol = (vol ** 2 + calcul_analyses.RISQUE_SPECIFIQUE ** 2) ** 0.5
    return calcul_analyses.classe_sri(vol), True


SECTEURS_EN = {"Aéronautique": "Aerospace", "Communication": "Communication", "Consommation": "Consumer discretionary",
               "Consommation de base": "Consumer staples", "Défense": "Defence", "Finance": "Financials", "Industrie": "Industrials",
               "Luxe": "Luxury", "Matériaux": "Materials", "Santé": "Health care", "Services publics": "Utilities",
               "Technologie": "Technology", "Transport aérien": "Airlines", "Énergie": "Energy", "Énergie propre": "Clean energy",
               "Immobilier": "Real estate"}
PAYS_EN = {"Allemagne": "Germany", "Danemark": "Denmark", "Espagne": "Spain", "France": "France", "Irlande": "Ireland",
           "Italie": "Italy", "Norvège": "Norway", "Pays-Bas": "Netherlands", "Royaume-Uni": "United Kingdom", "Suisse": "Switzerland",
           "Belgique": "Belgium", "Autriche": "Austria", "Finlande": "Finland", "Portugal": "Portugal", "Luxembourg": "Luxembourg"}


def secteur_pays(isin: str, langue: str = "fr") -> str:
    """« Finance · Espagne » (ou en anglais) pour une action en direct."""
    l = univers().loc[isin]
    if langue == "en":
        return f"{SECTEURS_EN.get(l['secteur'], l['secteur'])} · {PAYS_EN.get(l['pays'], l['pays'])}"
    return f"{l['secteur']} · {l['pays']}"
