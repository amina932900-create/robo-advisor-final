"""
livrables.py — Documents produits par l'outil :
- questionnaire_vierge(langue)        : le questionnaire à faire remplir et signer par le client (mêmes numéros que l'écran) ;
- declaration_pdf(contexte)           : la déclaration d'adéquation à faire signer (avec le fil de décision en annexe) ;
- excel(contexte)                     : le fichier de travail du conseiller (.xlsm avec macro si data/modele.xlsm existe, sinon .xlsx) ;
- email_client(contexte)              : un e-mail au client rédigé par IA (Gemini) et vérifié, que le conseiller relit avant envoi.

`contexte` est construit par contexte(dossier, langue) : réponses, profil, recommandation, contrôles, simulation, stress tests.
"""

from __future__ import annotations

import io
import os
import re
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from openpyxl import Workbook, load_workbook
from openpyxl.chart import LineChart, PieChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import BaseDocTemplate, Frame, KeepTogether, PageTemplate, Paragraph, Spacer, Table, TableStyle

import calcul_analyses as ca
import calcul_conformite
import calcul_portefeuille as cpf
import calcul_profil as qn
import donnees
from calcul_profil import T
from textes import AVERTISSEMENT, CLASSES, NOMS_COURTS, NOMS_ENVELOPPES, NOTES, date_txt, eur_txt, pct_txt

MODELE_XLSM = Path(__file__).resolve().parent / "data" / "modele.xlsm"


# ====================================================================================================
# Contexte commun aux documents
# ====================================================================================================
def contexte(dossier: dict, langue: str = "fr") -> dict:
    r = dossier["reponses"]
    prof = qn.calculer_profil(r, langue)
    dec = dossier.get("decisions") or {}
    meta = {"date_signature": dossier.get("date_signature_questionnaire"), "reference": dossier["reference"], **dec}
    reco = cpf.recommander(r, prof, dec.get("profil_retenu"), dec.get("ajustements"), meta, langue)
    ctrl = calcul_conformite.controler(r, prof, reco, dec, dossier.get("date_signature_questionnaire"), langue)
    ans = {"<2": 2, "2-5": 5, "5-8": 8, ">8": 15}.get(r.get("horizon"), 10)
    sim = ca.simuler(reco["portefeuille"], reco["enveloppe"], r["montant"], r.get("versement_mensuel") or 0,
                     r.get("retrait_mensuel") or 0, ans, r.get("cible") or 0)
    return {"dossier": dossier, "langue": langue, "reponses": r, "profil": prof, "reco": reco, "controles": ctrl,
            "synthese": calcul_conformite.synthese(ctrl), "simulation": sim, "ans": ans,
            "stress": ca.tous_les_stress(reco["portefeuille"], r["montant"], langue),
            "frais": ca.frais_totaux(reco["portefeuille"], reco["enveloppe"]),
            "mu_net": ca.rendement_net(reco["portefeuille"], reco["enveloppe"]),
            "enveloppes": cpf.repartition_enveloppes(reco["portefeuille"], reco["enveloppe"], r["montant"])}


def _txt_html(s: str) -> str:
    """Retire les balises HTML des textes du fil (badges) pour les documents."""
    return re.sub(r"<[^>]+>", "", str(s))


# ====================================================================================================
# PDF : styles communs
# ====================================================================================================
NAVY, OR, CLAIR, GRIS, TXT, DISC, LIGNE = (colors.HexColor(c) for c in ("#14213D", "#B08D57", "#F3EEE3", "#FBFAF7", "#1B2A41", "#6B7785", "#E2D5BD"))
LARG = A4[0] - 36 * mm
ST = {
    "corps": ParagraphStyle("corps", fontName="Helvetica", fontSize=9, leading=13, textColor=TXT),
    "petit": ParagraphStyle("petit", fontName="Helvetica", fontSize=7.5, leading=10, textColor=DISC),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8, leading=10, textColor=TXT),
    "tete": ParagraphStyle("tete", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=colors.white),
    "h1": ParagraphStyle("h1", fontName="Times-Bold", fontSize=22, leading=26, textColor=NAVY, spaceAfter=2),
    "h2": ParagraphStyle("h2", fontName="Times-Bold", fontSize=13, leading=16, textColor=NAVY, spaceBefore=12, spaceAfter=5, keepWithNext=1),
    "kl": ParagraphStyle("kl", fontName="Helvetica", fontSize=7, leading=9, textColor=DISC),
    "kv": ParagraphStyle("kv", fontName="Helvetica-Bold", fontSize=11.5, leading=14, textColor=NAVY),
}


def _s(x) -> str:
    x = _txt_html(x).replace(" ", " ").replace(" ", " ").replace("→", "->").replace("≥", ">=").replace("≤", "<=").replace("◂", "")
    x = x.replace("✓", "oui").replace("✗", "non").replace("…", "...").replace("’", "'").replace("±", "+/-")
    return x.encode("cp1252", "replace").decode("cp1252")


