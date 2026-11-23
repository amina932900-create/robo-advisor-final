"""
calcul_marches.py — Cours de marché et indicateurs HISTORIQUES (information complémentaire, jamais la base du conseil).

Source des cours, réglage unique ROBO_DONNEES (secrets Streamlit ou variable d'environnement) :
- "local"  (par défaut) : vrais cours de data/prix_snapshot.csv, créé par telecharger_prix.py, sans internet ;
- "direct" : Yahoo Finance en temps réel, repli sur la copie locale ;
- "demo"   : cours FICTIFS reproductibles (tests). Utilisé automatiquement, et signalé, si la copie locale manque.

Sert à : simulation rétrospective du portefeuille, indicateurs passés, rejeu des crises, volatilité des actions
du satellite (critère de sélection), dérive des poids pour le rééquilibrage.
"""

from __future__ import annotations

import hashlib
import os
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

import calcul_analyses
import donnees

CHEMIN_SNAPSHOT = Path(__file__).resolve().parent / "data" / "prix_snapshot.csv"
MODES = ("local", "direct", "demo")
JOURS = 252
DEBUT = "2005-01-03"
TICKER_SANS_RISQUE = "XEON.DE"
_prix_imposes: pd.DataFrame | None = None


def _reglage(nom: str) -> str | None:
    try:
        import streamlit as st
        if nom in st.secrets:
            return str(st.secrets[nom])
    except Exception:
        pass
    return os.environ.get(nom)


def mode() -> str:
    m = (_reglage("ROBO_DONNEES") or "local").strip().lower()
    m = m if m in MODES else "local"
    return "demo" if m == "local" and not CHEMIN_SNAPSHOT.exists() else m


def nom_mode(langue: str = "fr") -> str:
    noms = {"local": ("copie locale des cours réels", "local copy of real prices"),
            "direct": ("Yahoo Finance en direct", "live Yahoo Finance"),
            "demo": ("cours fictifs (démonstration)", "simulated prices (demo)")}
    return noms[mode()][1 if langue == "en" else 0]


def definir_prix(prix: pd.DataFrame | None) -> None:
    """Impose une table de prix (tests)."""
    global _prix_imposes
    _prix_imposes = prix
    _tous_les_prix.cache_clear()


# ---------------------------------------------------------------------------------------------------
# Cours fictifs : chaque ligne suit le rendement et la volatilité de sa classe (hypothèses Amundi), avec un
# facteur de marché commun ; les crises 2008, 2020 et 2022 sont reproduites à partir des chocs des stress tests.
# ---------------------------------------------------------------------------------------------------
def _graine(texte: str) -> int:
    return int(hashlib.md5(texte.encode()).hexdigest()[:8], 16)


def _serie_fictive(isin: str, jours: pd.DatetimeIndex) -> pd.Series:
    n = len(jours)
    expo = calcul_analyses.exposition({isin: 1.0})
    cl = max(expo, key=expo.get)
    mu, sigma = calcul_analyses.HYPOTHESES.get(cl, (0.06, 0.15))
    if donnees.est_titre(isin):
        sigma = (sigma ** 2 + calcul_analyses.RISQUE_SPECIFIQUE ** 2) ** 0.5
    rho = 0.75 if cl.startswith("actions") else 0.35 if cl in ("euro_hy", "immobilier_cote") else 0.1
    marche = np.random.default_rng(20050103).standard_normal(n)
    z = rho * marche + np.sqrt(1 - rho ** 2) * np.random.default_rng(_graine(isin)).standard_normal(n)
    vj = sigma / np.sqrt(JOURS)
    r = np.log1p(mu) / JOURS - vj ** 2 / 2 + vj * z
    for s in calcul_analyses.SCENARIOS.values():
        if not s["dates"]:
            continue
        m = (jours >= s["dates"][0]) & (jours <= s["dates"][1])
        k = int(m.sum())
        if k:
            choc = sum(p * s["chocs"].get(c, 0.0) for c, p in expo.items())
            r[m] += (np.log1p(choc) - r[m].sum()) / k
    return pd.Series(100 * np.exp(np.cumsum(r)), index=jours, name=isin)


@lru_cache(maxsize=1)
def _tous_les_prix() -> tuple[pd.DataFrame, str]:
    """Table des cours indexée par date, une colonne par ISIN de l'univers (lignes à taux fixe exclues)."""
    u = donnees.univers()
    cotees = u[u["taux_num"].isna()]
    if _prix_imposes is not None:
        return _prix_imposes, "tests"
    m = mode()
    if m == "direct" and not CHEMIN_SNAPSHOT.exists():
        m = "demo"                                   # pas de repli possible : cours fictifs, signalés
    if m == "demo":
        jours = pd.bdate_range(DEBUT, pd.Timestamp.today().normalize() - pd.offsets.BDay(1))
        return pd.concat([_serie_fictive(i, jours) for i in cotees.index], axis=1), "demo"
    brut = None
    if m == "direct":
        try:
            import yfinance as yf
            tick = sorted(set(cotees["ticker_yahoo"]) - {"", "TODO"})
            data = yf.download(tick, start=DEBUT, auto_adjust=True, progress=False, threads=True, timeout=15)
            brut = data["Close"] if isinstance(data.columns, pd.MultiIndex) else data[["Close"]]
            brut.index = pd.to_datetime(brut.index).tz_localize(None)
        except Exception:
            brut = None
    if brut is None or brut.dropna(how="all").empty:
        brut = pd.read_csv(CHEMIN_SNAPSHOT, index_col=0, parse_dates=True).sort_index()
        m = "local"
    par_isin = {i: brut[t] for i, t in cotees["ticker_yahoo"].items() if t in brut.columns}
    return pd.DataFrame(par_isin).sort_index(), m


