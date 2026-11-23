"""
ecran_methodologie.py — Méthodologie : la chaîne de décision, les règles, les hypothèses, la qualité des données et les limites.
Page pensée pour le jury et pour le contrôle de conformité.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import calcul_analyses as ca
import calcul_marches
import calcul_portefeuille as cpf
import calcul_profil as qn
import commun
import donnees
from commun import pct, tr


def page():
    i = 1 if commun.L() == "en" else 0
    commun.entete(tr("Méthodologie", "Methodology"), tr("Ce que l'outil calcule, sur quelles règles, avec quelles données, et ses limites.",
                                                         "What the tool computes, on which rules and data, and its limits."))
    o = st.tabs([tr("Règles de décision", "Decision rules"), tr("Hypothèses de marché", "Market assumptions"),
                 tr("Qualité des données", "Data quality"), tr("Limites", "Limits")])
    with o[0]:
        st.markdown(tr("""
**Qui utilise l'outil ?** Le conseiller. Le client remplit et signe le questionnaire ; le conseiller le saisit, obtient une recommandation
justifiée, l'ajuste en motivant chaque dérogation, et remet la déclaration d'adéquation à signer.

**Profil.** Quatre notes sur 5 : tolérance (moyenne de 4 réponses, arrondi prudent), horizon (< 2 ans → 1 ; 2-5 → 3 ; 5-8 → 4 ; > 8 → 5),
capacité à subir des pertes (5, abaissée par chaque fragilité : pas d'épargne de précaution, plus de 50 % du patrimoine, crédits lourds,
revenus instables, âge, besoin de liquidité), connaissances (quiz, plafonné par l'expérience). **Le profil est la plus petite note.**
Le conseiller peut l'abaisser avec un motif écrit, jamais le relever.

**Allocation.** Grille ci-dessous ; le conseiller peut déplacer actions et obligations de ±10 points (motif obligatoire), le monétaire
compense ; tout réglage qui fait dépasser la volatilité maximale du profil est refusé.

**Choix des supports.** Filtres (enveloppe, version ISR si préférence durable, exclusions) puis classement par critères : encours > 500 M€,
réplication physique, 5 ans d'historique, frais les plus bas. Une donnée non vérifiée compte comme critère non rempli. Aucun tirage au sort.

**Satellite.** SCPI : assurance-vie et horizon > 8 ans. Fonds actif : 5 % (patrimonial pour les profils 2-3, actions pour 4-5).
Actions en direct (profils 4-5, PEA ou compte-titres, connaissances ≥ 4) : un titre européen par secteur, le moins volatil de son secteur sur 3 ans.

**Contrôle.** Volatilité attendue sous le maximum du profil, SRI du portefeuille sous son maximum, 15 contrôles d'adéquation possibles ;
un contrôle bloquant empêche l'émission de la déclaration.
""", """
**Who uses the tool?** The adviser. The client fills and signs the questionnaire; the adviser enters it, gets a justified recommendation,
adjusts it with written reasons, and hands over the suitability statement for signature.

**Profile.** Four scores out of 5; the profile is the lowest. It may be lowered with a written reason, never raised.

**Selection.** Filters, then ranking: AuM > €500m, physical replication, 5-year history, lowest fees. No randomness.
"""))
        grille = pd.DataFrame([{tr("Profil", "Profile"): f"{p} · {qn.nom_profil(p, commun.L())}",
                                **{commun.nom_classe(c): pct(w, 0) for c, w in v["allocation"].items()},
                                tr("Volatilité attendue", "Expected volatility"): f"{pct(v['vol'][0], 0)} – {pct(v['vol'][1], 0)}",
                                tr("SRI max.", "Max SRI"): v["sri_max"]} for p, v in cpf.PROFILS.items()])
        st.dataframe(grille, hide_index=True, width="stretch")
        st.caption(tr("Fourchettes calées sur la volatilité attendue de chaque grille (hypothèses Amundi, corrélations ci-contre) ; "
                      "SRI maximum = classe PRIIPs de la borne haute.", "Ranges calibrated on expected volatility; max SRI = PRIIPs class of the upper bound."))
    with o[1]:
        st.dataframe(pd.DataFrame([{tr("Classe d'actifs", "Asset class"): ca.NOMS_CLASSES[c][i], tr("Rendement attendu", "Expected return"): pct(m, 1),
                                    tr("Volatilité", "Volatility"): pct(s, 1)} for c, (m, s) in ca.HYPOTHESES.items()]), hide_index=True, width="stretch")
        st.caption(tr("Source : ", "Source: ") + ca.SOURCE_HYPOTHESES + tr(". Bruts de frais ; la ligne immobilier coté est à confirmer dans le tableau source.",
                                                                          ". Gross of fees."))
        noms = [ca.NOMS_CLASSES[c][i] for c in ca.CLASSES]
        fig = go.Figure(go.Heatmap(z=ca.CORRELATIONS, x=noms, y=noms, zmin=-1, zmax=1, colorscale="RdBu_r",
                                   text=[[f"{v:.2f}" for v in l] for l in ca.CORRELATIONS], texttemplate="%{text}"))
        fig.update_layout(height=460, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, width="stretch", key="fig_corr")
        st.caption(tr("Corrélations de long terme (ordres de grandeur) ; risque propre d'une action seule : 20 % par an. "
                      "Une seule volatilité fait foi dans l'outil : la volatilité attendue, utilisée pour le profil, la conformité, la frontière et la projection.",
                      "Long-run correlations; stock-specific risk 20% a year. One volatility rules: the expected one."))
    with o[2]:
        u = donnees.univers()
        fonds = u[u["type"] == "fonds"]
        todo = {c: int((fonds[c].isin(["TODO", ""])).sum()) for c in ("sri", "sfdr", "pea", "encours_meur", "date_creation")}
        st.markdown(tr(f"""
- **Univers** : {len(fonds)} fonds et ETF, {int((u['type'] == 'action').sum())} actions européennes pour le satellite.
- **Champs non vérifiés** (laissés « TODO », jamais inventés) : SRI {todo['sri']}, SFDR {todo['sfdr']}, éligibilité PEA {todo['pea']},
  encours {todo['encours_meur']}, date de création {todo['date_creation']}. Un SRI manquant est **estimé** (signalé par *) à partir de la
  volatilité de la classe ; un critère non vérifié compte comme non rempli dans le classement.
- **Cours** : {calcul_marches.nom_mode('fr')}. Ils servent à l'information historique (simulation rétrospective, rejeu des crises),
  au critère du satellite et au suivi de la dérive, jamais au profil ni à la conformité.
- **Fiscalité 2026** : flat tax 31,4 % ; PEA 18,6 % après 5 ans ; assurance-vie 17,2 % de prélèvements sociaux (exclue de la hausse de CSG).
""", f"""
- **Universe**: {len(fonds)} funds and ETFs, {int((u['type'] == 'action').sum())} European stocks for the satellite.
- **Unverified fields** (left TODO, never invented): SRI {todo['sri']}, SFDR {todo['sfdr']}, PEA {todo['pea']}.
- **Prices**: {calcul_marches.nom_mode('en')}.
"""))
        st.dataframe(fonds[["nom", "sous_classe", "version", "ter", "sri", "sfdr", "pea", "encours_meur", "replication", "remarques"]],
                     hide_index=True, width="stretch", height=320)
    with o[3]:
        st.markdown(tr("""
- Hypothèses de marché à 10 ans d'une seule source (Amundi) ; corrélations simplifiées entre 10 classes d'actifs.
- Chocs de stress en ordres de grandeur ; fiscalité simplifiée (retrait unique à l'horizon) ; frais d'entrée de la SCPI (12 % TTC, note d'information Sofidy) amortis sur 10 ans.
- Le satellite actions sélectionne par la volatilité passée : critère simple et vérifiable, pas une analyse financière des sociétés.
- Préférence durable traduite par des versions ISR et des exclusions, pas par une notation ESG ; intensité carbone estimée par secteur.
- Dossiers stockés sur le disque du serveur de démonstration (effacés au redémarrage) ; en production, une base de données chiffrée.
- Projet pédagogique : l'outil ne constitue pas un conseil en investissement.
""", """
- 10-year assumptions from one source; simplified correlations; order-of-magnitude stress shocks; simplified tax.
- Satellite selection by past volatility; sustainability via SRI versions and exclusions, not an ESG rating.
- Student project: not investment advice.
"""))
