"""
calcul_analyses.py — Hypothèses de marché, risque attendu, frontière de Markowitz, simulation Monte Carlo,
stress tests, fiscalité des enveloppes et indicateurs de durabilité.

UNE SEULE mesure du risque fait foi dans l'outil : la volatilité ATTENDUE calculée ici (hypothèses Amundi +
corrélations de long terme). Elle sert à la grille des profils, au contrôle de conformité, à la frontière et à la
simulation. La volatilité historique (calcul_marches) n'est qu'une information complémentaire.
"""

from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
from scipy.optimize import minimize

import donnees

# ====================================================================================================
# 1. Hypothèses de marché
# Amundi Investment Institute, « Capital Market Assumptions — H2 update », août 2026, horizon 10 ans,
# rendements nominaux annuels en devise locale, bruts de frais. (rendement, volatilité)
# ====================================================================================================
SOURCE_HYPOTHESES = "Amundi Investment Institute, Capital Market Assumptions H2 update, août 2026, horizon 10 ans"
HYPOTHESES = {
    "euro_cash": (0.019, 0.010),
    "euro_gov": (0.037, 0.051),
    "euro_ig": (0.035, 0.050),
    "euro_hy": (0.046, 0.125),
    "actions_monde": (0.079, 0.154),
    "actions_usa": (0.080, 0.158),
    "actions_europe": (0.079, 0.162),
    "actions_emergents": (0.077, 0.162),
    "or": (0.064, 0.145),
    "immobilier_cote": (0.059, 0.121),   # ligne ambiguë dans l'extraction texte du PDF : à confirmer dans le tableau source
}
INFLATION = 0.02                 # cible de la BCE, pour exprimer les montants « en euros d'aujourd'hui »
RISQUE_SPECIFIQUE = 0.20         # risque propre d'une action seule (hypothèse), en plus du risque de son marché

# Sous-classe de l'univers -> mélange de classes d'hypothèses (« approximation » = pas d'équivalent exact)
CORRESPONDANCE = {
    "monde": {"actions_monde": 1.0}, "usa": {"actions_usa": 1.0}, "europe": {"actions_europe": 1.0},
    "france": {"actions_europe": 1.0},                         # approximation : pas de ligne France dans la source
    "emergents": {"actions_emergents": 1.0},
    "thematique": {"actions_monde": 1.0},                      # approximation : sous-estime le risque d'un thème
    "satellite": {"actions_europe": 1.0},                      # + risque spécifique de chaque titre
    "etat": {"euro_gov": 1.0}, "etat_court": {"euro_gov": 0.5, "euro_cash": 0.5},
    "ig": {"euro_ig": 1.0}, "haut_rendement": {"euro_hy": 1.0}, "monetaire": {"euro_cash": 1.0},
    "or": {"or": 1.0}, "immobilier": {"immobilier_cote": 1.0},
    "scpi": {"immobilier_cote": 0.5, "euro_gov": 0.5},         # approximation : SCPI moins volatile que la foncière cotée
    "patrimonial": {"actions_monde": 0.5, "euro_gov": 0.5}, "actions_actif": {"actions_monde": 1.0},
}
CLASSES = list(HYPOTHESES)
NOMS_CLASSES = {"euro_cash": ("Monétaire", "Money market"), "euro_gov": ("Obligations d'État", "Government bonds"),
                "euro_ig": ("Obligations d'entreprises", "Corporate bonds"), "euro_hy": ("Haut rendement", "High yield"),
                "actions_monde": ("Actions monde", "World equities"), "actions_usa": ("Actions États-Unis", "US equities"),
                "actions_europe": ("Actions Europe", "European equities"), "actions_emergents": ("Actions émergentes", "EM equities"),
                "or": ("Or", "Gold"), "immobilier_cote": ("Immobilier coté", "Listed real estate"),
                "fonds_euros": ("Fonds en euros", "Euro fund"), "specifique": ("Risque propre des titres", "Stock-specific risk")}

