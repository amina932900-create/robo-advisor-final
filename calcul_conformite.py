"""
calcul_conformite.py — Contrôles d'adéquation (MiFID II) et dossiers clients du conseiller.

Statuts d'un contrôle : « ok » ; « attention » (à documenter dans le dossier) ; « bloquant » (la déclaration
d'adéquation ne peut pas être émise). Toute dérogation du conseiller (profil abaissé, ajustement, autre enveloppe)
exige un motif écrit : sans motif, le contrôle est bloquant.

Dossiers : un fichier JSON par client dans data/dossiers/, identifié par une référence pseudonyme (RA-2026-001),
sans nom ni coordonnées (minimisation des données). Le serveur gratuit efface le disque à chaque redémarrage :
les dossiers de démonstration sont recréés automatiquement, et chaque dossier s'exporte et se réimporte en JSON.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import calcul_analyses
import calcul_profil
import calcul_portefeuille as cpf
import donnees
from calcul_profil import T
from textes import date_txt, pct_txt

ORDRE = {"ok": 0, "attention": 1, "bloquant": 2}
DOSSIER = Path(__file__).resolve().parent / "data" / "dossiers"
STATUTS = ["brouillon", "à signer", "signé", "archivé"]
STATUTS_EN = {"brouillon": "draft", "à signer": "to sign", "signé": "signed", "archivé": "archived"}


def _c(code, titre, statut, detail, regle):
    return {"code": code, "titre": titre, "statut": statut, "detail": detail, "regle": regle}


def controler(reponses: dict, profil: dict, reco: dict, decisions: dict, date_signature: str | None,
              langue: str = "fr") -> list[dict]:
    L, r, d = langue, reponses, decisions or {}
    P = lambda x, k=0: pct_txt(x, k, L)
    pf, classes = reco["portefeuille"], reco["classes"]
    u = donnees.univers()
    res = []

    # 1. Questionnaire signé et complet
    manq = calcul_profil.manquantes(r)
    if not date_signature or manq or not r.get("montant"):
        res.append(_c("QUESTIONNAIRE", T(L, "Questionnaire incomplet ou non signé", "Questionnaire incomplete or unsigned"), "bloquant",
                      T(L, f"{len(manq)} réponse(s) manquante(s)" + ("" if date_signature else ", date de signature absente"),
                        f"{len(manq)} missing answer(s)" + ("" if date_signature else ", no signature date")),
                      "MiFID II art. 25(2)"))
    else:
        res.append(_c("QUESTIONNAIRE", T(L, "Questionnaire signé et complet", "Questionnaire signed and complete"), "ok",
                      T(L, f"Signé le {date_txt(date_signature, L)}", f"Signed on {date_txt(date_signature, L)}"), "MiFID II art. 25(2)"))

    # 2. Profil retenu
    if reco["profil"] < reco["profil_calcule"]:
        motif = (d.get("motif_profil") or "").strip()
        res.append(_c("PROFIL", T(L, "Profil abaissé par le conseiller", "Profile lowered by the adviser"), "attention" if motif else "bloquant",
                      T(L, f"Calculé {reco['profil_calcule']}/5, retenu {reco['profil']}/5. " + (f"Motif : {motif}" if motif else "Motif obligatoire."),
                        f"Computed {reco['profil_calcule']}/5, chosen {reco['profil']}/5. " + (f"Reason: {motif}" if motif else "Reason required.")),
                      T(L, "Traçabilité des dérogations", "Override traceability")))
    else:
        res.append(_c("PROFIL", T(L, "Profil conforme au calcul", "Profile as computed"), "ok",
                      T(L, f"Profil {reco['profil']}/5, la plus petite des 4 notes.", f"Profile {reco['profil']}/5, lowest of the 4 scores."),
                      "MiFID II art. 25(2)"))

    # 3. Dérogations : ajustements et enveloppe
    ajust = {k: v for k, v in (d.get("ajustements") or {}).items() if abs(v) > 1e-9}
    if ajust:
        motif = (d.get("motif_ajustement") or "").strip()
        res.append(_c("AJUSTEMENT", T(L, "Allocation ajustée par le conseiller", "Allocation adjusted by the adviser"), "attention" if motif else "bloquant",
                      ", ".join(f"{k} {v * 100:+.0f} pts" for k, v in ajust.items()) + (f" — {motif}" if motif else T(L, " — motif obligatoire", " — reason required")),
                      T(L, "Traçabilité des dérogations", "Override traceability")))
    if reco["enveloppe"] != reco["enveloppe_auto"]:
        motif = (d.get("motif_enveloppe") or "").strip()
        res.append(_c("ENVELOPPE_CHOIX", T(L, "Enveloppe choisie par le conseiller", "Wrapper chosen by the adviser"), "attention" if motif else "bloquant",
                      f"{reco['enveloppe_auto']} → {reco['enveloppe']}" + (f" — {motif}" if motif else T(L, " — motif obligatoire", " — reason required")),
                      T(L, "Traçabilité des dérogations", "Override traceability")))

    # 4. Capacité financière
    m, pat = r.get("montant") or 0, r.get("patrimoine") or 0
    if pat and m > pat:
        res.append(_c("CAPACITE", T(L, "Montant supérieur au patrimoine", "Amount above wealth"), "bloquant",
                      T(L, "Vérifier la saisie du questionnaire.", "Check the questionnaire."), T(L, "Connaissance client", "KYC")))
    elif pat and m > 0.5 * pat:
        res.append(_c("CAPACITE", T(L, "Concentration du patrimoine", "Wealth concentration"), "attention",
                      T(L, f"{P(m / pat)} du patrimoine sur cette seule recommandation.", f"{P(m / pat)} of wealth in this recommendation."),
                      T(L, "Capacité à subir des pertes", "Capacity to bear losses")))
    else:
        res.append(_c("CAPACITE", T(L, "Capacité financière", "Financial capacity"), "ok",
                      T(L, "Montant cohérent avec le patrimoine.", "Amount consistent with wealth."), T(L, "Capacité à subir des pertes", "Capacity to bear losses")))

    # 5. Cohérence des réponses (alertes du profil)
    al = profil.get("alertes") or []
    res.append(_c("COHERENCE", T(L, "Cohérence des réponses", "Consistency of answers"), "attention" if al else "ok",
                  " ".join(al) if al else T(L, "Aucune incohérence relevée.", "No inconsistency found."),
                  T(L, "Connaissance client, information du client", "KYC, client information")))

    # 6. Liquidité
    liquide = classes.get("monetaire", 0)
    if r.get("besoin_liquidite") and liquide < 0.05:
        res.append(_c("LIQUIDITE", T(L, "Besoin de liquidité et faible réserve", "Liquidity need, small reserve"), "attention",
                      T(L, f"Monétaire et fonds en euros : {P(liquide)}.", f"Money market and euro fund: {P(liquide)}."),
                      T(L, "Adéquation à l'horizon", "Suitability to horizon")))
    if classes.get("scpi", 0) > 0 and r.get("horizon") != ">8":
        res.append(_c("LIQUIDITE", T(L, "SCPI avec un horizon court", "SCPI with a short horizon"), "bloquant",
                      T(L, "La SCPI exige un horizon de plus de 8 ans.", "SCPI requires 8+ years."), T(L, "Règle de construction", "Construction rule")))

    # 7. Connaissances
    hy = sum(w for i, w in pf.items() if u.loc[i, "sous_classe"] == "haut_rendement")
    titres = sum(w for i, w in pf.items() if u.loc[i, "type"] == "action")
    if (hy > 0 or titres > 0) and profil["notes"]["connaissances"] <= 3:
        res.append(_c("CONNAISSANCES", T(L, "Produits plus complexes et connaissances limitées", "Complex products, limited knowledge"), "attention",
                      T(L, f"Haut rendement {P(hy, 1)}, actions en direct {P(titres, 1)} : renforcer l'information remise.",
                        f"High yield {P(hy, 1)}, direct stocks {P(titres, 1)}: strengthen information."),
                      T(L, "MiFID II — connaissances et expérience", "MiFID II — knowledge and experience")))
    else:
        res.append(_c("CONNAISSANCES", T(L, "Connaissances et expérience", "Knowledge and experience"), "ok",
                      T(L, "Produits compatibles avec le niveau du client.", "Products consistent with the client's level."),
                      T(L, "MiFID II — connaissances et expérience", "MiFID II — knowledge and experience")))

    # 8. Diversification et plafonds
    em = sum(w for i, w in pf.items() if u.loc[i, "sous_classe"] == "emergents")
    th = sum(w for i, w in pf.items() if u.loc[i, "sous_classe"] == "thematique")
    depass = []
    if max(pf.values()) > cpf.MAX_LIGNE + 1e-6:
        depass.append(T(L, "une ligne au-delà de 30 %", "a holding above 30%"))
    if hy > cpf.MAX_HAUT_RENDEMENT + 1e-6:
        depass.append(T(L, f"haut rendement {P(hy)}", f"high yield {P(hy)}"))
    if em > cpf.MAX_EMERGENTS + 1e-6:
        depass.append(T(L, f"émergents {P(em)}", f"emerging {P(em)}"))
    if th > cpf.MAX_THEMATIQUE + 1e-6:
        depass.append(T(L, f"thématique {P(th)}", f"thematic {P(th)}"))
    res.append(_c("DIVERSIFICATION", "Diversification", "bloquant" if depass else "ok",
                  ", ".join(depass) if depass else T(L, f"{len(pf)} lignes ; plafonds respectés (30 % par ligne, haut rendement 10 %, émergents 15 %, thématique 10 %).",
                                                     f"{len(pf)} holdings; caps respected."),
                  T(L, "Règles de diversification", "Diversification rules")))

    # 9. Risque attendu
    vmin, vmax = cpf.PROFILS[reco["profil"]]["vol"]
    sri_max = cpf.PROFILS[reco["profil"]]["sri_max"]
    ok = reco["vol"] <= vmax + 1e-9 and reco["sri"] <= sri_max
    res.append(_c("RISQUE", T(L, "Risque attendu dans les limites du profil", "Expected risk within profile limits") if ok
                  else T(L, "Risque attendu au-delà du profil", "Expected risk above profile"), "ok" if ok else "bloquant",
                  T(L, f"Volatilité attendue {P(reco['vol'], 1)} (max. {P(vmax)}), SRI estimé {reco['sri']} (max. {sri_max}).",
                    f"Expected volatility {P(reco['vol'], 1)} (max {P(vmax)}), estimated SRI {reco['sri']} (max {sri_max})."),
                  T(L, "Grille des profils ; seuils PRIIPs", "Profile grid; PRIIPs thresholds")))

    # 10. Enveloppe
    if reco["enveloppe"] == "PEA" and reco["profil"] <= 2:
        res.append(_c("ENVELOPPE", T(L, "PEA peu adapté à un profil prudent", "PEA ill-suited to a prudent profile"), "attention",
                      T(L, "Le PEA ne reçoit ni fonds en euros ni obligations : l'essentiel sera en compte-titres.",
                        "No euro fund or bonds in a PEA: most will sit in a securities account."), T(L, "Choix de l'enveloppe", "Wrapper choice")))
    pea_part = sum(w for i, w in pf.items() if u.loc[i, "pea"] == "oui")
    if reco["enveloppe"] == "PEA" and pea_part * m > cpf.PLAFOND_PEA:
        res.append(_c("PLAFOND_PEA", T(L, "Plafond du PEA", "PEA ceiling"), "attention",
                      T(L, "Versements limités à 150 000 € : le surplus éligible va en compte-titres.", "Contributions capped at €150,000."),
                      T(L, "Code monétaire et financier, art. L221-30", "Monetary and Financial Code, art. L221-30")))

    # 11. Durabilité
    excl, esg = cpf.preferences_durables(r)
    touches = [i for i in pf if set(excl) & set(str(u.loc[i, "tags"]).split(";"))]
    if r.get("durabilite") not in (None, "aucune"):
        res.append(_c("DURABILITE", T(L, "Préférences de durabilité", "Sustainability preferences"), "bloquant" if touches else "ok",
                      T(L, f"{len(touches)} ligne(s) dans un secteur exclu." if touches else
                        f"Versions ISR retenues ({P(reco_isr(pf))} du portefeuille), exclusions appliquées aux actions en direct.",
                        f"{len(touches)} holding(s) in an excluded sector." if touches else "SRI versions selected, exclusions applied."),
                      T(L, "MiFID II — préférences de durabilité (règlement délégué 2021/1253)", "MiFID II — sustainability preferences")))

    # 12. Retraits
    if r.get("objectif") == "revenus" and m and (r.get("retrait_mensuel") or 0) * 12 > 0.04 * m:
        res.append(_c("RETRAITS", T(L, "Retraits élevés", "High withdrawals"), "attention",
                      T(L, f"Retraits de {P((r.get('retrait_mensuel') or 0) * 12 / m, 1)} du capital par an : voir le risque d'épuisement dans la projection.",
                        "Withdrawals above 4% a year: see depletion risk in the projection."), T(L, "Information du client", "Client information")))
    return res


def reco_isr(pf: dict) -> float:
    u = donnees.univers()
    return sum(w for i, w in pf.items() if u.loc[i, "version"] == "durable")


def synthese(controles: list[dict]) -> str:
    return max((c["statut"] for c in controles), key=ORDRE.get, default="ok")


# ====================================================================================================
# Dossiers
# ====================================================================================================
def _maintenant() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _chemin(ref: str) -> Path:
    if not ref.replace("-", "").isalnum():
        raise ValueError("Référence invalide")
    return DOSSIER / f"{ref}.json"


def nouvelle_reference() -> str:
    annee = date.today().year
    pris = {d["reference"] for d in lister()}
    k = 1
    while f"RA-{annee}-{k:03d}" in pris:
        k += 1
    return f"RA-{annee}-{k:03d}"


def nouveau_dossier() -> dict:
    return {"reference": nouvelle_reference(), "cree_le": _maintenant(), "statut": "brouillon", "reponses": {},
            "date_signature_questionnaire": None, "decisions": {}, "recommandation": None, "historique": [],
            "journal": [{"date": _maintenant(), "auteur": "conseiller", "evenement": "Dossier créé"}]}


def enregistrer(dossier: dict, evenement: str | None = None) -> None:
    DOSSIER.mkdir(parents=True, exist_ok=True)
    dossier["maj"] = _maintenant()
    if evenement:
        dossier.setdefault("journal", []).append({"date": _maintenant(), "auteur": "conseiller", "evenement": evenement})
    _chemin(dossier["reference"]).write_text(json.dumps(dossier, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def charger(ref: str) -> dict | None:
    p = _chemin(ref)
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except (OSError, json.JSONDecodeError):
        return None


def lister() -> list[dict]:
    if not DOSSIER.exists():
        return []
    res = [d for d in (charger(p.stem) for p in DOSSIER.glob("RA-*.json")) if d]
    return sorted(res, key=lambda d: d.get("maj", ""), reverse=True)


def supprimer(ref: str) -> None:
    p = _chemin(ref)
    if p.exists():
        p.unlink()


def revue_due(d: dict, aujourdhui: date | None = None) -> bool:
    """Revue annuelle à faire : déclaration signée il y a plus de 11 mois."""
    s = (d.get("recommandation") or {}).get("date_signature")
    if d.get("statut") != "signé" or not s:
        return False
    return date.fromisoformat(s[:10]) <= (aujourdhui or date.today()) - timedelta(days=335)


def figer_recommandation(dossier: dict, reco: dict, ctrl: list[dict]) -> None:
    """Fige la recommandation émise (ce qui sera signé) ; l'ancienne passe dans l'historique."""
    if dossier.get("recommandation") and dossier["recommandation"].get("date_signature"):
        dossier.setdefault("historique", []).append(dossier["recommandation"])
    dossier["recommandation"] = {"date": date.today().isoformat(), "portefeuille": reco["portefeuille"], "profil": reco["profil"],
                                 "profil_calcule": reco["profil_calcule"], "enveloppe": reco["enveloppe"], "classes": reco["classes"],
                                 "vol": reco["vol"], "sri": reco["sri"], "synthese": synthese(ctrl), "date_signature": None}
    dossier["statut"] = "à signer"


# ====================================================================================================
# Clients de démonstration (fictifs) : un par profil, des statuts variés, des revues annuelles à faire
# ====================================================================================================
_BASE = {"situation_familiale": "couple", "epargne_precaution": True, "credits": False, "statut_pro": "salarie_cdi",
         "stabilite_revenus": "stables", "besoin_liquidite": False, "versement_mensuel": 0, "cible": 0,
         "quiz_etf": True, "quiz_taux": False, "quiz_diversification": True, "quiz_perte": True, "quiz_fonds_euros": True,
         "durabilite": "aucune", "zone": "Monde", "enveloppe_souhaitee": "auto", "produits_detenus": ["assurance_vie", "livrets"]}
DEMO = [
    {"reference": "RA-2025-014", "statut": "signé", "signe": "2025-11-12",
     "note": "Retraitée, prépare la transmission à ses enfants.",
     "reponses": {**_BASE, "montant": 400_000, "age": 71, "revenus": "50-100k", "patrimoine": 1_400_000, "statut_pro": "retraite",
                  "objectif": "transmission", "horizon": ">8", "priorite": "prudent", "rendement_attendu": "2-3",
                  "quiz_taux": True, "anciennete": ">5", "niveau": "intermediaire", "reaction_baisse": "vendre_partie",
                  "perte_max": "5", "choix_portefeuille": "A"}},
    {"reference": "RA-2026-003", "statut": "signé", "signe": "2026-02-10",
     "note": "Cadre, prépare sa retraite avec des versements mensuels.",
     "reponses": {**_BASE, "montant": 250_000, "age": 46, "situation_familiale": "couple_enfants", "revenus": "100-200k",
                  "patrimoine": 850_000, "objectif": "retraite", "horizon": ">8", "priorite": "equilibre", "rendement_attendu": "4-5",
                  "versement_mensuel": 1_500, "cible": 600_000, "anciennete": "2-5", "niveau": "intermediaire",
                  "produits_detenus": ["assurance_vie", "etf"], "reaction_baisse": "attendre", "perte_max": "10",
                  "choix_portefeuille": "C", "quiz_fonds_euros": False}},
    {"reference": "RA-2025-021", "statut": "signé", "signe": "2025-11-03",
     "note": "Chef d'entreprise, horizon long, sensible à l'ESG.",
     "reponses": {**_BASE, "montant": 600_000, "age": 39, "revenus": ">200k", "patrimoine": 2_500_000, "statut_pro": "independant",
                  "stabilite_revenus": "variables", "objectif": "valorisation", "horizon": ">8", "priorite": "performance",
                  "rendement_attendu": "6-8", "anciennete": ">5", "niveau": "confirme", "produits_detenus": ["actions", "etf", "scpi"],
                  "reaction_baisse": "rien", "perte_max": "20", "choix_portefeuille": "C", "durabilite": "article 8",
                  "exclusions": ["armement", "tabac"], "zone": "Europe"}},
    {"reference": "RA-2024-031", "statut": "signé", "signe": "2024-06-14",
     "note": "Profession libérale ; revue 2025 reportée par le client.",
     "reponses": {**_BASE, "montant": 320_000, "age": 55, "revenus": ">200k", "patrimoine": 1_900_000, "statut_pro": "independant",
                  "objectif": "valorisation", "horizon": "5-8", "priorite": "performance", "rendement_attendu": "6-8", "anciennete": ">5",
                  "niveau": "confirme", "produits_detenus": ["actions", "etf", "assurance_vie"], "reaction_baisse": "rien", "perte_max": "20",
                  "choix_portefeuille": "C", "zone": "Monde", "enveloppe_souhaitee": "assurance-vie"}},
    {"reference": "RA-2026-011", "statut": "à signer", "signe": None,
     "note": "Jeune médecin, horizon très long, exclusions sectorielles.",
     "reponses": {**_BASE, "montant": 150_000, "age": 33, "situation_familiale": "celibataire", "revenus": "100-200k",
                  "patrimoine": 450_000, "statut_pro": "independant", "objectif": "valorisation", "horizon": ">8", "priorite": "max",
                  "rendement_attendu": ">8", "anciennete": ">5", "niveau": "confirme", "produits_detenus": ["actions", "etf", "obligations"],
                  "reaction_baisse": "renforcer", "perte_max": "30", "choix_portefeuille": "D", "durabilite": "exclusions",
                  "exclusions": ["tabac", "fossiles"], "enveloppe_souhaitee": "CTO"}},
    {"reference": "RA-2026-014", "statut": "brouillon", "signe": None,
     "note": "Projet d'achat immobilier dans 3 ans.",
     "reponses": {**_BASE, "montant": 180_000, "age": 52, "revenus": "50-100k", "patrimoine": 520_000, "credits": True,
                  "taux_effort": "20-35", "objectif": "immobilier", "horizon": "2-5", "priorite": "prudent", "rendement_attendu": "4-5",
                  "anciennete": "<2", "niveau": "debutant", "reaction_baisse": "attendre", "perte_max": "10", "choix_portefeuille": "B",
                  "besoin_liquidite": True}},
]


def creer_demo(force: bool = False) -> None:
    """Crée les dossiers de démonstration s'il n'y a aucun dossier (ou si force=True)."""
    if lister() and not force:
        return
    for c in DEMO:
        r = dict(c["reponses"])
        d = nouveau_dossier()
        d.update({"reference": c["reference"], "demo": True, "note": c["note"], "reponses": r,
                  "date_signature_questionnaire": (c["signe"] or date.today().isoformat())})
        d["cree_le"] = (c["signe"] or date.today().isoformat()) + "T10:00:00"
        if c["statut"] != "brouillon":
            prof = calcul_profil.calculer_profil(r)
            reco = cpf.recommander(r, prof, meta={"date_signature": d["date_signature_questionnaire"], "reference": d["reference"]})
            ctrl = controler(r, prof, reco, {}, d["date_signature_questionnaire"])
            figer_recommandation(d, reco, ctrl)
            if c["signe"]:
                d["recommandation"]["date"] = c["signe"]
                d["recommandation"]["date_signature"] = c["signe"]
                d["statut"] = "signé"
        d["journal"] = [{"date": d["cree_le"], "auteur": "conseiller", "evenement": "Questionnaire signé saisi"}]
        if c["signe"]:
            d["journal"].append({"date": c["signe"] + "T11:00:00", "auteur": "client", "evenement": "Déclaration d'adéquation signée"})
        enregistrer(d)
