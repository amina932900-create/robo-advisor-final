"""
calcul_portefeuille.py — Construction du portefeuille et « fil de décision ».

Principe : aucune part de hasard. Les mêmes réponses donnent toujours le même portefeuille, et chaque étape
enregistre la règle appliquée, les données utilisées et leur source (le fil de décision, affiché par l'outil,
repris dans la déclaration d'adéquation).

Architecture cœur-satellite :
- cœur : ETF actions et obligations, monétaire, fonds en euros (assurance-vie) ;
- satellite : SCPI (assurance-vie, horizon > 8 ans), un fonds actif (5 %), et pour les profils 4-5 avec de bonnes
  connaissances, une poche d'actions européennes en direct (PEA ou compte-titres).
"""

from __future__ import annotations

import calcul_analyses
import calcul_profil
import donnees
from calcul_profil import T
from textes import date_txt

# ====================================================================================================
# 1. Grille des profils
# Fourchettes de volatilité ATTENDUE calées sur le modèle (hypothèses Amundi + corrélations) ;
# SRI maximum du portefeuille = classe PRIIPs de la borne haute de la fourchette.
# ====================================================================================================
PROFILS = {
    1: {"allocation": {"actions": 0.10, "obligations": 0.35, "monetaire": 0.50, "diversifiants": 0.05, "scpi": 0.0, "actif": 0.0},
        "vol": (0.02, 0.04), "sri_max": 2},
    2: {"allocation": {"actions": 0.25, "obligations": 0.35, "monetaire": 0.25, "diversifiants": 0.05, "scpi": 0.05, "actif": 0.05},
        "vol": (0.04, 0.07), "sri_max": 3},
    3: {"allocation": {"actions": 0.45, "obligations": 0.30, "monetaire": 0.10, "diversifiants": 0.05, "scpi": 0.05, "actif": 0.05},
        "vol": (0.07, 0.10), "sri_max": 3},
    4: {"allocation": {"actions": 0.65, "obligations": 0.15, "monetaire": 0.05, "diversifiants": 0.05, "scpi": 0.05, "actif": 0.05},
        "vol": (0.10, 0.13), "sri_max": 4},
    5: {"allocation": {"actions": 0.85, "obligations": 0.05, "monetaire": 0.00, "diversifiants": 0.05, "scpi": 0.0, "actif": 0.05},
        "vol": (0.13, 0.16), "sri_max": 4},
}
CLASSES = ["actions", "obligations", "monetaire", "diversifiants", "scpi", "actif"]

# Contraintes
MAX_LIGNE = 0.30            # 30 % maximum par ligne : diversification du risque de chaque émetteur ou gérant
MAX_HAUT_RENDEMENT = 0.10
MAX_EMERGENTS = 0.15
MAX_THEMATIQUE = 0.10
MAX_FONDS_EUROS = 0.30
MIN_LIGNE = 0.01            # une ligne de moins de 1 % est regroupée avec la principale de sa classe (frais de transaction)
AJUSTEMENT_MAX = 0.10       # le conseiller peut déplacer actions et obligations de ±10 points
PLAFOND_PEA = 150_000

# Répartition à l'intérieur des poches (part de la poche)
PART_EMERGENTS = {4: 0.10, 5: 0.15}                   # profils 1-3 : pas d'émergents (plus volatils)
PART_THEMATIQUE = 0.10                                 # thème vert, profils 4-5 avec préférence durable
SATELLITE_ACTIONS = {4: (0.10, 5), 5: (0.15, 8)}      # (part du portefeuille, nombre de titres)
ZONES = {"Monde": {"monde": 1.0}, "Europe": {"monde": 0.5, "europe": 0.5},
         "France": {"monde": 0.5, "europe": 0.25, "france": 0.25}}
DEBORDEMENT_MONDE = {"usa": 0.70, "europe": 0.30}     # poids régionaux approchés du MSCI World au-delà de 30 % sur l'ETF monde
OBLIGATIONS = {1: {"etat_court": 0.50, "etat": 0.30, "ig": 0.20, "haut_rendement": 0.0},
               2: {"etat_court": 0.35, "etat": 0.35, "ig": 0.30, "haut_rendement": 0.0},
               3: {"etat_court": 0.20, "etat": 0.35, "ig": 0.35, "haut_rendement": 0.10},
               4: {"etat_court": 0.15, "etat": 0.35, "ig": 0.40, "haut_rendement": 0.10},
               5: {"etat_court": 0.15, "etat": 0.35, "ig": 0.40, "haut_rendement": 0.10}}