def _p(texte, style="corps"):
    return Paragraph(escape(_s(texte)), ST[style])


def _tab(lignes, largeurs, entete=True, zebre=True):
    data = [[c if not isinstance(c, str) else Paragraph(escape(_s(c)), ST["tete" if entete and i == 0 else "cell"]) for c in l]
            for i, l in enumerate(lignes)]
    t = Table(data, colWidths=largeurs, repeatRows=1 if entete else 0)
    st = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, LIGNE),
          ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5)]
    if entete:
        st.append(("BACKGROUND", (0, 0), (-1, 0), NAVY))
    if zebre:
        st += [("BACKGROUND", (0, i), (-1, i), GRIS) for i in range(1 if entete else 0, len(data)) if i % 2 == 0]
    t.setStyle(TableStyle(st))
    return t


def _doc(buffer, titre, langue):
    doc = BaseDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=22 * mm, bottomMargin=20 * mm,
                          title=_s(titre), author="Robo-advisor")

    def habillage(c, d):
        c.saveState()
        c.setFillColor(NAVY)
        c.rect(0, A4[1] - 13 * mm, A4[0], 13 * mm, stroke=0, fill=1)
        c.setFillColor(OR)
        c.rect(0, A4[1] - 13.8 * mm, A4[0], 0.8 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Times-Bold", 11)
        c.drawString(18 * mm, A4[1] - 8.5 * mm, _s(titre))
        c.setFont("Helvetica", 8)
        c.drawRightString(A4[0] - 18 * mm, A4[1] - 8.5 * mm, str(d.page))
        c.setFillColor(DISC)
        c.setFont("Helvetica", 6.5)
        c.drawCentredString(A4[0] / 2, 10 * mm, _s(AVERTISSEMENT[langue]))
        c.restoreState()
    doc.addPageTemplates([PageTemplate(id="p", frames=[Frame(18 * mm, 18 * mm, LARG, A4[1] - 40 * mm, id="f", leftPadding=0, rightPadding=0,
                                                             topPadding=0, bottomPadding=0)], onPage=habillage)])
    return doc


def _signatures(L):
    t = Table([[_p(T(L, "Le client — date et signature", "Client — date and signature"), "cell"),
                _p(T(L, "Le conseiller — date et signature", "Adviser — date and signature"), "cell")]],
              colWidths=[LARG / 2 - 4 * mm, LARG / 2 - 4 * mm], rowHeights=[26 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (0, 0), 0.5, DISC), ("BOX", (1, 0), (1, 0), 0.5, DISC)]))
    return t