# Corrélations de long terme (ordres de grandeur, hypothèse pédagogique documentée dans la Méthodologie)
_C = {
    ("euro_gov", "euro_ig"): 0.80, ("euro_gov", "euro_hy"): 0.20, ("euro_ig", "euro_hy"): 0.60,
    ("actions_monde", "actions_usa"): 0.97, ("actions_monde", "actions_europe"): 0.88,
    ("actions_monde", "actions_emergents"): 0.75, ("actions_usa", "actions_europe"): 0.80,
    ("actions_usa", "actions_emergents"): 0.65, ("actions_europe", "actions_emergents"): 0.70,
    ("immobilier_cote", "actions_monde"): 0.75, ("immobilier_cote", "actions_usa"): 0.70,
    ("immobilier_cote", "actions_europe"): 0.72, ("immobilier_cote", "actions_emergents"): 0.60,
    ("immobilier_cote", "euro_gov"): 0.20, ("immobilier_cote", "euro_ig"): 0.40, ("immobilier_cote", "euro_hy"): 0.60,
    ("or", "euro_gov"): 0.20, ("or", "euro_ig"): 0.20, ("or", "euro_hy"): 0.10, ("or", "immobilier_cote"): 0.15,
}
for _a in ("actions_monde", "actions_usa", "actions_europe", "actions_emergents"):
    _C[("euro_gov", _a)], _C[("euro_ig", _a)], _C[("euro_hy", _a)], _C[("or", _a)] = 0.0, 0.30, 0.70, 0.10
for _a in CLASSES[1:]:
    _C.setdefault(("euro_cash", _a), 0.05)


def _matrice() -> np.ndarray:
    c = np.eye(len(CLASSES))
    for (a, b), v in _C.items():
        i, j = CLASSES.index(a), CLASSES.index(b)
        c[i, j] = c[j, i] = v
    vals, vecs = np.linalg.eigh(c)                        # garantit une matrice semi-définie positive
    c = vecs @ np.diag(np.clip(vals, 1e-6, None)) @ vecs.T
    d = np.sqrt(np.diag(c))
    return c / np.outer(d, d)


CORRELATIONS = _matrice()
MU = np.array([HYPOTHESES[c][0] for c in CLASSES])
SIGMA = np.array([HYPOTHESES[c][1] for c in CLASSES])
COV = np.outer(SIGMA, SIGMA) * CORRELATIONS


def classe_sri(vol: float | None) -> int | None:
    """Classe de risque de marché selon les seuils de volatilité du règlement PRIIPs (estimation)."""
    if vol is None:
        return None
    for seuil, k in [(0.005, 1), (0.05, 2), (0.12, 3), (0.20, 4), (0.30, 5), (0.80, 6)]:
        if vol < seuil:
            return k
    return 7


def taux_fonds_euros() -> float:
    u = donnees.univers()
    return float(u.loc["FONDS-EUROS", "taux_num"]) if "FONDS-EUROS" in u.index else 0.0265


def hypotheses_ligne(isin: str) -> tuple[float, float]:
    """(rendement attendu NET des frais du fonds, volatilité) d'une ligne, hors risque spécifique."""
    l = donnees.ligne(isin)
    if l["sous_classe"] == "fonds_euros":
        return float(l["taux_num"]), 0.0                  # taux servi, déjà net des frais de gestion du contrat
    melange = CORRESPONDANCE[l["sous_classe"]]
    mu = sum(p * HYPOTHESES[c][0] for c, p in melange.items())
    sigma = sum(p * HYPOTHESES[c][1] for c, p in melange.items())
    ter = l["ter_num"]
    return mu - (0.0 if ter != ter else float(ter)), sigma


def exposition(pf: dict) -> dict[str, float]:
    """Décompose un portefeuille {ligne: poids} sur les classes d'hypothèses (+ « fonds_euros »)."""
    u = donnees.univers()
    expo: dict[str, float] = {}
    for isin, w in pf.items():
        sc = u.loc[isin, "sous_classe"]
        for c, p in ({"fonds_euros": 1.0} if sc == "fonds_euros" else CORRESPONDANCE[sc]).items():
            expo[c] = expo.get(c, 0.0) + w * p
    return expo


def variance_specifique(pf: dict) -> float:
    u = donnees.univers()
    return sum((w ** 2) * RISQUE_SPECIFIQUE ** 2 for i, w in pf.items() if u.loc[i, "type"] == "action")