DIVERSIFIANTS = {"or": 0.60, "immobilier": 0.40}
NOMS_POCHES = {"monde": ("Actions monde", "World equities"), "usa": ("Actions États-Unis", "US equities"),
               "europe": ("Actions Europe", "European equities"), "france": ("Actions France", "French equities"),
               "emergents": ("Actions émergentes", "EM equities"), "thematique": ("Thématique verte", "Green theme"),
               "etat": ("États zone euro", "Euro govies"), "etat_court": ("États 1-3 ans", "Euro govies 1-3y"),
               "ig": ("Entreprises de bonne qualité", "Investment grade"), "haut_rendement": ("Haut rendement", "High yield"),
               "monetaire": ("Monétaire", "Money market"), "fonds_euros": ("Fonds en euros", "Euro fund"),
               "or": ("Or", "Gold"), "immobilier": ("Immobilier coté", "Listed real estate"), "scpi": ("SCPI", "SCPI"),
               "patrimonial": ("Fonds patrimonial", "Multi-asset fund"), "actions_actif": ("Fonds actions actif", "Active equity fund"),
               "satellite": ("Actions européennes en direct", "Direct European stocks")}
SOURCE_GRILLE = "Grille interne ; fourchettes calées sur les hypothèses Amundi CMA 2026 ; seuils SRI du règlement PRIIPs"


def nom_profil(p: int, langue: str = "fr") -> str:
    return calcul_profil.nom_profil(p, langue)


def _pc(x, langue, d=0):
    from textes import pct_txt
    return pct_txt(x, d, langue)


# ====================================================================================================
# 2. Enveloppe
# ====================================================================================================
def choisir_enveloppe(reponses: dict, profil: int, langue: str = "fr") -> tuple[str, str, list[int]]:
    """(enveloppe, raison, questions citées). Le souhait du client est respecté ; la conformité signale s'il est peu adapté."""
    L, num = langue, lambda i: calcul_profil.q(i)["num"]
    voulue = reponses.get("enveloppe_souhaitee")
    if voulue in ("assurance-vie", "PEA", "CTO"):
        return voulue, T(L, "souhait exprimé par le client", "client's stated preference"), [num("enveloppe_souhaitee")]
    if reponses.get("objectif") in ("retraite", "transmission"):
        return "assurance-vie", T(L, "objectif retraite ou transmission : fiscalité après 8 ans et transmission hors succession",
                                  "retirement or estate goal: tax after 8 years and estate planning"), [num("objectif")]
    if reponses.get("horizon") in ("5-8", ">8") and profil >= 4:
        return "PEA", T(L, "horizon de plus de 5 ans et forte part d'actions : fiscalité allégée après 5 ans",
                        "horizon over 5 years and high equity share: lower tax after 5 years"), [num("horizon")]
    return "assurance-vie", T(L, "accès au fonds en euros (capital garanti) et fiscalité avantageuse",
                              "access to the euro fund and favourable tax"), [num("horizon"), num("objectif")]


def repartition_enveloppes(pf: dict, enveloppe: str, montant: float | None = None) -> dict:
    """Enveloppe de chaque ligne. PEA : lignes éligibles dans la limite de 150 000 € ; le reste en compte-titres."""
    if enveloppe != "PEA":
        return {i: enveloppe for i in pf}
    u = donnees.univers()
    res, verse = {}, 0.0
    for isin, w in sorted(pf.items(), key=lambda x: -x[1]):
        m = w * (montant or 0)
        if u.loc[isin, "pea"] == "oui" and (montant is None or verse + m <= PLAFOND_PEA):
            res[isin], verse = "PEA", verse + m
        else:
            res[isin] = "CTO"
    return res


# ====================================================================================================
# 3. Sélection des ETF : filtres puis classement par critères (aucun tirage)
# ====================================================================================================
def criteres(isin: str) -> dict:
    """Critères du cahier des charges : encours > 500 M€, réplication physique, au moins 5 ans d'historique."""
    l = donnees.ligne(isin)
    enc, anc = l["encours_num"], l["anciennete_ans"]
    return {"encours": None if enc != enc else bool(enc >= 500),
            "physique": None if l["replication"] in ("", "TODO") else str(l["replication"]).startswith("Physique"),
            "historique": None if anc != anc else bool(anc >= 5)}


