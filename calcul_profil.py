"""
calcul_profil.py — Le questionnaire signé par le client et le calcul de son profil de risque.

Le client remplit et signe le questionnaire papier (généré par livrables.questionnaire_vierge, mêmes numéros) ;
le conseiller le saisit dans l'outil. Chaque question a un numéro fixe, cité dans le fil de décision :
« Connaissances 3 ← quiz 2/5 (Q18 : réponse Vrai, bonne réponse Faux) ».

Règle (orientations ESMA sur l'adéquation, pratique des banques) : 4 notes de 1 à 5
(tolérance, horizon, capacité à subir des pertes, connaissances) ; le profil est la plus petite.
"""

from __future__ import annotations

import math

BLOCS = {
    "A": {"fr": "Situation", "en": "Situation"},
    "B": {"fr": "Objectifs", "en": "Goals"},
    "C": {"fr": "Connaissances et expérience", "en": "Knowledge & experience"},
    "D": {"fr": "Rapport au risque", "en": "Attitude to risk"},
    "E": {"fr": "Préférences", "en": "Preferences"},
}

# Chaque question : id, bloc, type (nombre, euros, choix, oui_non, vrai_faux, multi), fr / en,
# options = (valeur, libellé FR, libellé EN, points), condition = question affichée seulement si…
QUESTIONS = [
    # ------------------------------------------------------------------ A. Situation
    {"id": "age", "bloc": "A", "type": "nombre", "min": 18, "max": 100,
     "fr": "Âge du client", "en": "Client's age"},
    {"id": "situation_familiale", "bloc": "A", "type": "choix", "fr": "Situation familiale", "en": "Family situation",
     "options": [("celibataire", "Célibataire", "Single", 0), ("couple", "En couple, marié(e) ou pacsé(e)", "Couple or married", 0),
                 ("couple_enfants", "En couple avec enfant(s)", "Couple with children", 0),
                 ("seul_enfants", "Seul(e) avec enfant(s)", "Single parent", 0)]},
    {"id": "revenus", "bloc": "A", "type": "choix", "fr": "Revenus nets annuels du foyer", "en": "Household annual net income",
     "options": [("<50k", "Moins de 50 000 €", "Under €50,000", 3), ("50-100k", "50 000 à 100 000 €", "€50,000 to €100,000", 4),
                 ("100-200k", "100 000 à 200 000 €", "€100,000 to €200,000", 5), (">200k", "Plus de 200 000 €", "Over €200,000", 5)]},
    {"id": "patrimoine", "bloc": "A", "type": "euros", "min": 0, "max": 100_000_000,
     "fr": "Patrimoine total, immobilier compris (€)", "en": "Total wealth, real estate included (€)"},
    {"id": "epargne_precaution", "bloc": "A", "type": "oui_non",
     "fr": "Épargne de précaution d'au moins 3 à 6 mois de dépenses, en dehors de ce placement",
     "en": "Emergency fund of at least 3 to 6 months of expenses, outside this investment"},
    {"id": "credits", "bloc": "A", "type": "oui_non", "fr": "Crédits en cours (immobilier, consommation)",
     "en": "Outstanding loans (mortgage, consumer)"},
    {"id": "taux_effort", "bloc": "A", "type": "choix", "condition": ("credits", True),
     "fr": "Si oui : part des revenus consacrée aux remboursements", "en": "If yes: share of income spent on repayments",
     "options": [("<20", "Moins de 20 %", "Under 20%", 5), ("20-35", "De 20 à 35 %", "20% to 35%", 4),
                 (">35", "Plus de 35 %", "Over 35%", 3)]},
    {"id": "statut_pro", "bloc": "A", "type": "choix", "fr": "Situation professionnelle", "en": "Employment status",
     "options": [("salarie_cdi", "Salarié(e) en CDI ou fonctionnaire", "Permanent employee or civil servant", 5),
                 ("independant", "Indépendant(e), chef d'entreprise, profession libérale", "Self-employed or business owner", 4),
                 ("cdd", "Salarié(e) en CDD ou intérim", "Fixed-term or temp employee", 4),
                 ("retraite", "Retraité(e)", "Retired", 4), ("sans_emploi", "Sans emploi", "Unemployed", 3)]},
    {"id": "stabilite_revenus", "bloc": "A", "type": "choix", "fr": "Revenus des prochaines années",
     "en": "Income over the coming years",
     "options": [("stables", "Stables ou en hausse", "Stable or rising", 5), ("variables", "Variables", "Variable", 4),
                 ("baisse", "Probablement en baisse", "Likely to fall", 3)]},
    # ------------------------------------------------------------------ B. Objectifs
    {"id": "objectif", "bloc": "B", "type": "choix", "fr": "Objectif principal du placement", "en": "Main goal",
     "options": [("retraite", "Préparer la retraite", "Prepare for retirement", 0),
                 ("immobilier", "Financer un projet immobilier", "Fund a property purchase", 0),
                 ("valorisation", "Faire fructifier le capital", "Grow the capital", 0),
                 ("revenus", "Obtenir des revenus complémentaires", "Generate extra income", 0),
                 ("transmission", "Transmettre un capital", "Pass on wealth", 0)]},
    {"id": "retrait_mensuel", "bloc": "B", "type": "euros", "min": 0, "max": 50_000, "condition": ("objectif", "revenus"),
     "fr": "Si revenus complémentaires : retrait mensuel souhaité (€)", "en": "If extra income: desired monthly withdrawal (€)"},
    {"id": "horizon", "bloc": "B", "type": "choix", "fr": "Horizon de placement", "en": "Investment horizon",
     "options": [("<2", "Moins de 2 ans", "Under 2 years", 1), ("2-5", "2 à 5 ans", "2 to 5 years", 3),
                 ("5-8", "5 à 8 ans", "5 to 8 years", 4), (">8", "Plus de 8 ans", "More than 8 years", 5)]},
    {"id": "priorite", "bloc": "B", "type": "choix", "fr": "Entre sécurité et performance, la priorité",
     "en": "Between safety and performance, the priority",
     "options": [("securite", "Protéger le capital avant tout", "Protect capital above all", 1),
                 ("prudent", "Plutôt la sécurité", "Mostly safety", 2), ("equilibre", "Un équilibre des deux", "A balance", 3),
                 ("performance", "Plutôt la performance", "Mostly performance", 4),
                 ("max", "La performance maximale à long terme", "Maximum long-term performance", 5)]},
    {"id": "rendement_attendu", "bloc": "B", "type": "choix", "fr": "Rendement annuel espéré", "en": "Hoped-for annual return",
     "options": [("2-3", "2 à 3 %, avec des baisses très faibles", "2-3%, very small falls", 1),
                 ("4-5", "4 à 5 %, baisses jusqu'à -10 %", "4-5%, falls up to -10%", 2),
                 ("6-8", "6 à 8 %, baisses jusqu'à -25 %", "6-8%, falls up to -25%", 4),
                 (">8", "Plus de 8 %, baisses de -40 % ou plus", "Over 8%, falls of -40% or more", 5)]},
    {"id": "versement_mensuel", "bloc": "B", "type": "euros", "min": 0, "max": 50_000,
     "fr": "Versements mensuels prévus (€, 0 si aucun)", "en": "Planned monthly contributions (€, 0 if none)"},
    {"id": "cible", "bloc": "B", "type": "euros", "min": 0, "max": 100_000_000,
     "fr": "Montant visé à l'horizon (€, 0 si aucun)", "en": "Target amount at the horizon (€, 0 if none)"},
    {"id": "besoin_liquidite", "bloc": "B", "type": "oui_non", "fr": "Besoin possible de retirer une partie avant l'horizon",
     "en": "Possible need to withdraw part before the horizon"},
    # ------------------------------------------------------------------ C. Connaissances
    {"id": "quiz_etf", "bloc": "C", "type": "vrai_faux", "bonne": True,
     "fr": "Vrai ou faux : un ETF cherche à reproduire la performance d'un indice.",
     "en": "True or false: an ETF aims to replicate an index."},
    {"id": "quiz_taux", "bloc": "C", "type": "vrai_faux", "bonne": False,
     "fr": "Vrai ou faux : quand les taux montent, le prix des obligations existantes monte aussi.",
     "en": "True or false: when rates rise, existing bond prices rise too."},
    {"id": "quiz_diversification", "bloc": "C", "type": "vrai_faux", "bonne": True,
     "fr": "Vrai ou faux : répartir son argent entre plusieurs actifs réduit le risque global.",
     "en": "True or false: spreading money across assets reduces overall risk."},
    {"id": "quiz_perte", "bloc": "C", "type": "vrai_faux", "bonne": True,
     "fr": "Vrai ou faux : un placement en actions peut perdre une partie du capital.",
     "en": "True or false: an equity investment can lose part of the capital."},
    {"id": "quiz_fonds_euros", "bloc": "C", "type": "vrai_faux", "bonne": True,
     "fr": "Vrai ou faux : en assurance-vie, le capital du fonds en euros est garanti par l'assureur.",
     "en": "True or false: in life insurance, euro fund capital is guaranteed by the insurer."},
    {"id": "anciennete", "bloc": "C", "type": "choix", "fr": "Ancienneté sur les marchés financiers",
     "en": "Experience in financial markets",
     "options": [("jamais", "Aucune", "None", 3), ("<2", "Moins de 2 ans", "Under 2 years", 3),
                 ("2-5", "2 à 5 ans", "2 to 5 years", 4), (">5", "Plus de 5 ans", "Over 5 years", 5)]},
    {"id": "niveau", "bloc": "C", "type": "choix", "fr": "Niveau de connaissance financière déclaré",
     "en": "Self-assessed financial knowledge",
     "options": [("debutant", "Débutant", "Beginner", 3), ("intermediaire", "Intermédiaire", "Intermediate", 4),
                 ("confirme", "Confirmé", "Advanced", 5)]},
    {"id": "produits_detenus", "bloc": "C", "type": "multi", "fr": "Produits déjà détenus", "en": "Products already held",
     "options": [("livrets", "Livrets", "Savings accounts", 0), ("assurance_vie", "Assurance-vie", "Life insurance", 0),
                 ("actions", "Actions", "Shares", 1), ("etf", "ETF", "ETFs", 1), ("obligations", "Obligations", "Bonds", 1),
                 ("scpi", "SCPI", "SCPI", 1)]},
    # ------------------------------------------------------------------ D. Rapport au risque
    {"id": "reaction_baisse", "bloc": "D", "type": "choix", "fr": "Le portefeuille perd 20 % en quelques mois : réaction",
     "en": "The portfolio loses 20% in a few months: reaction",
     "options": [("tout_vendre", "Tout vendre", "Sell everything", 1), ("vendre_partie", "Vendre une partie", "Sell part", 2),
                 ("attendre", "Attendre que ça remonte", "Wait for a recovery", 3), ("rien", "Ne rien changer", "Change nothing", 4),
                 ("renforcer", "Investir davantage", "Invest more", 5)]},
    {"id": "perte_max", "bloc": "D", "type": "choix", "fr": "Perte maximale acceptable sur un an",
     "en": "Maximum acceptable loss over one year",
     "options": [("0", "Aucune", "None", 1), ("5", "Jusqu'à -5 %", "Up to -5%", 2), ("10", "Jusqu'à -10 %", "Up to -10%", 3),
                 ("20", "Jusqu'à -20 %", "Up to -20%", 4), ("30", "Plus de -20 %", "More than -20%", 5)]},
    {"id": "choix_portefeuille", "bloc": "D", "type": "choix", "fr": "Portefeuille préféré sur un an (fourchettes indicatives)",
     "en": "Preferred one-year portfolio (indicative ranges)",
     "options": [("A", "A : de -2 % à +4 %", "A: -2% to +4%", 1), ("B", "B : de -8 % à +10 %", "B: -8% to +10%", 2),
                 ("C", "C : de -15 % à +18 %", "C: -15% to +18%", 4), ("D", "D : de -25 % à +30 %", "D: -25% to +30%", 5)]},
    # ------------------------------------------------------------------ E. Préférences
    {"id": "durabilite", "bloc": "E", "type": "choix", "fr": "Préférence de durabilité (MiFID II)",
     "en": "Sustainability preference (MiFID II)",
     "options": [("aucune", "Aucune", "None", 0), ("exclusions", "Exclure certains secteurs", "Exclude some sectors", 0),
                 ("article 8", "Fonds promouvant des critères ESG (article 8)", "ESG-promoting funds (Article 8)", 0),
                 ("article 9", "Fonds à objectif durable (article 9)", "Sustainable-objective funds (Article 9)", 0)]},
    {"id": "exclusions", "bloc": "E", "type": "multi", "condition": ("durabilite", "!aucune"),
     "fr": "Si oui : secteurs à exclure", "en": "If so: sectors to exclude",
     "options": [("armement", "Armement", "Weapons", 0), ("tabac", "Tabac", "Tobacco", 0),
                 ("fossiles", "Énergies fossiles", "Fossil fuels", 0), ("alcool", "Alcool", "Alcohol", 0),
                 ("aerien", "Transport aérien", "Aviation", 0), ("nucleaire", "Nucléaire", "Nuclear", 0)]},
    {"id": "zone", "bloc": "E", "type": "choix", "fr": "Zone géographique à privilégier pour les actions",
     "en": "Preferred region for equities",
     "options": [("Monde", "Monde (pondérations de marché)", "World (market weights)", 0),
                 ("Europe", "Europe", "Europe", 0), ("France", "France", "France", 0)]},
    {"id": "enveloppe_souhaitee", "bloc": "E", "type": "choix", "fr": "Enveloppe souhaitée", "en": "Preferred wrapper",
     "options": [("auto", "Pas de préférence", "No preference", 0), ("assurance-vie", "Assurance-vie", "Life insurance", 0),
                 ("PEA", "PEA", "PEA", 0), ("CTO", "Compte-titres", "Securities account", 0)]},
]