def point(pf: dict) -> tuple[float, float]:
    """(volatilité attendue, rendement attendu BRUT) d'un portefeuille."""
    e = exposition(pf)
    w = np.array([e.get(c, 0.0) for c in CLASSES])
    mu = float(w @ MU) + e.get("fonds_euros", 0.0) * taux_fonds_euros()
    var = float(w @ COV @ w) + variance_specifique(pf)
    return math.sqrt(max(var, 0.0)), mu


def contributions(pf: dict) -> dict[str, tuple[float, float]]:
    """Par classe : (poids, part du risque total). La part du risque vaut w_i (Σw)_i / σ² ; la somme fait 1."""
    e = exposition(pf)
    w = np.array([e.get(c, 0.0) for c in CLASSES])
    spec = variance_specifique(pf)
    var = float(w @ COV @ w) + spec
    if var <= 0:
        return {}
    rc = w * (COV @ w) / var
    res = {c: (float(w[i]), float(rc[i])) for i, c in enumerate(CLASSES) if w[i] > 1e-4}
    if e.get("fonds_euros", 0) > 1e-4:
        res["fonds_euros"] = (float(e["fonds_euros"]), 0.0)
    if spec > 0:
        res["specifique"] = (0.0, spec / var)
    return dict(sorted(res.items(), key=lambda x: -x[1][1]))


# ====================================================================================================
# 2. Frontière efficiente de Markowitz (moyenne-variance, sans vente à découvert, scipy SLSQP)
# ====================================================================================================
def _min_variance(mu, cov, cible=None):
    n = len(mu)
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1}]
    if cible is not None:
        cons.append({"type": "eq", "fun": lambda w: w @ mu - cible})
    res = minimize(lambda w: w @ cov @ w, np.full(n, 1 / n), method="SLSQP", bounds=[(0.0, 1.0)] * n,
                   constraints=cons, options={"maxiter": 300, "ftol": 1e-12})
    return res.x if res.success else None


@lru_cache(maxsize=2)
def frontiere(avec_fonds_euros: bool = False, n_points: int = 40) -> list[dict]:
    mu, cov, noms = MU.copy(), COV.copy(), list(CLASSES)
    if avec_fonds_euros:
        mu, cov, noms = np.append(mu, taux_fonds_euros()), np.pad(cov, ((0, 1), (0, 1))), noms + ["fonds_euros"]
    w0 = _min_variance(mu, cov)
    pts = []
    for cible in np.linspace(float(w0 @ mu) if w0 is not None else float(mu.min()), float(mu.max()), n_points):
        w = _min_variance(mu, cov, float(cible))
        if w is None:
            continue
        w = np.clip(w, 0, None)
        w /= w.sum()
        pts.append({"vol": float(np.sqrt(w @ cov @ w)), "mu": float(w @ mu),
                    "poids": {nom: float(x) for nom, x in zip(noms, w) if x > 1e-4}})
    return pts


def rendement_frontiere(vol: float, avec_fonds_euros: bool = False) -> float | None:
    pts = frontiere(avec_fonds_euros)
    if not pts:
        return None
    vols, mus = np.array([p["vol"] for p in pts]), np.array([p["mu"] for p in pts])
    return float(mus[0]) if vol <= vols[0] else float(np.interp(vol, vols, mus))


def max_sharpe() -> dict:
    rf = HYPOTHESES["euro_cash"][0]
    return max((p for p in frontiere(False) if p["vol"] > 1e-6), key=lambda p: (p["mu"] - rf) / p["vol"])


PORTEFEUILLE_6040 = {"IE00B4L5Y983": 0.60, "IE00B4WXJJ64": 0.40}    # MSCI World + emprunts d'État euro


def analyse_markowitz(pf: dict) -> dict:
    vol, mu = point(pf)
    avec_fe = "FONDS-EUROS" in pf
    mu_f = rendement_frontiere(vol, avec_fe)
    rf = HYPOTHESES["euro_cash"][0]
    return {"vol": vol, "mu": mu, "sharpe": (mu - rf) / vol if vol > 0 else None, "mu_frontiere": mu_f,
            "ecart": None if mu_f is None else mu - mu_f, "avec_fonds_euros": avec_fe, "rf": rf,
            "frontiere": frontiere(False), "frontiere_fe": frontiere(True) if avec_fe else None,
            "max_sharpe": max_sharpe(), "ref_6040": point(PORTEFEUILLE_6040), "contributions": contributions(pf)}