# ====================================================================================================
# Questionnaire vierge à faire signer
# ====================================================================================================
def questionnaire_vierge(langue: str = "fr") -> bytes:
    L = langue
    buf = io.BytesIO()
    titre = T(L, "Questionnaire de connaissance client", "Client knowledge questionnaire")
    doc = _doc(buf, titre, L)
    h = [_p(titre, "h1"),
         _p(T(L, "Référence client : ____________    Date : ____ / ____ / ________    Montant envisagé : ______________ €",
              "Client reference: ____________    Date: ____ / ____ / ________    Amount considered: ______________ €")),
         Spacer(1, 4),
         _p(T(L, "Ce questionnaire permet à votre conseiller de vérifier que ses recommandations vous conviennent (directive MiFID II). "
                 "Merci de répondre à toutes les questions ; les questions précédées de « Si » ne concernent que certains cas. "
                 "Aucun nom n'est conservé dans l'outil : seule la référence ci-dessus identifie votre dossier.",
              "This questionnaire lets your adviser check that recommendations suit you (MiFID II). Please answer all questions."), "petit")]
    for b, nom in qn.BLOCS.items():
        h.append(_p(f"{b}. {nom[L]}", "h2"))
        for q in qn.QUESTIONS:
            if q["bloc"] != b:
                continue
            if q["type"] in ("nombre", "euros"):
                rep = "________________" + (" €" if q["type"] == "euros" else "")
            elif q["type"] == "oui_non":
                rep = T(L, "[  ] Oui     [  ] Non", "[  ] Yes     [  ] No")
            elif q["type"] == "vrai_faux":
                rep = T(L, "[  ] Vrai     [  ] Faux", "[  ] True     [  ] False")
            else:
                i = 2 if L == "en" else 1
                rep = "     ".join(f"[  ] {o[i]}" for o in q["options"])
            h.append(KeepTogether([_p(f"<b>Q{q['num']}.</b> {escape(_s(q[L]))}".replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>")),
                                   Paragraph(escape(_s(rep)), ST["cell"]), Spacer(1, 4)]))
    h += [Spacer(1, 10), _p(T(L, "Je certifie l'exactitude de mes réponses et m'engage à informer mon conseiller de tout changement de situation.",
                              "I certify my answers are accurate and will inform my adviser of any change.")), Spacer(1, 6), _signatures(L)]
    doc.build(h)
    return buf.getvalue()


# ====================================================================================================
# Déclaration d'adéquation
# ====================================================================================================
def _barre(classes, L):
    d = Drawing(LARG, 34)
    x = 0
    coul = {"actions": "#14213D", "obligations": "#3E6E8E", "monetaire": "#9DB4C0", "diversifiants": "#B08D57", "scpi": "#7A6C5D", "actif": "#C9B79C"}
    for c, w in classes.items():
        if w > 1e-6:
            d.add(Rect(x, 18, w * LARG, 12, fillColor=colors.HexColor(coul[c]), strokeColor=colors.white))
            x += w * LARG
    x = 0
    for c, w in classes.items():
        if w > 1e-6:
            t = f"{_s(CLASSES[L][c])} {pct_txt(w, 0, L)}"
            d.add(Rect(x, 4, 7, 7, fillColor=colors.HexColor(coul[c]), strokeColor=None))
            d.add(String(x + 10, 4, t, fontName="Helvetica", fontSize=7.5, fillColor=TXT))
            x += 16 + 4.1 * len(t)
    return d


def declaration_pdf(ctx: dict) -> bytes:
    L, r, reco, prof = ctx["langue"], ctx["reponses"], ctx["reco"], ctx["profil"]
    d = ctx["dossier"]
    P = lambda x, k=1: pct_txt(x, k, L)
    E = lambda x: eur_txt(x, L)
    buf = io.BytesIO()
    titre = T(L, "Déclaration d'adéquation", "Suitability statement")
    doc = _doc(buf, f"{titre} · {d['reference']}", L)
    h = [_p(titre, "h1"), _p(T(L, f"Référence {d['reference']} · établie le {date_txt(date.today().isoformat(), L)} · questionnaire signé le "
                                 f"{date_txt(d.get('date_signature_questionnaire'), L)}",
                               f"Reference {d['reference']} · issued {date_txt(date.today().isoformat(), L)}"), "petit"), Spacer(1, 6)]
    kp = [(T(L, "Montant", "Amount"), E(r["montant"])), (T(L, "Profil", "Profile"), f"{reco['profil']}/5 {qn.nom_profil(reco['profil'], L)}"),
          (T(L, "Enveloppe", "Wrapper"), NOMS_ENVELOPPES[L][reco["enveloppe"]]),
          (T(L, "Risque attendu", "Expected risk"), f"{P(reco['vol'])} · SRI {reco['sri']}/7")]
    t = Table([[Paragraph(escape(_s(a)), ST["kl"]) for a, _ in kp], [Paragraph(escape(_s(b)), ST["kv"]) for _, b in kp]], colWidths=[LARG / 4] * 4)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), CLAIR), ("LEFTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, 0), 6),
                           ("BOTTOMPADDING", (0, 1), (-1, 1), 7)]))
    h.append(t)

    # 1. Situation et objectifs
    h.append(_p(T(L, "1. Votre situation et vos objectifs", "1. Your situation and goals"), "h2"))
    cles = ["age", "situation_familiale", "revenus", "patrimoine", "objectif", "horizon", "versement_mensuel", "cible", "durabilite"]
    h.append(_tab([[T(L, "Élément", "Item"), T(L, "Réponse signée", "Signed answer")]] +
                  [[f"Q{qn.q(k)['num']} · {qn.q(k)[L]}", qn.libelle(k, r.get(k), L)] for k in cles if k in r],
                  [105 * mm, LARG - 105 * mm]))

    # 2. Profil
    h.append(_p(T(L, "2. Votre profil de risque", "2. Your risk profile"), "h2"))
    h.append(_p(T(L, f"Votre profil est {qn.nom_profil(reco['profil'], L)} ({reco['profil']}/5) : la plus petite de vos 4 notes, règle prudente appliquée par les banques.",
                  f"Your profile is {qn.nom_profil(reco['profil'], L)} ({reco['profil']}/5): the lowest of your 4 scores.")))
    h.append(Spacer(1, 3))
    h.append(_tab([[T(L, "Note", "Score"), "/5", T(L, "Justification", "Rationale")]] +
                  [[NOTES[L][k], str(v), " ; ".join(t_ for t_, _ in prof["detail"][k])] for k, v in prof["notes"].items()],
                  [48 * mm, 10 * mm, LARG - 58 * mm]))

    # 3. Recommandation
    h.append(_p(T(L, "3. Notre recommandation", "3. Our recommendation"), "h2"))
    h.append(_barre(reco["classes"], L))
    u = donnees.univers()
    lignes = [[T(L, "Support", "Product"), T(L, "Poids", "Weight"), T(L, "Montant", "Amount"), T(L, "Frais", "Fees"), "SRI",
               T(L, "Enveloppe", "Wrapper")]]
    une_estimee = False
    for isin, w in sorted(reco["portefeuille"].items(), key=lambda x: (cpf.CLASSES.index(u.loc[x[0], "classe"]), -x[1])):
        l = u.loc[isin]
        sri, est = donnees.sri(isin)
        une_estimee = une_estimee or est
        sous = donnees.secteur_pays(isin, L) if l["type"] == "action" else isin
        lignes.append([Paragraph(f"{escape(_s(l['nom']))}<br/><font size=6.5 color='#6B7785'>{escape(_s(sous))}</font>", ST["cell"]),
                       P(w), E(w * r["montant"]), "-" if (l["ter_num"] != l["ter_num"] or l["type"] == "action") else P(l["ter_num"], 2), f"{sri}{'*' if est else ''}",
                       NOMS_COURTS[L][ctx["enveloppes"][isin]]])
    h += [Spacer(1, 3), _tab(lignes, [80 * mm, 14 * mm, 24 * mm, 14 * mm, 11 * mm, LARG - 143 * mm])]
    if une_estimee:
        h.append(_p(T(L, "* Action détenue en direct (pas de DIC) : SRI estimé à partir de la volatilité de sa classe d'actifs. Les autres SRI sont ceux des DIC.",
                      "* Directly held stock (no KID): SRI estimated from its asset-class volatility. Other SRIs come from the KIDs."), "petit"))

    # 4. Risques, frais, projection
    h.append(_p(T(L, "4. Risques, frais et perspectives", "4. Risks, fees and outlook"), "h2"))
    f = ctx["frais"]
    sim = ctx["simulation"]
    vmin, vmax = cpf.PROFILS[reco["profil"]]["vol"]
    h.append(_tab([[T(L, "Indicateur", "Indicator"), T(L, "Valeur", "Value")],
                   [T(L, "Volatilité attendue (zone du profil)", "Expected volatility (profile range)"), f"{P(reco['vol'])} ({P(vmin, 0)}–{P(vmax, 0)})"],
                   [T(L, "Rendement annuel attendu, net de tous les frais", "Expected annual return, net of all fees"), P(ctx["mu_net"], 2)],
                   [T(L, "Frais annuels : fonds + contrat + SCPI", "Annual fees: funds + wrapper + SCPI"),
                    f"{P(f['total'], 2)} ({P(f['fonds'], 2)} + {P(f['contrat'], 2)} + {P(f['scpi'], 2)})"],
                   [T(L, f"Capital dans {ctx['ans']} ans : défavorable / central / favorable", f"Capital in {ctx['ans']} years: low / central / high"),
                    f"{E(sim['p10'][-1])} / {E(sim['p50'][-1])} / {E(sim['p90'][-1])}"]]
                  + ([[T(L, "Probabilité d'atteindre votre objectif", "Probability of reaching your target"), P(sim["proba_cible"], 0)]]
                     if sim.get("proba_cible") is not None else []), [110 * mm, LARG - 110 * mm]))
    h.append(Spacer(1, 4))
    h.append(_tab([[T(L, "Scénario de crise", "Crisis scenario"), T(L, "Impact", "Impact"), T(L, "En euros", "In euros")]] +
                  [[f"{x['nom']} ({x['periode']})", P(x["variation"]), E(x["euros"])] for x in ctx["stress"]],
                  [110 * mm, 25 * mm, LARG - 135 * mm]))
    h.append(_p(T(L, "Perte en capital possible sur toutes les lignes sauf le fonds en euros. Les performances passées ne préjugent pas des performances "
                     "futures ; les projections reposent sur des hypothèses publiées (Amundi, 2026) et ne sont pas garanties.",
                  "Capital loss possible on every line except the euro fund. Projections are not guaranteed."), "petit"))

    # 5. Fil de décision
    h.append(_p(T(L, "5. Comment cette recommandation a été construite", "5. How this recommendation was built"), "h2"))
    for e in reco["fil"]:
        bloc = [_p(f"<b>{e['n']}. {escape(_s(e['titre']))}</b> — {escape(_s(e['resultat']))}".replace("&lt;", "<").replace("&gt;", ">")),
                _p(T(L, "Règle : ", "Rule: ") + e["regle"], "petit")]
        for t_, refs in e["details"]:
            bloc.append(_p("• " + t_ + (" [" + ", ".join(f"Q{n}" for n in refs) + "]" if refs else ""), "cell"))
        if e.get("source"):
            bloc.append(_p(T(L, "Source : ", "Source: ") + e["source"], "petit"))
        h += [KeepTogether(bloc), Spacer(1, 4)]

    # 6. Contrôles
    h.append(_p(T(L, "6. Contrôles d'adéquation", "6. Suitability checks"), "h2"))
    lib = {"ok": T(L, "Conforme", "Compliant"), "attention": T(L, "À documenter", "To document"), "bloquant": T(L, "Bloquant", "Blocking")}
    h.append(_tab([[T(L, "Contrôle", "Check"), T(L, "Statut", "Status"), T(L, "Détail", "Detail")]] +
                  [[c["titre"], lib[c["statut"]], c["detail"]] for c in ctx["controles"]], [52 * mm, 22 * mm, LARG - 74 * mm]))

    # 7. Conclusion
    h.append(_p(T(L, "7. Conclusion", "7. Conclusion"), "h2"))
    if ctx["synthese"] == "bloquant":
        texte = T(L, "Un contrôle bloquant subsiste : cette recommandation ne peut pas vous être remise en l'état.",
                  "A blocking check remains: this recommendation cannot be issued.")
    else:
        texte = T(L, f"Au vu des réponses que vous avez signées, le portefeuille proposé est adapté à votre profil {qn.nom_profil(reco['profil'], L)} : "
                     f"son risque attendu reste dans les limites fixées pour ce profil, et l'enveloppe {NOMS_ENVELOPPES[L][reco['enveloppe']]} "
                     "est cohérente avec votre objectif et votre horizon.",
                  f"Given your signed answers, the proposed portfolio suits your {qn.nom_profil(reco['profil'], L)} profile.")
    cadre = Table([[_p(texte)]], colWidths=[LARG])
    cadre.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), CLAIR), ("LEFTPADDING", (0, 0), (-1, -1), 10),
                               ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    h.append(KeepTogether([cadre, Spacer(1, 10), _signatures(L)]))

    # Annexe
    h.append(_p(T(L, "Annexe — vos réponses au questionnaire", "Appendix — your questionnaire answers"), "h2"))
    h.append(_tab([["N°", "Question", T(L, "Réponse", "Answer")]] +
                  [[f"Q{q['num']}", q[L], qn.libelle(q["id"], r.get(q["id"]), L)] for q in qn.QUESTIONS if qn.visible(q, r)],
                  [12 * mm, 105 * mm, LARG - 117 * mm]))
    doc.build(h)
    return buf.getvalue()