for _n, _q in enumerate(QUESTIONS, start=1):
    _q["num"] = _n                         # numéro fixe, le même que sur le questionnaire papier

PAR_ID = {q["id"]: q for q in QUESTIONS}
QUIZ = [q["id"] for q in QUESTIONS if q["type"] == "vrai_faux"]
TOLERANCE = ["reaction_baisse", "perte_max", "choix_portefeuille", "priorite"]
NOTE_HORIZON = {"<2": 1, "2-5": 3, "5-8": 4, ">8": 5}
NOMS = {1: ("Prudent", "Conservative"), 2: ("Modéré", "Moderate"), 3: ("Équilibré", "Balanced"),
        4: ("Dynamique", "Growth"), 5: ("Offensif", "Aggressive")}
MONTANT_MIN, MONTANT_MAX = 100_000, 1_000_000
PRODUITS_RISQUES = ("actions", "etf", "obligations", "scpi")


def T(langue: str, fr: str, en: str) -> str:
    return en if langue == "en" else fr


def nom_profil(p: int, langue: str = "fr") -> str:
    return NOMS[p][1 if langue == "en" else 0]


def q(id_question: str) -> dict:
    return PAR_ID[id_question]


def visible(question: dict, reponses: dict) -> bool:
    """Une question conditionnelle n'est posée que si sa condition est remplie."""
    cond = question.get("condition")
    if not cond:
        return True
    cle, attendu = cond
    v = reponses.get(cle)
    if isinstance(attendu, str) and attendu.startswith("!"):
        return v not in (None, attendu[1:])
    return v == attendu