# ====================================================================================================
# 3. Simulation Monte Carlo (10 000 trajectoires, pas mensuel, rendement log-normal)
# - rendement attendu NET : frais des fonds (TER) et frais du contrat d'assurance-vie sur la seule part en unités
#   de compte (le taux du fonds en euros est déjà net) ;
# - versements (ou retraits) mensuels en fin de mois ; un capital ne descend jamais sous 0 ;
# - montants nominaux et, en parallèle, « en euros d'aujourd'hui » (inflation de 2 %).
# ====================================================================================================
FRAIS_ENVELOPPE = {"assurance-vie": 0.0060, "PEA": 0.0, "CTO": 0.0}   # frais annuels de l'enveloppe (indicatifs)


def frais_contrat(pf: dict, enveloppe: str) -> float:
    """Frais du contrat en % du portefeuille : 0,60 % sur la part en unités de compte en assurance-vie."""
    if enveloppe != "assurance-vie":
        return 0.0
    return FRAIS_ENVELOPPE["assurance-vie"] * (1 - pf.get("FONDS-EUROS", 0.0))


def frais_fonds(pf: dict) -> tuple[float, list[str]]:
    """Frais annuels moyens pondérés des fonds (TER) ; lignes sans frais connus signalées."""
    u = donnees.univers()
    total, inconnus = 0.0, []
    for isin, w in pf.items():
        ter = u.loc[isin, "ter_num"]
        if ter == ter:
            total += w * float(ter)
        elif u.loc[isin, "type"] != "action" and u.loc[isin, "sous_classe"] != "fonds_euros":
            inconnus.append(u.loc[isin, "nom"])
    return total, inconnus


FRAIS_ENTREE_SCPI = 0.12                 # commission de souscription Immorente : 10 % HT = 12 % TTC (note d'information Sofidy, 08/2026)
DUREE_AMORTISSEMENT_SCPI = 10            # amortis sur 10 ans dans le calcul des frais annuels


def frais_totaux(pf: dict, enveloppe: str) -> dict:
    fonds, inconnus = frais_fonds(pf)
    scpi = pf.get("SCPI-IMMORENTE", 0.0) * FRAIS_ENTREE_SCPI / DUREE_AMORTISSEMENT_SCPI
    contrat = frais_contrat(pf, enveloppe)
    return {"fonds": fonds, "scpi": scpi, "contrat": contrat, "total": fonds + scpi + contrat, "inconnus": inconnus}


def rendement_net(pf: dict, enveloppe: str) -> float:
    """Rendement attendu net de tous les frais (TER, frais d'entrée SCPI amortis, contrat)."""
    mu = sum(w * hypotheses_ligne(i)[0] for i, w in pf.items())
    return mu - frais_contrat(pf, enveloppe) - pf.get("SCPI-IMMORENTE", 0.0) * FRAIS_ENTREE_SCPI / DUREE_AMORTISSEMENT_SCPI