def prix() -> pd.DataFrame:
    return _tous_les_prix()[0]


def rendements(pf: dict) -> pd.DataFrame:
    """Rendements quotidiens de chaque ligne ; fonds en euros et SCPI : taux constant (pas de cotation)."""
    u = donnees.univers()
    p = prix()
    rend = pd.DataFrame(index=p.index[1:])
    for isin in pf:
        taux = u.loc[isin, "taux_num"]
        if taux == taux:
            rend[isin] = (1 + taux) ** (1 / JOURS) - 1
        elif isin in p.columns:
            rend[isin] = p[isin].ffill(limit=5).pct_change(fill_method=None).iloc[1:].values
        else:
            rend[isin] = np.nan
    return rend


def serie(pf: dict) -> tuple[pd.Series, list[str]]:
    """Rendements quotidiens du portefeuille rééquilibré chaque jour (simulation rétrospective)."""
    rend = rendements(pf)
    w = pd.Series(pf)
    sans = [i for i in pf if rend[i].isna().all()]
    avert = [f"Pas d'historique : {', '.join(donnees.nom(i) for i in sans)}"] if sans else []
    dispo = rend.notna()
    couverture = dispo.mul(w, axis=1).sum(axis=1) / w.sum()
    rend = rend[couverture >= 0.9]
    if rend.empty:
        return pd.Series(dtype=float), avert + ["Historique insuffisant."]
    poids = rend.notna().mul(w, axis=1)
    poids = poids.div(poids.sum(axis=1), axis=0)
    return (rend.fillna(0) * poids).sum(axis=1), avert


def indicateurs(pf: dict) -> dict:
    """Indicateurs historiques (simulation rétrospective) : perf 1/3/5 ans, volatilité, perte maximale, crises."""
    s, avert = serie(pf)
    res = {"source": mode(), "avertissements": avert, "depuis": None, "perf_1a": None, "perf_3a": None,
           "perf_5a": None, "vol_hist": None, "perte_max": None, "crises": {}}
    if len(s) < 60:
        return res

    def perf(a):
        n = a * JOURS
        return float((1 + s.iloc[-n:]).prod() - 1) if len(s) >= n * 0.95 else None

    v = (1 + s.iloc[-5 * JOURS:]).cumprod()
    res.update(depuis=str(s.index[0].date()), perf_1a=perf(1), perf_3a=perf(3), perf_5a=perf(5),
               vol_hist=float(s.iloc[-3 * JOURS:].std() * np.sqrt(JOURS)), perte_max=float((v / v.cummax() - 1).min()))
    for cle, sc in calcul_analyses.SCENARIOS.items():
        if sc["dates"]:
            x = s.loc[sc["dates"][0]:sc["dates"][1]]
            if not x.empty and x.index[0] <= pd.Timestamp(sc["dates"][0]) + pd.Timedelta(days=7):
                res["crises"][cle] = float((1 + x).prod() - 1)
    return res


def base100(pf: dict, annees: int = 5) -> pd.Series:
    s, _ = serie(pf)
    s = s.iloc[-annees * JOURS:]
    return (1 + s).cumprod() * 100


def rejeu(pf: dict, cle: str) -> pd.Series | None:
    """Valeur (base 100) du portefeuille pendant une crise passée : la « machine à remonter le temps »."""
    sc = calcul_analyses.SCENARIOS[cle]
    if not sc["dates"]:
        return None
    s, _ = serie(pf)
    debut = pd.Timestamp(sc["dates"][0])
    x = s.loc[debut - pd.Timedelta(days=30): pd.Timestamp(sc["dates"][1]) + pd.Timedelta(days=365)]
    if x.empty or x.index[0] > debut:
        return None
    return (1 + x).cumprod() * 100 / float((1 + x.loc[:debut]).prod())


def volatilite_titre(isin: str, annees: int = 3) -> float | None:
    """Volatilité annualisée d'une ligne sur les dernières années (critère de sélection du satellite actions)."""
    p = prix()
    if isin not in p.columns:
        return None
    r = p[isin].dropna().pct_change().dropna().iloc[-annees * JOURS:]
    return float(r.std() * np.sqrt(JOURS)) if len(r) > 120 else None


def poids_derives(pf: dict, depuis: str, jusqua: str | None = None) -> dict:
    """Poids actuels d'un portefeuille investi à la date `depuis` et laissé dériver (pour le rééquilibrage)."""
    rend = rendements(pf).loc[pd.Timestamp(depuis):(pd.Timestamp(jusqua) if jusqua else None)]
    if rend.empty:
        return dict(pf)
    croissance = (1 + rend.fillna(0)).prod()
    valeurs = {i: w * float(croissance[i]) for i, w in pf.items()}
    total = sum(valeurs.values())
    return {i: v / total for i, v in valeurs.items()}


def performance_depuis(pf: dict, depuis: str) -> float | None:
    rend = rendements(pf).loc[pd.Timestamp(depuis):]
    if rend.empty:
        return None
    croissance = (1 + rend.fillna(0)).prod()
    return float(sum(w * croissance[i] for i, w in pf.items()) - 1)