def points(id_question: str, valeur):
    """Points d'une réponse à choix ; None si absente ou inconnue."""
    for v, *_, pts in q(id_question).get("options", []):
        if v == valeur:
            return pts
    return None


def libelle(id_question: str, valeur, langue: str = "fr") -> str:
    """Libellé lisible d'une réponse (écrans, PDF, Excel)."""
    question = q(id_question)
    if valeur is None or valeur == "":
        return "—"
    if question["type"] == "oui_non":
        return {True: T(langue, "Oui", "Yes"), False: T(langue, "Non", "No")}.get(valeur, str(valeur))
    if question["type"] == "vrai_faux":
        return {True: T(langue, "Vrai", "True"), False: T(langue, "Faux", "False")}.get(valeur, str(valeur))
    if question["type"] in ("choix", "multi"):
        i = 2 if langue == "en" else 1
        table = {o[0]: o[i] for o in question["options"]}
        if isinstance(valeur, (list, tuple)):
            return ", ".join(table.get(v, str(v)) for v in valeur) or "—"
        return table.get(valeur, str(valeur))
    if question["type"] == "euros":
        return f"{valeur:,.0f} €".replace(",", " ") if langue == "fr" else f"€{valeur:,.0f}"
    return str(valeur)


def manquantes(reponses: dict) -> list[dict]:
    """Questions visibles sans réponse (toutes sont obligatoires : le questionnaire est signé)."""
    res = []
    for question in QUESTIONS:
        if not visible(question, reponses):
            continue
        v = reponses.get(question["id"])
        if question["type"] == "multi":
            continue                               # « aucun » est une réponse valable
        if v is None or v == "":
            res.append(question)
    return res