def _trajectoires(mu, sigma, montant, flux, ans, n, rng) -> np.ndarray:
    mois = ans * 12
    chocs = rng.standard_normal((n, mois)) * (sigma / math.sqrt(12)) + math.log1p(mu) / 12
    croissance = np.exp(chocs)
    valeurs = np.empty((n, ans + 1))
    valeurs[:, 0] = montant
    v = np.full(n, float(montant))
    for m in range(mois):
        v = np.maximum(v * croissance[:, m] + flux, 0.0)
        if (m + 1) % 12 == 0:
            valeurs[:, (m + 1) // 12] = v
    return valeurs


def simuler(pf: dict, enveloppe: str, montant: float, versement: float, retrait: float, ans: int, cible: float,
            n: int = 10_000, graine: int = 42) -> dict:
    """Quantiles 10/50/90 % chaque année, probabilité d'atteindre la cible, références 60/40 et gestion traditionnelle."""
    ans = max(1, int(ans))
    flux = (versement or 0) - (retrait or 0)
    mu = rendement_net(pf, enveloppe)
    vol, _ = point(pf)
    traj = _trajectoires(mu, vol, montant, flux, ans, n, np.random.default_rng(graine))
    q = np.percentile(traj, [10, 50, 90], axis=0)
    v64, _ = point(PORTEFEUILLE_6040)
    mu64 = rendement_net(PORTEFEUILLE_6040, "CTO")
    q64 = np.percentile(_trajectoires(mu64, v64, montant, flux, ans, n, np.random.default_rng(graine + 1)), 50, axis=0)
    deflateur = np.array([(1 + INFLATION) ** -a for a in range(ans + 1)])
    return {"p10": q[0].tolist(), "p50": q[1].tolist(), "p90": q[2].tolist(), "ref_6040": q64.tolist(),
            "p50_reel": (q[1] * deflateur).tolist(), "p10_reel": (q[0] * deflateur).tolist(),
            "verse": [montant + flux * 12 * a for a in range(ans + 1)],
            "proba_cible": float((traj[:, -1] >= cible).mean()) if cible and cible > 0 else None,
            "proba_epuisement": float((traj[:, -1] <= 0).mean()) if flux < 0 else None,
            "mu": mu, "vol": vol, "n": n, "ans": ans}


def capital_deterministe(montant, flux, ans, rendement) -> list[float]:
    r = (1 + rendement) ** (1 / 12) - 1
    v, res = float(montant), [float(montant)]
    for m in range(int(ans) * 12):
        v = max(v * (1 + r) + flux, 0.0)
        if (m + 1) % 12 == 0:
            res.append(v)
    return res


# ====================================================================================================
# 4. Stress tests : chocs par grande classe (ordres de grandeur des crises, en euros) ou chocs hypothétiques
# ====================================================================================================
SCENARIOS = {
    "crise_2008": {"nom": ("Crise financière 2007-2009", "Global financial crisis 2007-2009"),
                   "periode": ("oct. 2007 – mars 2009", "Oct 2007 – Mar 2009"), "dates": ("2007-10-09", "2009-03-09"),
                   "recit": ("Faillite de Lehman Brothers, gel du crédit, récession mondiale.",
                             "Lehman collapse, credit freeze, global recession."),
                   "chocs": {"euro_cash": 0.05, "euro_gov": 0.12, "euro_ig": 0.03, "euro_hy": -0.30, "actions_monde": -0.52,
                             "actions_usa": -0.50, "actions_europe": -0.58, "actions_emergents": -0.60, "or": 0.25,
                             "immobilier_cote": -0.65, "fonds_euros": 0.06}},
    "covid_2020": {"nom": ("Krach du Covid-19", "Covid-19 crash"), "periode": ("févr. – mars 2020", "Feb – Mar 2020"),
                   "dates": ("2020-02-19", "2020-03-23"),
                   "recit": ("Confinements mondiaux, puis rebond rapide grâce aux banques centrales.",
                             "Global lockdowns, then a fast rebound driven by central banks."),
                   "chocs": {"euro_cash": 0.0, "euro_gov": -0.01, "euro_ig": -0.07, "euro_hy": -0.18, "actions_monde": -0.33,
                             "actions_usa": -0.33, "actions_europe": -0.37, "actions_emergents": -0.32, "or": -0.03,
                             "immobilier_cote": -0.40, "fonds_euros": 0.0}},
    "taux_2022": {"nom": ("Remontée des taux 2022", "2022 rate hikes"), "periode": ("janv. – déc. 2022", "Jan – Dec 2022"),
                  "dates": ("2021-12-31", "2022-12-30"),
                  "recit": ("Inflation au plus haut depuis 40 ans : actions et obligations baissent ensemble.",
                            "40-year-high inflation: stocks and bonds fall together."),
                  "chocs": {"euro_cash": 0.0, "euro_gov": -0.18, "euro_ig": -0.14, "euro_hy": -0.11, "actions_monde": -0.13,
                            "actions_usa": -0.14, "actions_europe": -0.10, "actions_emergents": -0.15, "or": 0.06,
                            "immobilier_cote": -0.35, "fonds_euros": 0.02}},
    "krach_actions": {"nom": ("Krach actions de 30 %", "30% equity crash"), "periode": ("choc hypothétique", "hypothetical shock"),
                      "dates": None,
                      "recit": ("Les actions mondiales perdent 30 % ; les emprunts d'État amortissent.",
                                "World equities lose 30%; government bonds cushion."),
                      "chocs": {"euro_cash": 0.0, "euro_gov": 0.03, "euro_ig": -0.02, "euro_hy": -0.10, "actions_monde": -0.30,
                                "actions_usa": -0.30, "actions_europe": -0.30, "actions_emergents": -0.33, "or": 0.05,
                                "immobilier_cote": -0.20, "fonds_euros": 0.0}},
    "choc_taux": {"nom": ("Hausse des taux de 2 points", "Rates up 2 points"), "periode": ("choc hypothétique", "hypothetical shock"),
                  "dates": None,
                  "recit": ("Les taux montent brutalement de 2 points : les obligations longues baissent le plus.",
                            "Rates jump 2 points: long bonds fall the most."),
                  "chocs": {"euro_cash": 0.0, "euro_gov": -0.14, "euro_ig": -0.09, "euro_hy": -0.08, "actions_monde": -0.10,
                            "actions_usa": -0.10, "actions_europe": -0.10, "actions_emergents": -0.12, "or": -0.05,
                            "immobilier_cote": -0.15, "fonds_euros": 0.0}},
}


def stress(pf: dict, montant: float, cle: str, langue: str = "fr") -> dict:
    s = SCENARIOS[cle]
    i = 1 if langue == "en" else 0
    lignes = {isin: sum(p * s["chocs"].get(c, 0.0) for c, p in exposition({isin: 1.0}).items()) for isin in pf}
    variation = sum(pf[k] * v for k, v in lignes.items())
    par_classe: dict[str, float] = {}
    for isin, w in pf.items():
        c = donnees.classe(isin)
        par_classe[c] = par_classe.get(c, 0.0) + w * lignes[isin]
    _, mu = point(pf)
    recup = math.log(1 / (1 + variation)) / math.log(1 + mu) if variation < 0 and mu > 0 else None
    pires = sorted(lignes.items(), key=lambda x: pf[x[0]] * x[1])[:4]
    return {"cle": cle, "nom": s["nom"][i], "periode": s["periode"][i], "recit": s["recit"][i], "variation": variation,
            "euros": variation * montant, "apres": montant * (1 + variation), "par_classe": par_classe,
            "recuperation": recup, "pires": [(donnees.nom(k), v, pf[k] * v * montant) for k, v in pires if v < 0]}


def tous_les_stress(pf: dict, montant: float, langue: str = "fr") -> list[dict]:
    return [stress(pf, montant, k, langue) for k in SCENARIOS]


# ====================================================================================================
# 5. Fiscalité au moment du retrait total (règles 2026)
# CTO : PFU 31,4 % (12,8 % + 18,6 %). PEA : après 5 ans, 18,6 % ; avant, 31,4 % ; 150 000 € de versements max.
# Assurance-vie : prélèvements sociaux 17,2 % (exclue de la hausse de CSG 2026) ; après 8 ans, abattement
# 4 600 € / 9 200 € puis 7,5 % (12,8 % sur la part des primes au-delà de 150 000 €) ; avant 8 ans, 12,8 %.
# ====================================================================================================
PS_CTO_PEA, PS_AV, IR_PFU, IR_AV_8ANS = 0.186, 0.172, 0.128, 0.075
ABATTEMENT_AV = {"seul": 4_600, "couple": 9_200}
SEUIL_AV = PLAFOND_PEA = 150_000


def capital_final(montant, versement, ans, rendement) -> float:
    return capital_deterministe(montant, versement, ans, rendement)[-1]


def comparer_enveloppes(pf: dict, montant: float, versement: float, ans: int, foyer: str = "seul", langue: str = "fr") -> list[dict]:
    """Capital net de frais et d'impôts au retrait total, pour le MÊME portefeuille dans chaque enveloppe.
    En PEA, seules les lignes éligibles y sont logées (dans la limite de 150 000 €) ; le reste va en compte-titres."""
    u = donnees.univers()
    ans = max(1, int(ans))
    verse = montant + versement * 12 * ans
    noms = {"assurance-vie": ("Assurance-vie", "Life insurance"), "PEA": ("PEA + compte-titres", "PEA + securities account"),
            "CTO": ("Compte-titres", "Securities account")}
    res = []
    for env in ("assurance-vie", "PEA", "CTO"):
        if env == "PEA":
            part = min(sum(w for i, w in pf.items() if u.loc[i, "pea"] == "oui"), PLAFOND_PEA / verse if verse else 0)
            r = rendement_net(pf, "PEA")
            cap_pea = capital_final(montant * part, versement * part, ans, r)
            cap_cto = capital_final(montant * (1 - part), versement * (1 - part), ans, r)
            g1, g2 = max(cap_pea - verse * part, 0), max(cap_cto - verse * (1 - part), 0)
            ir = (0.0 if ans >= 5 else g1 * IR_PFU) + g2 * IR_PFU
            ps = (g1 + g2) * PS_CTO_PEA
            brut = cap_pea + cap_cto
        else:
            brut = capital_final(montant, versement, ans, rendement_net(pf, env))
            g = max(brut - verse, 0)
            if env == "CTO":
                ir, ps = g * IR_PFU, g * PS_CTO_PEA
            else:
                ps = g * PS_AV
                if ans < 8:
                    ir = g * IR_PFU
                else:
                    base = max(g - ABATTEMENT_AV.get(foyer, 4_600), 0)
                    bas = min(1.0, SEUIL_AV / verse) if verse else 1.0
                    ir = base * (bas * IR_AV_8ANS + (1 - bas) * IR_PFU)
            part = None
        gain = brut - verse
        res.append({"enveloppe": env, "nom": noms[env][1 if langue == "en" else 0], "verse": verse, "brut": brut,
                    "ir": ir, "ps": ps, "impots": ir + ps, "net": brut - ir - ps, "taux": (ir + ps) / gain if gain > 0 else 0.0,
                    "part_pea": part})
    for x in res:
        x["applicable"] = not (x["enveloppe"] == "PEA" and not x["part_pea"])
    meilleur = max((x for x in res if x["applicable"]), key=lambda x: x["net"])["enveloppe"]
    for x in res:
        x["meilleur"] = x["enveloppe"] == meilleur
    return res


def foyer(reponses: dict) -> str:
    return "couple" if reponses.get("situation_familiale") in ("couple", "couple_enfants") else "seul"


# ====================================================================================================
# 6. Durabilité : part ISR, classement SFDR, exclusions, intensité carbone ESTIMÉE (moyennes sectorielles)
# ====================================================================================================
INTENSITE_FONDS = {"monde": 100, "usa": 80, "europe": 90, "france": 90, "emergents": 300, "thematique": 140,
                   "immobilier": 50, "actions_actif": 90, "patrimonial": 70, "scpi": 30, "ig": 110, "haut_rendement": 150}
INTENSITE_SECTEUR = {"Services publics": 500, "Énergie": 450, "Transport aérien": 800, "Matériaux": 600,
                     "Énergie propre": 100, "Industrie": 120, "Aéronautique": 60, "Défense": 40, "Consommation de base": 60,
                     "Consommation": 40, "Luxe": 15, "Santé": 15, "Technologie": 15, "Communication": 20, "Finance": 5}
REFERENCE_MONDE = 100


def durabilite(pf: dict) -> dict:
    u = donnees.univers()
    isr = sum(w for i, w in pf.items() if u.loc[i, "version"] == "durable")
    sfdr: dict[str, float] = {}
    for i, w in pf.items():
        s = str(u.loc[i, "sfdr"]).strip()
        cle = s if s in ("6", "8", "9") else ("titre" if u.loc[i, "type"] == "action" else "à vérifier")
        sfdr[cle] = sfdr.get(cle, 0.0) + w
    inten, poids = 0.0, 0.0
    for i, w in pf.items():
        l = u.loc[i]
        v = INTENSITE_SECTEUR.get(l["secteur"], 100) if l["type"] == "action" else INTENSITE_FONDS.get(l["sous_classe"])
        if v is not None:
            inten, poids = inten + w * v, poids + w
    return {"part_isr": isr, "sfdr": sfdr, "intensite": inten / poids if poids else None, "couverture": poids,
            "reference": REFERENCE_MONDE}
