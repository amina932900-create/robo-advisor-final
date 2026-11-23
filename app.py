"""
app.py — Point d'entrée. Lancer : streamlit run app.py

Outil d'aide à la décision du CONSEILLER en gestion de patrimoine :
le client remplit et signe le questionnaire ; le conseiller le saisit, obtient une recommandation justifiée étape
par étape (fil de décision), l'ajuste en motivant chaque dérogation, puis édite les documents à faire signer.

Fichiers :
- app.py, commun.py, ecran_*.py      interface (Streamlit)
- calcul_*.py, donnees.py            calculs, sans Streamlit, testés par pytest
- livrables.py                       PDF, Excel, e-mail rédigé par IA, questionnaire vierge
- telecharger_prix.py                met à jour data/prix_snapshot.csv
"""

from __future__ import annotations

import streamlit as st

import commun
import donnees
import ecran_analyses
import ecran_livrables
import ecran_methodologie
import ecran_questionnaire
import ecran_recommandation
import ecran_tableau
from commun import tr

VERSION = "2026-11-23 b · univers sourcé, IA auto"   # à changer à chaque livraison : permet de vérifier la version en ligne

st.set_page_config(page_title="Robo-advisor patrimonial", page_icon="◆", layout="wide", initial_sidebar_state="expanded")
commun.initialiser()

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Playfair+Display:wght@600;700&display=swap');
html, body, [class*="css"], .stMarkdown, button, input, label, textarea {font-family:'Inter', sans-serif;}
.block-container, [data-testid="stMainBlockContainer"] {padding:2.6rem 2rem 3rem; max-width:1500px;}
[data-testid="stSidebar"] {background:#14213D;}
[data-testid="stSidebar"] * {color:#E8E4DA !important;}
[data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"] {background:rgba(176,141,87,.22);}
[data-testid="stSidebar"] button {background:transparent; border:1px solid rgba(232,228,218,.35);}
.ra-marque {font-family:'Playfair Display', serif; font-size:21px; font-weight:700; letter-spacing:.2px; color:#F3EEE3 !important;}
.ra-marque-s {font-size:11px; letter-spacing:1.6px; text-transform:uppercase; color:#B08D57 !important; margin-bottom:10px;}
.ra-surtitre {font-size:11.5px; letter-spacing:1.6px; text-transform:uppercase; color:#B08D57; font-weight:600;}
.ra-titre {font-family:'Playfair Display', serif; font-size:31px; font-weight:700; color:#14213D; letter-spacing:-.2px; margin:0 0 2px;}
.ra-sous-titre {font-size:14px; color:#6B7785; margin:0 0 18px;}
.ra-kpis {display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin:4px 0 14px;}
.ra-kpi {background:#FBFAF7; border:1px solid #E8E2D6; border-radius:12px; padding:12px 14px;}
.ra-kpi-l {font-size:11.5px; color:#6B7785; text-transform:uppercase; letter-spacing:.6px;}
.ra-kpi-v {font-size:22px; font-weight:650; line-height:1.25; margin-top:3px;}
.ra-kpi-a {font-size:11.5px; color:#6B7785; margin-top:2px;}
.ra-carte {border:1px solid #E8E2D6; border-radius:12px; padding:14px 16px; background:#fff; margin-bottom:10px;}
.ra-badge {font-size:11.5px; font-weight:600; padding:3px 9px; border-radius:20px; white-space:nowrap;}
.ra-note {font-size:12px; color:#6B7785;}
.ra-cran {display:inline-block; width:22px; height:7px; border-radius:4px; margin-right:3px; background:#E3E0D8;}
.ra-cran.plein {background:#14213D; animation:ra-pousse .45s ease-out both;}
@keyframes ra-pousse {from {transform:scaleX(0); transform-origin:left;} to {transform:scaleX(1);}}
.ra-barre {display:flex; border-radius:6px; overflow:hidden; margin:6px 0;}
.ra-barre div {animation:ra-pousse .6s ease-out both;}
.ra-legende {display:flex; flex-wrap:wrap; gap:4px 14px; font-size:12px; color:#4A5560;}
.ra-ref {display:inline-block; font-size:10.5px; font-weight:600; padding:1px 6px; border-radius:6px; background:#F3EEE3;
         color:#7A5C2E; border:1px solid #E2D5BD; cursor:help; margin:0 1px;}
.ra-fil {border-left:2px solid #E2D5BD; margin-left:12px; padding-left:0;}
.ra-fil-etape {margin:0 0 6px 0; position:relative;}
.ra-fil-etape summary {list-style:none; cursor:pointer; display:flex; gap:12px; align-items:baseline; padding:8px 10px 8px 0;}
.ra-fil-etape summary::-webkit-details-marker {display:none;}
.ra-fil-n {flex:none; width:26px; height:26px; border-radius:50%; background:#14213D; color:#F3EEE3; font-size:12px; font-weight:700;
           display:flex; align-items:center; justify-content:center; margin-left:-14px;}
.ra-fil-t {font-weight:650; color:#14213D; min-width:210px;}
.ra-fil-r {color:#4A5560; font-size:13.5px;}
.ra-fil-etape[open] .ra-fil-n {background:#B08D57;}
.ra-fil-corps {margin:0 0 10px 28px; background:#FBFAF7; border:1px solid #EFE9DD; border-radius:10px; padding:10px 14px; font-size:13px;}
.ra-fil-regle {color:#14213D; font-weight:500; margin-bottom:4px;}
.ra-fil-corps ul, .ra-pourquoi {margin:4px 0 4px 16px; padding:0;} .ra-fil-corps li, .ra-pourquoi li {margin:3px 0; color:#3A4553;}
.ra-fil-src {color:#8A8F98; font-size:11.5px; margin-top:4px;}
.ra-profil-num {font-family:'Playfair Display', serif; font-size:52px; font-weight:700; color:#14213D; line-height:1;}
.ra-client {display:grid; grid-template-columns:1.1fr 1.4fr 1fr 1fr 1fr 1.3fr; gap:10px; align-items:center; padding:10px 6px;
            border-bottom:1px solid #EFE9DD; font-size:13.5px;}
.ra-client-t {font-size:11px; text-transform:uppercase; letter-spacing:.6px; color:#8A8F98; border-bottom:1px solid #E2D5BD;}
.st-key-lang_fr button, .st-key-lang_en button {min-height:28px; padding:0 8px;}
</style>""", unsafe_allow_html=True)

P = {
    "tableau": st.Page(ecran_tableau.page, title=tr("Tableau de bord", "Dashboard"), icon=":material/dashboard:", url_path="tableau", default=True),
    "questionnaire": st.Page(ecran_questionnaire.page, title=tr("Questionnaire signé", "Signed questionnaire"), icon=":material/edit_document:",
                             url_path="questionnaire"),
    "recommandation": st.Page(ecran_recommandation.page, title=tr("Recommandation", "Recommendation"), icon=":material/account_tree:",
                              url_path="recommandation"),
    "analyses": st.Page(ecran_analyses.page, title=tr("Projection et risques", "Projection & risk"), icon=":material/monitoring:",
                        url_path="analyses"),
    "livrables": st.Page(ecran_livrables.page, title=tr("Documents", "Documents"), icon=":material/description:", url_path="documents"),
    "methodologie": st.Page(ecran_methodologie.page, title=tr("Méthodologie", "Methodology"), icon=":material/science:", url_path="methodologie"),
}
commun.PAGES.update(P)
d = commun.dossier()
groupe = tr(f"Dossier {d['reference']}", f"File {d['reference']}") if d else tr("Dossier client", "Client file")
nav = st.navigation({tr("Cabinet", "Practice"): [P["tableau"], P["methodologie"]],
                     groupe: [P["questionnaire"], P["recommandation"], P["analyses"], P["livrables"]]})

cible = st.session_state.pop("_cible", None)
if cible in P:
    st.switch_page(P[cible])

with st.sidebar:
    st.markdown("<div class='ra-marque'>Robo-advisor</div><div class='ra-marque-s'>" + tr("Espace conseiller", "Adviser workspace")
                + "</div>", unsafe_allow_html=True)
    c1, c2, _ = st.columns([1, 1, 2])
    c1.button("FR", key="lang_fr", on_click=commun.changer_langue, args=("fr",))
    c2.button("EN", key="lang_en", on_click=commun.changer_langue, args=("en",))
    import calcul_marches
    st.caption(("🧪 " if calcul_marches.mode() == "demo" else "💾 ") + tr("Cours : ", "Prices: ") + calcul_marches.nom_mode(commun.L()))
    _u = donnees.univers()
    st.caption(f"Version {VERSION} · " + tr(f"{int((_u == 'TODO').sum().sum())} donnée(s) TODO", f"{int((_u == 'TODO').sum().sum())} TODO field(s)"))
    st.caption(tr("Projet pédagogique de M2 Banque-Finance : outil simulé, pas un conseil en investissement réel.",
                  "Master's student project: simulated tool, not real investment advice."))

nav.run()