def nettoyer(reponses: dict) -> dict:
    """Retire les réponses des questions masquées (ex. taux d'effort sans crédit)."""
    return {k: v for k, v in reponses.items() if k not in PAR_ID or visible(PAR_ID[k], reponses)}


def arrondi_prudent(x: float) -> int:
    """Arrondi au plus proche, la moitié vers le bas (3,5 -> 3) : prudent sans écraser les profils élevés."""
    return max(1, min(5, math.ceil(x - 0.5)))


def score_quiz(reponses: dict) -> tuple[int, list[str]]:
    """(bonnes réponses sur 5, liste des erreurs « Q18 »)."""
    bonnes, erreurs = 0, []
    for qid in QUIZ:
        if reponses.get(qid) == q(qid)["bonne"]:
            bonnes += 1
        else:
            erreurs.append(qid)
    return bonnes, erreurs


def part_investie(reponses: dict) -> float | None:
    patrimoine = reponses.get("patrimoine") or 0
    return None if patrimoine <= 0 else (reponses.get("montant") or 0) / patrimoine


def calculer_profil(reponses: dict, langue: str = "fr") -> dict:
    """
    Renvoie {"profil", "notes", "detail", "alertes", "quiz", "nom"}.
    detail[note] = liste de (texte, [numéros de questions]) : la justification de chaque note.
    Fonctionne aussi sur un questionnaire incomplet (affichage en direct pendant la saisie).
    """
    r = reponses
    L = langue
    detail = {k: [] for k in ("tolerance", "horizon", "capacite", "connaissances")}

    # --- Tolérance : moyenne de 4 réponses, arrondi prudent
    pts = [(qid, points(qid, r.get(qid))) for qid in TOLERANCE]
    pts = [(qid, p) for qid, p in pts if p is not None]
    if pts:
        moy = sum(p for _, p in pts) / len(pts)
        tolerance = arrondi_prudent(moy)
        detail["tolerance"].append((T(L, f"Moyenne de {len(pts)} réponses : {' + '.join(str(p) for _, p in pts)} = "
                                          f"{moy:.2f}".replace(".", ",") + f" → {tolerance}",
                                          f"Average of {len(pts)} answers: {moy:.2f} → {tolerance}"),
                                    [q(qid)["num"] for qid, _ in pts]))
    else:
        tolerance = 1
        detail["tolerance"].append((T(L, "Non renseignée : hypothèse la plus prudente (1)", "Not filled: most prudent (1)"), []))

    # --- Horizon
    horizon = NOTE_HORIZON.get(r.get("horizon"), 1)
    detail["horizon"].append((T(L, f"Horizon « {libelle('horizon', r.get('horizon'), L)} » → {horizon}",
                                f"Horizon '{libelle('horizon', r.get('horizon'), L)}' → {horizon}"), [q("horizon")["num"]]))

    # --- Capacité à subir des pertes : 5, abaissée par chaque fragilité
    capacite = 5

    def plafond(valeur, fr, en, refs):
        nonlocal capacite
        capacite = min(capacite, valeur)
        detail["capacite"].append((T(L, fr, en) + f" → {valeur} max.", refs))

    part = part_investie(r)
    if r.get("epargne_precaution") is False:
        plafond(3, "Pas d'épargne de précaution", "No emergency fund", [q("epargne_precaution")["num"]])
    if part is not None and part > 0.5:
        plafond(3, f"{round(part * 100)} % du patrimoine placé ici", f"{round(part * 100)}% of wealth invested here",
                [q("patrimoine")["num"]])
    if r.get("revenus") == "<50k" and part is not None and part > 0.3:
        plafond(3, "Revenus inférieurs à 50 000 € et plus de 30 % du patrimoine placé",
                "Income under €50,000 and over 30% of wealth invested", [q("revenus")["num"], q("patrimoine")["num"]])
    if r.get("credits") and points("taux_effort", r.get("taux_effort")) not in (None, 5):
        plafond(points("taux_effort", r.get("taux_effort")), "Remboursements de crédits élevés", "High loan repayments",
                [q("taux_effort")["num"]])
    for qid, fr, en in (("statut_pro", "Situation professionnelle", "Employment status"),
                        ("stabilite_revenus", "Revenus futurs incertains", "Uncertain future income")):
        p = points(qid, r.get(qid))
        if p is not None and p < 4:
            plafond(p, fr, en, [q(qid)["num"]])
    age = r.get("age")
    if isinstance(age, (int, float)):
        if age >= 75:
            plafond(3, f"Âge : {int(age)} ans", f"Age: {int(age)}", [q("age")["num"]])
        elif age >= 65:
            plafond(4, f"Âge : {int(age)} ans", f"Age: {int(age)}", [q("age")["num"]])
    if r.get("besoin_liquidite"):
        plafond(4, "Besoin possible de retrait avant l'horizon", "Possible early withdrawal", [q("besoin_liquidite")["num"]])
    if not detail["capacite"]:
        detail["capacite"].append((T(L, "Aucune fragilité relevée → 5", "No weakness found → 5"), []))

    # --- Connaissances : quiz, puis plafond par l'expérience
    bonnes, erreurs = score_quiz(r)
    connaissances = 3 if bonnes < 3 else 4 if bonnes < 5 else 5
    texte_err = ", ".join(f"Q{q(e)['num']}" for e in erreurs)
    detail["connaissances"].append((T(L, f"Quiz {bonnes}/5" + (f" (erreurs : {texte_err})" if erreurs else "") + f" → {connaissances}",
                                      f"Quiz {bonnes}/5" + (f" (errors: {texte_err})" if erreurs else "") + f" → {connaissances}"),
                                    [q(x)["num"] for x in QUIZ]))
    exp = [points(qid, r.get(qid)) for qid in ("anciennete", "niveau")]
    nb_risques = len([p for p in (r.get("produits_detenus") or []) if p in PRODUITS_RISQUES])
    exp.append(3 if nb_risques == 0 else 4 if nb_risques <= 2 else 5)
    exp = [p for p in exp if p is not None]
    if exp:
        note_exp = arrondi_prudent(sum(exp) / len(exp))
        if note_exp < connaissances:
            connaissances = note_exp
            detail["connaissances"].append((T(L, f"Expérience (ancienneté, niveau, {nb_risques} produit(s) risqué(s) détenu(s)) → {note_exp} max.",
                                              f"Experience (track record, level, {nb_risques} risky product(s)) → {note_exp} max."),
                                            [q("anciennete")["num"], q("niveau")["num"], q("produits_detenus")["num"]]))

    notes = {"tolerance": tolerance, "horizon": horizon, "capacite": capacite, "connaissances": connaissances}
    profil = min(notes.values())
    return {"profil": profil, "notes": notes, "detail": detail, "alertes": alertes(r, L), "quiz": bonnes,
            "nom": nom_profil(profil, L), "limitant": [k for k, v in notes.items() if v == profil]}