def classer_etf(sous_classe: str, durable: bool, enveloppe: str, langue: str = "fr") -> list[dict]:
    """Candidats d'une poche, classés. Chaque candidat porte ses critères et la raison de son rang."""
    L = langue
    u = donnees.univers()
    df = u[(u["sous_classe"] == sous_classe) & (u["type"] == "fonds")]
    voulue = "durable" if durable else "standard"
    a_la_version = (df["version"] == voulue).any()
    res = []
    for isin, l in df.iterrows():
        ok_version = l["version"] in (voulue, "commun") or not a_la_version
        pea = l["pea"] == "oui"
        crit = criteres(isin)
        manque = sum(1 for v in crit.values() if v is not True)
        rang_pea = 0 if (enveloppe != "PEA" or l["classe"] != "actions" or pea) else 1
        ter = l["ter_num"] if l["ter_num"] == l["ter_num"] else 9.0
        enc = l["encours_num"] if l["encours_num"] == l["encours_num"] else 0.0
        res.append({"isin": isin, "nom": l["nom"], "ter": None if ter == 9.0 else ter, "encours": enc or None,
                    "replication": l["replication"], "anciennete": l["anciennete_ans"], "pea": pea, "version": l["version"],
                    "criteres": crit, "ok_version": ok_version,
                    "cle": (0 if ok_version else 1, rang_pea, manque, ter, -enc)})
    res.sort(key=lambda c: c["cle"])
    for k, c in enumerate(res):
        if not c["ok_version"]:
            c["motif"] = T(L, "version ISR non demandée" if not durable else "version standard (une version ISR existe)",
                           "SRI version not requested" if not durable else "standard version (an SRI one exists)")
        elif k == 0:
            raisons = []
            if enveloppe == "PEA" and c["pea"] and sous_classe in ("monde", "usa", "europe", "france", "emergents"):
                raisons.append(T(L, "éligible au PEA", "PEA-eligible"))
            if durable and c["version"] == "durable":
                raisons.append(T(L, "version ISR", "SRI version"))
            rivaux = [r for r in res if r["cle"][:2] == c["cle"][:2]]
            if len(rivaux) > 1:
                raisons.append(T(L, "frais les plus bas à critères égaux", "lowest fees, other criteria equal"))
            elif len(res) > 1:
                raisons.append(T(L, "seul candidat restant après ces filtres", "only candidate left after these filters"))
            else:
                raisons.append(T(L, "seul candidat de sa poche", "only candidate"))
            noms = {"encours": T(L, "encours > 500 M€", "AuM > €500m"), "physique": T(L, "réplication physique", "physical replication"),
                    "historique": T(L, "5 ans d'historique", "5-year track record")}
            manquants = [noms[k] for k, v in c["criteres"].items() if v is not True]
            if manquants:
                raisons.append(T(L, "critère(s) non rempli(s) : ", "criteria not met: ") + ", ".join(manquants))
            c["motif"] = ", ".join(raisons)
        else:
            premier = res[0]
            if c["cle"][1] > premier["cle"][1]:
                c["motif"] = T(L, "non éligible au PEA", "not PEA-eligible")
            elif c["cle"][2] > premier["cle"][2]:
                c["motif"] = T(L, "remplit moins de critères (encours, réplication, historique)", "meets fewer criteria")
            else:
                c["motif"] = T(L, "frais plus élevés", "higher fees")
    return res


# ====================================================================================================
# 4. Satellite « actions en direct » (profils 4-5) : un titre par secteur, le moins volatil de son secteur
# ====================================================================================================
def selection_satellite(n: int, enveloppe: str, exclusions, filtre_esg: bool, langue: str = "fr") -> list[dict]:
    import calcul_marches
    u = donnees.univers()
    df = u[(u["sous_classe"] == "satellite") & u["euro"]]
    if enveloppe == "PEA":
        df = df[df["pea"] == "oui"]
    excl = set(exclusions or [])
    if excl:
        df = df[~df["tags"].map(lambda s: bool(excl & set(str(s).split(";"))))]
    if filtre_esg:
        df = df[df["esg"] != "non"]
    candidats = []
    for isin, l in df.iterrows():
        v = calcul_marches.volatilite_titre(isin)
        if v is not None:
            candidats.append({"isin": isin, "nom": l["nom"], "secteur": l["secteur"], "pays": l["pays"], "vol": v})
    champions = {}
    for c in sorted(candidats, key=lambda c: (c["vol"], c["isin"])):
        champions.setdefault(c["secteur"], c)
    retenus = sorted(champions.values(), key=lambda c: (c["vol"], c["isin"]))[:n]
    for c in retenus:
        concurrents = sum(1 for x in candidats if x["secteur"] == c["secteur"])
        c["motif"] = T(langue, f"le moins volatil des {concurrents} titres du secteur {c['secteur']} (volatilité 3 ans {_pc(c['vol'], 'fr')})",
                       f"least volatile of {concurrents} stocks in {c['secteur']} (3-year volatility {_pc(c['vol'], 'en')})")
    return retenus


# ====================================================================================================
# 5. Construction
# ====================================================================================================
class AjustementRefuse(ValueError):
    pass


def allocation_cible(profil: int, ajustements: dict | None = None) -> dict:
    """Grille du profil, ajustée par le conseiller (±10 points ; la poche monétaire compense)."""
    alloc = dict(PROFILS[profil]["allocation"])
    a = ajustements or {}
    da, do = a.get("actions", 0.0), a.get("obligations", 0.0)
    if abs(da) > AJUSTEMENT_MAX + 1e-9 or abs(do) > AJUSTEMENT_MAX + 1e-9:
        raise AjustementRefuse("±10 points maximum par classe")
    alloc["actions"] += da
    alloc["obligations"] += do
    alloc["monetaire"] -= da + do
    for c in ("actions", "obligations", "monetaire"):
        if alloc[c] < -1e-9:
            raise AjustementRefuse({"monetaire": f"la poche monétaire ({PROFILS[profil]['allocation']['monetaire'] * 100:.0f} %) ne peut pas compenser ; "
                                                 "réduisez une autre classe d'autant",
                                    "obligations": "la poche obligataire deviendrait négative",
                                    "actions": "la poche actions deviendrait négative"}[c])
        alloc[c] = max(0.0, round(alloc[c], 6))
    return alloc