# ====================================================================================================
# Excel du conseiller (avec macro VBA si le modèle data/modele.xlsm est présent)
# ====================================================================================================
FIN = Side(style="thin", color="E2D5BD")
BORD = Border(bottom=FIN)
F_EUR, F_PCT, F_PCT2 = '#,##0 "€"', "0.0%", "0.00%"


def _titre_xl(ws, titre, sous, n):
    ws.sheet_view.showGridLines = False
    for rr in (1, 2):
        for c in range(1, n + 1):
            ws.cell(row=rr, column=c).fill = PatternFill("solid", fgColor="14213D")
    ws["A1"], ws["A2"] = titre, sous
    ws["A1"].font = Font(bold=True, size=16, color="FFFFFF")
    ws["A2"].font = Font(size=10, color="B08D57")


def _entetes(ws, ligne, vals):
    for j, v in enumerate(vals, start=1):
        c = ws.cell(row=ligne, column=j, value=v)
        c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="14213D")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def excel(ctx: dict) -> tuple[bytes, str]:
    """Renvoie (contenu, extension). Si data/modele.xlsm existe (macro MiseEnForme importée), le fichier est un .xlsm."""
    L, r, reco = ctx["langue"], ctx["reponses"], ctx["reco"]
    u = donnees.univers()
    avec_macro = MODELE_XLSM.exists()
    wb = load_workbook(MODELE_XLSM, keep_vba=True) if avec_macro else Workbook()
    for ws in list(wb.worksheets):
        wb.remove(ws)
    ref = ctx["dossier"]["reference"]

    ws = wb.create_sheet(T(L, "Synthèse", "Summary"))
    _titre_xl(ws, T(L, "Recommandation", "Recommendation") + f" · {ref}", date_txt(date.today().isoformat(), L), 4)
    lignes = [(T(L, "Montant", "Amount"), r["montant"], F_EUR), (T(L, "Profil", "Profile"), f"{reco['profil']}/5 {qn.nom_profil(reco['profil'], L)}", None),
              (T(L, "Profil calculé", "Computed profile"), reco["profil_calcule"], None),
              (T(L, "Enveloppe", "Wrapper"), NOMS_ENVELOPPES[L][reco["enveloppe"]], None),
              (T(L, "Volatilité attendue", "Expected volatility"), reco["vol"], F_PCT), ("SRI", reco["sri"], None),
              (T(L, "Rendement attendu net", "Expected net return"), ctx["mu_net"], F_PCT2),
              (T(L, "Frais annuels totaux", "Total annual fees"), ctx["frais"]["total"], F_PCT2),
              (T(L, f"Capital central dans {ctx['ans']} ans", f"Central capital in {ctx['ans']} years"), ctx["simulation"]["p50"][-1], F_EUR),
              (T(L, "Conformité", "Compliance"), ctx["synthese"], None)]
    for i, (a, b, f) in enumerate(lignes, start=4):
        ws.cell(row=i, column=1, value=a).border = BORD
        c = ws.cell(row=i, column=2, value=b)
        c.font, c.border = Font(bold=True), BORD
        if f:
            c.number_format = f
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 42, 28

    ws = wb.create_sheet(T(L, "Portefeuille", "Portfolio"))
    _titre_xl(ws, T(L, "Portefeuille", "Portfolio"), ref, 8)
    _entetes(ws, 4, [T(L, "Support", "Product"), "ISIN", T(L, "Classe", "Class"), T(L, "Poids", "Weight"), T(L, "Montant", "Amount"),
                     T(L, "Frais", "Fees"), T(L, "Enveloppe", "Wrapper"), T(L, "Raison du choix", "Reason")])
    k = 5
    for isin, w in sorted(reco["portefeuille"].items(), key=lambda x: (cpf.CLASSES.index(u.loc[x[0], "classe"]), -x[1])):
        l = u.loc[isin]
        vals = [l["nom"], isin, CLASSES[L][l["classe"]], w, f"=D{k}*Synth!B4".replace("Synth", f"'{T(L, 'Synthèse', 'Summary')}'"),
                None if l["ter_num"] != l["ter_num"] else float(l["ter_num"]), NOMS_COURTS[L][ctx["enveloppes"][isin]], reco["lignes"][isin]["raison"]]
        for j, v in enumerate(vals, start=1):
            c = ws.cell(row=k, column=j, value=v)
            c.border = BORD
        ws.cell(row=k, column=4).number_format, ws.cell(row=k, column=5).number_format, ws.cell(row=k, column=6).number_format = F_PCT, F_EUR, F_PCT2
        k += 1
    ws.cell(row=k, column=1, value="Total").font = Font(bold=True)
    ws.cell(row=k, column=4, value=f"=SUM(D5:D{k - 1})").number_format = F_PCT
    ws.cell(row=k, column=5, value=f"=SUM(E5:E{k - 1})").number_format = F_EUR
    for col, wd in zip("ABCDEFGH", (46, 16, 22, 9, 13, 8, 14, 70)):
        ws.column_dimensions[col].width = wd
    ws.auto_filter.ref = f"A4:H{k - 1}"
    ws.freeze_panes = "A5"
    base = k + 2
    _entetes(ws, base, [T(L, "Classe", "Class"), T(L, "Poids", "Weight")])
    cl = [(c, w) for c, w in reco["classes"].items() if w > 1e-6]
    for i, (c, w) in enumerate(cl, start=base + 1):
        ws.cell(row=i, column=1, value=CLASSES[L][c])
        ws.cell(row=i, column=2, value=w).number_format = F_PCT
    pie = PieChart()
    pie.title = T(L, "Allocation", "Allocation")
    pie.add_data(Reference(ws, min_col=2, min_row=base, max_row=base + len(cl)), titles_from_data=True)
    pie.set_categories(Reference(ws, min_col=1, min_row=base + 1, max_row=base + len(cl)))
    ws.add_chart(pie, f"D{base}")

    ws = wb.create_sheet(T(L, "Fil de décision", "Decision trail"))
    _titre_xl(ws, T(L, "Fil de décision", "Decision trail"), T(L, "Comment la recommandation a été construite", "How it was built"), 4)
    _entetes(ws, 4, ["N°", T(L, "Étape", "Step"), T(L, "Résultat et justification", "Result and rationale"), T(L, "Questions", "Questions")])
    k = 5
    for e in reco["fil"]:
        ws.cell(row=k, column=1, value=e["n"])
        ws.cell(row=k, column=2, value=e["titre"]).font = Font(bold=True)
        ws.cell(row=k, column=3, value=f"{e['resultat']} — {e['regle']}").font = Font(bold=True)
        k += 1
        for t_, refs in e["details"]:
            ws.cell(row=k, column=3, value=_txt_html(t_)).alignment = Alignment(wrap_text=True)
            ws.cell(row=k, column=4, value=", ".join(f"Q{n}" for n in refs))
            k += 1
    for col, wd in zip("ABCD", (5, 30, 110, 22)):
        ws.column_dimensions[col].width = wd

    ws = wb.create_sheet(T(L, "Projection", "Projection"))
    _titre_xl(ws, T(L, "Projection", "Projection"), T(L, "10 000 trajectoires (hypothèses Amundi 2026)", "10,000 paths"), 6)
    sim = ctx["simulation"]
    _entetes(ws, 4, [T(L, "Année", "Year"), T(L, "Défavorable", "Low"), T(L, "Central", "Central"), T(L, "Favorable", "High"), "60/40",
                     T(L, "Versé", "Contributed")])
    a0 = date.today().year
    for a in range(len(sim["p50"])):
        for j, v in enumerate([a0 + a, sim["p10"][a], sim["p50"][a], sim["p90"][a], sim["ref_6040"][a], sim["verse"][a]], start=1):
            c = ws.cell(row=5 + a, column=j, value=v)
            if j > 1:
                c.number_format = F_EUR
    ch = LineChart()
    ch.title, ch.height, ch.width = T(L, "Évolution possible du capital", "How the capital could evolve"), 9, 22
    ch.add_data(Reference(ws, min_col=2, max_col=6, min_row=4, max_row=4 + len(sim["p50"])), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=1, min_row=5, max_row=4 + len(sim["p50"])))
    ws.add_chart(ch, "H4")
    for col in "ABCDEF":
        ws.column_dimensions[col].width = 15

    ws = wb.create_sheet(T(L, "Conformité", "Compliance"))
    _titre_xl(ws, T(L, "Contrôles d'adéquation", "Suitability checks"), ref, 4)
    _entetes(ws, 4, [T(L, "Contrôle", "Check"), T(L, "Statut", "Status"), T(L, "Détail", "Detail"), T(L, "Référence", "Rule")])
    fond = {"ok": "E6F4EA", "attention": "FFF4DB", "bloquant": "FDE8E8"}
    for i, c in enumerate(ctx["controles"], start=5):
        for j, v in enumerate([c["titre"], c["statut"], c["detail"], c["regle"]], start=1):
            x = ws.cell(row=i, column=j, value=v)
            x.alignment = Alignment(wrap_text=True, vertical="center")
        ws.cell(row=i, column=2).fill = PatternFill("solid", fgColor=fond[c["statut"]])
    for col, wd in zip("ABCD", (40, 12, 80, 45)):
        ws.column_dimensions[col].width = wd

    ws = wb.create_sheet(T(L, "Réponses", "Answers"))
    _titre_xl(ws, T(L, "Questionnaire signé", "Signed questionnaire"), T(L, f"signé le {date_txt(ctx['dossier'].get('date_signature_questionnaire'), L)}", ""), 3)
    _entetes(ws, 4, ["N°", "Question", T(L, "Réponse", "Answer")])
    for i, q in enumerate([q for q in qn.QUESTIONS if qn.visible(q, r)], start=5):
        ws.cell(row=i, column=1, value=f"Q{q['num']}")
        ws.cell(row=i, column=2, value=q[L])
        ws.cell(row=i, column=3, value=qn.libelle(q["id"], r.get(q["id"]), L))
    for col, wd in zip("ABC", (6, 80, 40)):
        ws.column_dimensions[col].width = wd

    wb.active = 0
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue(), ("xlsm" if avec_macro else "xlsx")