def alertes(r: dict, langue: str = "fr") -> list[str]:
    """Points de cohérence à vérifier avec le client (ils n'abaissent pas le profil, ils se documentent)."""
    L, res = langue, []
    part = part_investie(r)
    if r.get("epargne_precaution") is False:
        res.append(T(L, "Pas d'épargne de précaution : la constituer avant d'investir.", "No emergency fund: build one first."))
    if part is not None and part > 1:
        res.append(T(L, "Le montant dépasse le patrimoine déclaré : vérifier la saisie.", "Amount exceeds declared wealth: check."))
    elif part is not None and part > 0.5:
        res.append(T(L, "Plus de la moitié du patrimoine placée ici : risque de concentration.", "Over half of wealth invested here."))
    if r.get("credits") and r.get("besoin_liquidite"):
        res.append(T(L, "Crédits en cours et besoin de liquidité : garder une réserve.", "Loans and liquidity need: keep a reserve."))
    if r.get("rendement_attendu") in ("6-8", ">8") and r.get("perte_max") in ("0", "5"):
        res.append(T(L, "Rendement espéré élevé mais presque aucune perte acceptée : à expliquer au client.",
                     "High hoped-for return but almost no loss accepted: explain to the client."))
    if r.get("cible") and r.get("montant") and r["cible"] < r["montant"]:
        res.append(T(L, "Montant visé inférieur au montant investi.", "Target below the amount invested."))
    age = r.get("age")
    if isinstance(age, (int, float)) and age >= 75 and r.get("horizon") == ">8":
        res.append(T(L, "Horizon de plus de 8 ans à 75 ans ou plus : vérifier l'objectif (transmission ?).",
                     "Horizon over 8 years at 75+: check the goal (estate planning?)."))
    if r.get("objectif") == "immobilier" and r.get("horizon") == ">8":
        res.append(T(L, "Projet immobilier à plus de 8 ans : vérifier la date du projet.", "Property project over 8 years away: check."))
    if r.get("objectif") == "revenus" and r.get("montant") and (r.get("retrait_mensuel") or 0) * 12 > 0.04 * r["montant"]:
        res.append(T(L, "Retraits supérieurs à 4 % du capital par an : risque d'épuisement du capital.",
                     "Withdrawals above 4% of capital a year: risk of depleting the capital."))
    return res