def recommander(reponses: dict, profil_calcule: dict, profil_retenu: int | None = None, ajustements: dict | None = None,
                meta: dict | None = None, langue: str = "fr") -> dict:
    """
    Construit la recommandation complète.
    profil_retenu : le conseiller peut BAISSER le profil (jamais le monter) ; ajustements : {"actions": +0.05, ...}.
    Renvoie portefeuille {isin: poids}, classes, lignes (raison + alternatives), enveloppes, fil de décision, risque.
    """
    L, r, meta = langue, reponses, meta or {}
    num = lambda i: calcul_profil.q(i)["num"]
    p_calc = profil_calcule["profil"]
    p = min(profil_retenu or p_calc, p_calc)
    fil = []

    def etape(titre, resultat, regle, details=(), source=""):
        fil.append({"n": len(fil) + 1, "titre": titre, "resultat": resultat, "regle": regle,
                    "details": list(details), "source": source})

    # --- 1. Questionnaire
    etape(T(L, "Questionnaire signé", "Signed questionnaire"),
          T(L, f"Signé le {date_txt(meta.get('date_signature'), L) or '—'}, référence {meta.get('reference', '—')}",
            f"Signed on {date_txt(meta.get('date_signature'), L) or '—'}, reference {meta.get('reference', '—')}"),
          T(L, "Aucune recommandation sans questionnaire signé par le client.", "No recommendation without a signed questionnaire."),
          [(T(L, f"Montant à investir : {r.get('montant', 0):,.0f} €".replace(",", " "), f"Amount: €{r.get('montant', 0):,.0f}"), [])],
          "MiFID II art. 25(2)")

    # --- 2. Quatre notes
    noms_notes = {"tolerance": T(L, "Tolérance", "Tolerance"), "horizon": "Horizon",
                  "capacite": T(L, "Capacité", "Capacity"), "connaissances": T(L, "Connaissances", "Knowledge")}
    details = []
    for k, v in profil_calcule["notes"].items():
        for texte, refs in profil_calcule["detail"][k]:
            details.append((f"{noms_notes[k]} {v}/5 — {texte}", refs))
    etape(T(L, "Quatre notes sur 5", "Four scores out of 5"),
          " · ".join(f"{noms_notes[k]} {v}" for k, v in profil_calcule["notes"].items()),
          T(L, "Chaque note se calcule à partir de réponses précises du questionnaire.", "Each score comes from specific answers."),
          details, T(L, "Orientations ESMA sur l'adéquation ; questionnaires BNP Paribas, Fortuneo, Boursorama",
                     "ESMA suitability guidelines"))

    # --- 3. Profil
    limit = ", ".join(noms_notes[k] for k in profil_calcule["limitant"])
    det = [(T(L, f"Note(s) limitante(s) : {limit}", f"Limiting score(s): {limit}"), [])]
    if p < p_calc:
        det.append((T(L, f"Profil abaissé de {p_calc} à {p} par le conseiller : {meta.get('motif_profil') or 'motif à saisir'}",
                      f"Profile lowered from {p_calc} to {p} by the adviser: {meta.get('motif_profil') or 'reason required'}"), []))
    etape(T(L, "Profil de risque", "Risk profile"), f"{p}/5 — {nom_profil(p, L)}",
          T(L, "Le profil est la plus petite des 4 notes ; il peut être abaissé, jamais relevé.",
            "Profile = lowest of the 4 scores; it may be lowered, never raised."), det,
          T(L, "Règle prudente des banques ; MiFID II", "Prudent banking rule; MiFID II"))

    # --- 4. Allocation
    alloc = allocation_cible(p, ajustements)
    grille = PROFILS[p]["allocation"]
    noms_cl = {"fr": {"actions": "actions", "obligations": "obligations", "monetaire": "monétaire", "diversifiants": "or et immobilier coté",
                      "scpi": "SCPI", "actif": "fonds actif"},
               "en": {"actions": "equities", "obligations": "bonds", "monetaire": "money market", "diversifiants": "gold & real estate",
                      "scpi": "SCPI", "actif": "active fund"}}[L]
    det = [(T(L, "Grille ", "Grid ") + nom_profil(p, L) + " : " + ", ".join(f"{noms_cl[c]} {_pc(w, L)}" for c, w in grille.items() if w), [])]
    if ajustements and any(abs(v) > 1e-9 for v in ajustements.values()):
        det.append((T(L, f"Ajustement du conseiller : actions {ajustements.get('actions', 0) * 100:+.0f} pts, obligations "
                         f"{ajustements.get('obligations', 0) * 100:+.0f} pts, compensé par le monétaire — motif : "
                         f"{meta.get('motif_ajustement') or 'à saisir'}",
                      f"Adviser adjustment: equities {ajustements.get('actions', 0) * 100:+.0f} pts, bonds "
                      f"{ajustements.get('obligations', 0) * 100:+.0f} pts — reason: {meta.get('motif_ajustement') or 'required'}"), []))

    # --- 5. Enveloppe
    env_auto, raison_env, refs_env = choisir_enveloppe(r, p, L)
    env = meta.get("enveloppe_forcee") or env_auto
    det_env = [(raison_env, refs_env)]
    if env != env_auto:
        det_env.append((T(L, f"Choix du conseiller ({env} au lieu de {env_auto}) : {meta.get('motif_enveloppe') or 'motif à saisir'}",
                          f"Adviser choice ({env} instead of {env_auto}): {meta.get('motif_enveloppe') or 'reason required'}"), []))

    # --- 6. Satellite et règles d'enveloppe
    det_sat = []
    if alloc["scpi"] > 0 and not (env == "assurance-vie" and r.get("horizon") == ">8"):
        det_sat.append((T(L, f"SCPI ({_pc(alloc['scpi'], L)}) reportée sur les obligations : elle exige l'assurance-vie et un horizon de plus de 8 ans",
                          f"SCPI ({_pc(alloc['scpi'], L)}) moved to bonds: requires life insurance and an 8+ year horizon"),
                        [num("horizon")]))
        alloc["obligations"] += alloc["scpi"]
        alloc["scpi"] = 0.0
    elif alloc["scpi"] > 0:
        det_sat.append((T(L, f"SCPI retenue ({_pc(alloc['scpi'], L)}) : assurance-vie et horizon de plus de 8 ans (frais d'entrée, revente lente)",
                          f"SCPI kept ({_pc(alloc['scpi'], L)}): life insurance and 8+ year horizon"), [num("horizon")]))
    if alloc["actif"] > 0:
        det_sat.append((T(L, "Fonds actif : " + ("patrimonial (profils 2-3)" if p <= 3 else "actions (profils 4-5)") +
                          " ; ses frais plus élevés qu'un ETF sont affichés et assumés pour compléter la gestion passive",
                          "Active fund: " + ("multi-asset (profiles 2-3)" if p <= 3 else "equity (profiles 4-5)")), []))
    excl, filtre_esg = preferences_durables(r)
    durable = r.get("durabilite") not in (None, "aucune")
    n_conn = profil_calcule["notes"]["connaissances"]
    sat_part, sat_n = SATELLITE_ACTIONS.get(p, (0.0, 0))
    sat_ok = sat_part > 0 and env in ("PEA", "CTO") and n_conn >= 4
    if p >= 4 and not sat_ok:
        det_sat.append((T(L, "Pas d'actions en direct : réservées au PEA ou au compte-titres et à des connaissances d'au moins 4/5",
                          "No direct stocks: PEA or securities account and knowledge ≥ 4/5 only"), [num("niveau")]))

    pf: dict[str, float] = {}
    lignes: dict[str, dict] = {}
    resume_sat = [T(L, "SCPI", "SCPI")] if alloc["scpi"] > 0 and env == "assurance-vie" and r.get("horizon") == ">8" else []
    if alloc["actif"] > 0:
        resume_sat.append(T(L, "fonds actif", "active fund"))
    resume_rep = []

    def placer(sc: str, montant: float, poche_txt: str, cap: float = MAX_LIGNE, extra: list | None = None,
               max_lignes: int | None = None) -> float:
        """Place `montant` sur les ETF classés de la poche ; au-delà du plafond, sur le suivant. Renvoie le reste."""
        cands = classer_etf(sc, durable, env, L)
        ordre = [c for c in cands if c["ok_version"]] + [c for c in cands if not c["ok_version"]]
        ordre = ordre[:max_lignes] if max_lignes else ordre
        reste = montant
        for k, c in enumerate(ordre):
            if reste <= 1e-9:
                break
            if env != "assurance-vie" and c["isin"] == "FONDS-EUROS":
                continue
            place = min(reste, cap - pf.get(c["isin"], 0.0))
            if place <= 1e-9:
                continue
            pf[c["isin"]] = pf.get(c["isin"], 0.0) + place
            reste -= place
            motif = c["motif"] if k == 0 else T(L, "complément : plafond de 30 % par ligne atteint sur le premier choix",
                                                 "top-up: 30% line cap reached on the first choice")
            info = lignes.setdefault(c["isin"], {"poche": sc, "raison": motif, "alternatives": cands, "texte_poche": poche_txt})
            if extra:
                info.setdefault("notes", []).extend(extra)
        return reste

    # Actions
    det_rep = []
    A = alloc["actions"]
    if A > 0:
        sat = selection_satellite(sat_n, env, excl, filtre_esg, L) if sat_ok else []
        S = min(sat_part, A) if sat else 0.0
        for c in sat:
            pf[c["isin"]] = S / len(sat)
            lignes[c["isin"]] = {"poche": "satellite", "raison": c["motif"], "alternatives": [], "texte_poche": NOMS_POCHES["satellite"][L == "en"]}
        if sat:
            resume_sat.append(T(L, f"{len(sat)} actions en direct ({_pc(S, L)})", f"{len(sat)} direct stocks ({_pc(S, L)})"))
            det_sat.append((T(L, f"Actions en direct : {_pc(S, L)} sur {len(sat)} titres européens, un par secteur, chacun le moins volatil de son secteur sur 3 ans",
                              f"Direct stocks: {_pc(S, L)} on {len(sat)} European stocks, one per sector, least volatile of its sector"),
                            [num("niveau"), num("anciennete")]))
        coeur = A - S
        em = min(PART_EMERGENTS.get(p, 0.0) * coeur, MAX_EMERGENTS)
        theme = min(PART_THEMATIQUE * coeur, MAX_THEMATIQUE) if durable and p >= 4 else 0.0
        dev = coeur - em - theme
        zone = r.get("zone") or "Monde"
        mix = ZONES.get(zone, ZONES["Monde"])
        resume_rep.append(T(L, f"actions zone {zone}", f"equities: {zone}"))
        if em:
            resume_rep.append(T(L, f"émergents {_pc(em, L, 1)}", f"EM {_pc(em, L, 1)}"))
        if theme:
            resume_rep.append(T(L, f"thème vert {_pc(theme, L, 1)}", f"green theme {_pc(theme, L, 1)}"))
        det_rep.append((T(L, f"Actions cœur {_pc(coeur, L)} : zone « {zone} » → " + ", ".join(f"{NOMS_POCHES[k][0].lower()} {int(v * 100)} %" for k, v in mix.items()),
                          f"Core equities {_pc(coeur, L)}: region '{zone}' → " + ", ".join(f"{NOMS_POCHES[k][1].lower()} {int(v * 100)}%" for k, v in mix.items())),
                        [num("zone")]))
        if em:
            det_rep.append((T(L, f"Émergents {_pc(em, L, 1)} ({int(PART_EMERGENTS[p] * 100)} % de la poche, profils 4-5 seulement ; plafond 15 %)",
                              f"Emerging {_pc(em, L, 1)} (profiles 4-5 only; cap 15%)"), []))
        if theme:
            det_rep.append((T(L, f"Thématique verte {_pc(theme, L, 1)} (préférence durable, profils 4-5 ; plafond 10 %)",
                              f"Green theme {_pc(theme, L, 1)} (sustainable preference, profiles 4-5; cap 10%)"), [num("durabilite")]))
        reste_monde = 0.0
        for sc, part in mix.items():
            if sc == "monde":
                # un seul ETF monde par portefeuille : au-delà de 30 %, on reproduit ses poids régionaux
                reste_monde = placer("monde", part * dev, NOMS_POCHES["monde"][L == "en"], max_lignes=1)
            else:
                placer(sc, part * dev, NOMS_POCHES[sc][L == "en"])
        if reste_monde > 1e-9:
            det_rep.append((T(L, f"ETF monde plafonné à 30 % : les {_pc(reste_monde, L, 1)} restants reproduisent ses poids régionaux (États-Unis 70 %, Europe 30 %)",
                              f"World ETF capped at 30%: remaining {_pc(reste_monde, L, 1)} follow its regional weights (US 70%, Europe 30%)"), []))
            for sc, part in DEBORDEMENT_MONDE.items():
                placer(sc, part * reste_monde, NOMS_POCHES[sc][L == "en"])
        if em:
            placer("emergents", em, NOMS_POCHES["emergents"][L == "en"])
        if theme:
            placer("thematique", theme, NOMS_POCHES["thematique"][L == "en"], cap=0.05)

    # Obligations
    O = alloc["obligations"]
    if O > 0:
        rep = dict(OBLIGATIONS[p])
        court = r.get("horizon") in ("<2", "2-5") or r.get("objectif") == "immobilier"
        if court:
            rep["etat_court"] += rep.pop("etat")
        resume_rep.append(T(L, "obligations courtes" if court else ("obligations sans haut rendement" if not rep["haut_rendement"] else
                                                                   "obligations diversifiées"),
                            "short bonds" if court else ("bonds without high yield" if not rep["haut_rendement"] else "diversified bonds")))
        det_rep.append((T(L, f"Obligations {_pc(O, L)} : " + ", ".join(f"{NOMS_POCHES[k][0].lower()} {int(v * 100)} %" for k, v in rep.items() if v)
                          + (" (horizon court ou projet immobilier : obligations d'État courtes, moins sensibles aux taux)" if court else ""),
                          f"Bonds {_pc(O, L)}: " + ", ".join(f"{NOMS_POCHES[k][1].lower()} {int(v * 100)}%" for k, v in rep.items() if v)
                          + (" (short horizon: short-dated govies)" if court else "")),
                        [num("horizon"), num("objectif")] if court else []))
        reste = 0.0
        for sc, part in rep.items():
            if part > 0:
                reste += placer(sc, part * O, NOMS_POCHES[sc][L == "en"])
        if reste > 1e-9:
            reste = placer("etat", reste, NOMS_POCHES["etat"][L == "en"])

    # Monétaire
    M = alloc["monetaire"]
    if M > 0:
        if env == "assurance-vie":
            fe = min(M, MAX_FONDS_EUROS)
            pf["FONDS-EUROS"] = fe
            lignes["FONDS-EUROS"] = {"poche": "fonds_euros", "alternatives": [], "texte_poche": NOMS_POCHES["fonds_euros"][L == "en"],
                                     "raison": T(L, "capital garanti par l'assureur, réservé à l'assurance-vie ; 30 % maximum",
                                                 "capital guaranteed, life insurance only; 30% max")}
            M -= fe
        if M > 1e-9:
            reste = placer("monetaire", M, NOMS_POCHES["monetaire"][L == "en"])
            if reste > 1e-9:
                placer("etat_court", reste, NOMS_POCHES["etat_court"][L == "en"])

    # Diversifiants, SCPI, fonds actif
    for sc, part in DIVERSIFIANTS.items():
        if alloc["diversifiants"] > 0:
            placer(sc, part * alloc["diversifiants"], NOMS_POCHES[sc][L == "en"])
    if alloc["scpi"] > 0:
        pf["SCPI-IMMORENTE"] = alloc["scpi"]
        lignes["SCPI-IMMORENTE"] = {"poche": "scpi", "alternatives": [], "texte_poche": "SCPI",
                                    "raison": T(L, "immobilier non coté : revenus réguliers, faible corrélation aux marchés ; frais d'entrée amortis sur 10 ans",
                                                "unlisted real estate: regular income; entry fees amortised over 10 years")}
    if alloc["actif"] > 0:
        placer("patrimonial" if p <= 3 else "actions_actif", alloc["actif"],
               NOMS_POCHES["patrimonial" if p <= 3 else "actions_actif"][L == "en"])

    pf = {i: w for i, w in pf.items() if w > 1e-6}
    total = sum(pf.values())
    pf = {i: w / total for i, w in pf.items()}
    for isin in sorted(pf, key=pf.get):
        if pf[isin] < MIN_LIGNE and lignes[isin]["poche"] != "satellite":
            meme = [i for i in pf if i != isin and donnees.classe(i) == donnees.classe(isin) and lignes[i]["poche"] != "satellite"
                    and pf[i] + pf[isin] <= MAX_LIGNE + 1e-9]
            if meme:
                cible = max(meme, key=pf.get)
                pf[cible] += pf.pop(isin)
                det_rep.append((T(L, f"{donnees.nom(isin)} (moins de 1 %) regroupée avec {donnees.nom(cible)} pour limiter les frais de transaction",
                                  f"{donnees.nom(isin)} (under 1%) merged into {donnees.nom(cible)} to limit transaction costs"), []))

    etape(T(L, "Allocation", "Allocation"), ", ".join(f"{noms_cl[c]} {_pc(w, L)}" for c, w in poids_par_classe(pf).items() if w > 1e-6),
          T(L, "La part de chaque classe découle de la grille du profil.", "Each class weight comes from the profile grid."),
          det, SOURCE_GRILLE)
    etape(T(L, "Enveloppe", "Wrapper"), {"assurance-vie": T(L, "Assurance-vie", "Life insurance"), "PEA": T(L, "PEA + compte-titres", "PEA + securities account"),
                                         "CTO": T(L, "Compte-titres", "Securities account")}[env],
          T(L, "Retraite ou transmission → assurance-vie ; horizon > 5 ans et profil ≥ 4 → PEA ; sinon assurance-vie ; le souhait du client prime.",
            "Retirement/estate → life insurance; horizon > 5y and profile ≥ 4 → PEA; else life insurance; client's wish prevails."),
          det_env, T(L, "Fiscalité 2026 ; code monétaire et financier (PEA)", "2026 tax rules"))
    etape(T(L, "Satellite et règles d'enveloppe", "Satellite and wrapper rules"),
          " · ".join(resume_sat) or T(L, "aucun satellite", "no satellite"),
          T(L, "SCPI : assurance-vie et horizon > 8 ans ; fonds actif 5 % ; actions en direct : profils 4-5, PEA ou compte-titres, connaissances ≥ 4.",
            "SCPI: life insurance and 8+ years; active fund 5%; direct stocks: profiles 4-5, PEA/securities, knowledge ≥ 4."),
          det_sat or [(T(L, "Aucune ligne satellite pour ce profil", "No satellite for this profile"), [])])
    etape(T(L, "Répartition dans chaque poche", "Split within each sleeve"), " · ".join(resume_rep),
          T(L, "Actions : pondérations de marché ajustées par la zone préférée ; obligations : plus courtes et plus sûres pour les profils prudents.",
            "Equities: market weights adjusted by region; bonds: shorter and safer for prudent profiles."), det_rep)
    det_sel = [(f"{donnees.nom(i)} ({_pc(w, L, 1)}) — {lignes[i]['raison']}", []) for i, w in sorted(pf.items(), key=lambda x: -x[1])]
    n_titres = sum(1 for i in pf if donnees.est_titre(i))
    etape(T(L, "Choix des supports", "Product selection"),
          T(L, f"{len(pf)} lignes : {len(pf) - n_titres} fonds" + (f", {n_titres} actions" if n_titres else ""),
            f"{len(pf)} holdings: {len(pf) - n_titres} funds" + (f", {n_titres} stocks" if n_titres else "")),
          T(L, "Filtres (enveloppe, durabilité, exclusions) puis classement : encours > 500 M€, réplication physique, 5 ans d'historique, frais les plus bas.",
            "Filters (wrapper, sustainability, exclusions) then ranking: AuM > €500m, physical replication, 5-year history, lowest fees."),
          det_sel, T(L, "Cahier des charges, section 5.3 ; données justETF et DIC", "Specification 5.3; justETF and KIDs"))

    # --- Contrôle du risque attendu
    vol, mu = calcul_analyses.point(pf)
    sri = calcul_analyses.classe_sri(vol)
    vmin, vmax = PROFILS[p]["vol"]
    dans = vol <= vmax + 1e-9
    etape(T(L, "Contrôle du risque", "Risk check"),
          T(L, f"Volatilité attendue {_pc(vol, L, 1)} (fourchette {_pc(vmin, L)}–{_pc(vmax, L)}) · SRI estimé {sri}/7 (max. {PROFILS[p]['sri_max']})",
            f"Expected volatility {_pc(vol, L, 1)} (range {_pc(vmin, L)}–{_pc(vmax, L)}) · estimated SRI {sri}/7 (max {PROFILS[p]['sri_max']})"),
          T(L, "La volatilité attendue doit rester sous le maximum du profil ; le SRI du portefeuille sous son SRI maximum.",
            "Expected volatility must stay below the profile maximum; portfolio SRI below its maximum."),
          [(T(L, "Conforme" if dans and sri <= PROFILS[p]["sri_max"] else "Hors limites : la recommandation est bloquée",
              "Within limits" if dans and sri <= PROFILS[p]["sri_max"] else "Out of limits: recommendation blocked"), [])],
          calcul_analyses.SOURCE_HYPOTHESES)

    return {"portefeuille": pf, "classes": poids_par_classe(pf), "allocation": alloc, "lignes": lignes, "enveloppe": env,
            "enveloppe_auto": env_auto, "profil": p, "profil_calcule": p_calc, "fil": fil, "vol": vol, "mu": mu, "sri": sri,
            "dans_les_limites": dans and sri <= PROFILS[p]["sri_max"], "satellite": sat_ok, "durable": durable}