# ====================================================================================================
# E-mail au client rédigé par IA (Gemini), avec garde-fou : aucun chiffre absent des données fournies
# ====================================================================================================
# Essayés dans l'ordre ; les noms changent souvent : GEMINI_MODEL (secrets) force un modèle précis vu dans Google AI Studio.
MODELES_GEMINI = ["gemini-3.1-flash-lite", "gemini-flash-latest", "gemini-flash-lite-latest", "gemini-2.5-flash", "gemini-2.5-flash-lite"]
derniere_source = "aucune"


def _secret(nom: str) -> str | None:
    try:
        import streamlit as st
        if nom in st.secrets:
            return str(st.secrets[nom])
    except Exception:
        pass
    return os.environ.get(nom)


def chiffres_autorises(ctx: dict) -> dict[str, str]:
    L, r, reco, sim = ctx["langue"], ctx["reponses"], ctx["reco"], ctx["simulation"]
    env_txt = NOMS_ENVELOPPES[L][reco["enveloppe"]]
    c = {"profil": f"{reco['profil']}/5 ({qn.nom_profil(reco['profil'], L)})",
         "enveloppe": env_txt if reco["enveloppe"] == "PEA" else env_txt.lower(),
         "montant investi": eur_txt(r["montant"], L), "nombre de lignes": str(len(reco["portefeuille"])),
         "frais annuels totaux": pct_txt(ctx["frais"]["total"], 2, L), "durée de la projection (ans)": str(ctx["ans"]),
         "capital central à terme": eur_txt(sim["p50"][-1], L), "capital défavorable à terme": eur_txt(sim["p10"][-1], L),
         "capital favorable à terme": eur_txt(sim["p90"][-1], L)}
    for k, w in reco["classes"].items():
        if w > 1e-6:
            c[f"part {CLASSES[L][k].lower()}"] = pct_txt(w, 0, L)
    if sim.get("proba_cible") is not None:
        c["probabilité d'atteindre l'objectif"] = pct_txt(sim["proba_cible"], 0, L)
    return c