def verifier_ajustement(reponses, profil_calcule, profil, ajustements, meta=None) -> tuple[bool, str, dict | None]:
    """Teste un ajustement du conseiller : refusé s'il sort des ±10 points ou du risque maximum du profil."""
    try:
        reco = recommander(reponses, profil_calcule, profil, ajustements, meta)
    except AjustementRefuse as e:
        return False, str(e), None
    if not reco["dans_les_limites"]:
        return False, f"volatilité attendue {reco['vol'] * 100:.1f} % au-delà du maximum du profil ({PROFILS[reco['profil']]['vol'][1] * 100:.0f} %)", reco
    return True, "", reco


def poids_par_classe(pf: dict) -> dict:
    res = {c: 0.0 for c in CLASSES}
    for isin, w in pf.items():
        res[donnees.classe(isin)] += w
    return res


def preferences_durables(reponses: dict) -> tuple[list[str], bool]:
    """(secteurs exclus, filtre ESG) : les préférences article 8 ou 9 imposent le filtre des secteurs sensibles."""
    excl = [e for e in (reponses.get("exclusions") or []) if e in ("armement", "tabac", "fossiles", "alcool", "aerien", "nucleaire")]
    return excl, str(reponses.get("durabilite")) in ("article 8", "article 9")


def alerte_reequilibrage(cible: dict, actuel: dict, seuil: float = 0.05) -> list[tuple[str, float, float]]:
    """Classes dont le poids actuel s'écarte de la cible de plus de `seuil` (contrat 4.3 du cahier des charges)."""
    c, a = poids_par_classe(cible), poids_par_classe(actuel)
    return [(k, c[k], a[k]) for k in CLASSES if abs(a[k] - c[k]) > seuil]