def _nombres(texte: str) -> list[float]:
    res = []
    for brut in re.findall(r"\d{1,3}(?:[   ,]\d{3})+(?:[.,]\d+)?(?!\d)|\d+(?:[.,]\d+)?", texte):
        s = re.sub(r"[   ,](?=\d{3}(?:\D|$))", "", brut).replace(",", ".")
        try:
            res.append(float(s))
        except ValueError:
            pass
    return res


def chiffres_inventes(texte: str, ctx: dict) -> list[float]:
    ok = {1.0, 2.0, 3.0, 4.0, 5.0, 7.0, 8.0, 10.0, 50.0, 90.0, 60.0, 40.0}
    for v in chiffres_autorises(ctx).values():
        for x in _nombres(v):
            ok |= {round(x, 1), float(round(x))}
    ok |= {float(n) for n in _nombres(ctx["dossier"]["reference"])}
    return [x for x in _nombres(texte) if round(x, 1) not in ok and float(round(x)) not in ok]


def email_modele(ctx: dict) -> tuple[str, str]:
    """Plan B (et base de l'IA) : e-mail sobre, rempli uniquement avec les chiffres calculés."""
    L, c = ctx["langue"], chiffres_autorises(ctx)
    objet = T(L, f"Votre recommandation d'investissement — réf. {ctx['dossier']['reference']}",
              f"Your investment recommendation — ref. {ctx['dossier']['reference']}")
    corps = T(L, f"""Madame, Monsieur,

Suite à notre échange et au questionnaire que vous avez signé, je vous adresse ma recommandation.

Votre profil ressort {c['profil']}. Je vous propose de placer {c['montant investi']} en {c['enveloppe']}, répartis sur {c['nombre de lignes']} supports, pour des frais annuels totaux de {c['frais annuels totaux']}.

Sur {c['durée de la projection (ans)']} ans, le capital pourrait atteindre {c['capital central à terme']} dans un scénario central, entre {c['capital défavorable à terme']} et {c['capital favorable à terme']} dans 8 cas sur 10. Ces projections ne sont pas garanties.

Vous trouverez ci-joint la déclaration d'adéquation, qui détaille chaque choix et ses raisons, à me retourner signée.

Je reste à votre disposition pour en parler.

Bien cordialement,
Votre conseiller""", f"""Dear client,

Following our meeting and the questionnaire you signed, please find my recommendation.

Your profile is {c['profil']}. I propose investing {c['montant investi']} in a {c['enveloppe']}, across {c['nombre de lignes']} products, with total annual fees of {c['frais annuels totaux']}.

Over {c['durée de la projection (ans)']} years, the capital could reach {c['capital central à terme']} in a central scenario, between {c['capital défavorable à terme']} and {c['capital favorable à terme']} in 8 cases out of 10. These projections are not guaranteed.

Attached is the suitability statement, which explains each choice, to be returned signed.

Kind regards,
Your adviser""")
    return objet, corps


def email_client(ctx: dict) -> tuple[str, str, str]:
    """(objet, corps, source). L'IA reformule à partir des seuls chiffres fournis ; sinon, modèle fixe."""
    global derniere_source
    objet, base = email_modele(ctx)
    cle = _secret("GEMINI_API_KEY")
    if not cle:
        derniere_source = "modèle (pas de clé GEMINI_API_KEY)"
        return objet, base, derniere_source
    L = ctx["langue"]
    donnees_ia = "\n".join(f"- {k} : {v}" for k, v in chiffres_autorises(ctx).items())
    raisons = "\n".join(f"- {e['titre']} : {_txt_html(e['resultat'])}" for e in ctx["reco"]["fil"][2:6])
    prompt = (f"Tu es conseiller en gestion de patrimoine. Rédige en {'anglais' if L == 'en' else 'français'} un e-mail de 170 mots au plus "
              "à ton client (vouvoiement, ton chaleureux et professionnel) pour lui présenter sa recommandation et lui demander de "
              "retourner signée la déclaration d'adéquation jointe.\nRègles : 1. N'utilise QUE les chiffres ci-dessous, recopiés tels quels ; "
              "n'en calcule aucun autre. 2. Ne promets aucun rendement ; précise que les projections ne sont pas garanties. "
              "3. Pas de markdown, pas d'objet, signe « Votre conseiller ».\n\n"
              f"Chiffres :\n{donnees_ia}\n\nRaisons principales :\n{raisons}")
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=cle, http_options=types.HttpOptions(timeout=20_000))
        modeles = [_secret("GEMINI_MODEL")] if _secret("GEMINI_MODEL") else MODELES_GEMINI
        texte, erreurs = None, []
        import time
        for m in modeles:
            for essai in range(3):                      # 503 (modèle surchargé) ou 429 (quota) : on réessaie après une pause
                try:
                    # limite large : les modèles récents « réfléchissent » avant d'écrire et consomment des jetons
                    rep = client.models.generate_content(model=m, contents=prompt,
                                                         config=types.GenerateContentConfig(temperature=0.3, max_output_tokens=4096))
                    if rep.text and rep.text.strip():
                        texte, utilise = rep.text.strip(), m
                    else:
                        erreurs.append(f"{m} : réponse vide")
                    break
                except Exception as e:
                    code = re.search(r"\b(4\d\d|5\d\d)\b", str(e))
                    code = code.group(1) if code else type(e).__name__
                    if code in ("503", "429", "500") and essai < 2:
                        time.sleep(2 * (essai + 1))
                        continue
                    erreurs.append(f"{m} : {code}")
                    break
            if texte:
                break
        if not texte:
            raise RuntimeError(", ".join(erreurs) or "aucun modèle n'a répondu")
    except Exception as e:
        derniere_source = f"modèle (IA indisponible : {type(e).__name__} — {str(e)[:240]})"
        return objet, base, derniere_source
    inventes = chiffres_inventes(texte, ctx)
    if inventes:
        derniere_source = f"modèle (l'IA a cité des chiffres non fournis : {inventes[:3]})"
        return objet, base, derniere_source
    derniere_source = f"IA : {utilise}"
    return objet, texte, derniere_source
