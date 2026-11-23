"""
commun.py — État de session, dossier client courant, calculs mis en cache et composants visuels partagés.

L'utilisateur de l'outil est le CONSEILLER. Un « dossier » = un client (référence pseudonyme RA-…), son
questionnaire signé, les décisions du conseiller (dérogations motivées) et la recommandation émise.
"""

from __future__ import annotations

import json
from datetime import date

import streamlit as st

import calcul_analyses
import calcul_conformite
import calcul_portefeuille
import calcul_profil
from textes import CLASSES, NOMS_ENVELOPPES, date_txt, eur_txt, nombre_txt, pct_txt

PAGES: dict = {}
BLEU, OR, TEXTE, DISCRET, VERT, ROUGE, AMBRE = "#14213D", "#B08D57", "#1B2A41", "#6B7785", "#1E7F4F", "#B3261E", "#8A5A00"
COULEURS_CLASSES = {"actions": "#14213D", "obligations": "#3E6E8E", "monetaire": "#9DB4C0", "diversifiants": "#B08D57",
                    "scpi": "#7A6C5D", "actif": "#C9B79C"}


def initialiser():
    s = st.session_state
    s.setdefault("langue", "fr")
    s.setdefault("ref", None)
    calcul_conformite.creer_demo()


def changer_langue(langue: str):
    """Change la langue ; les widgets (libellés traduits) sont recréés à partir du dossier."""
    st.session_state["langue"] = langue
    for k in [k for k in st.session_state if str(k).startswith(("w_", "q_", "a_"))]:
        del st.session_state[k]


def L() -> str:
    return st.session_state.get("langue", "fr")


def tr(fr: str, en: str) -> str:
    return en if L() == "en" else fr


def pct(x, d=1, signe=False):
    return pct_txt(x, d, L(), signe)


def eur(x, signe=False):
    return eur_txt(x, L(), signe)


def nb(x, d=2):
    return nombre_txt(x, d, L())


def dt(iso):
    return date_txt(iso, L())


def aller(cible: str):
    """Callback de bouton : la page change au début de l'exécution suivante (voir app.py)."""
    st.session_state["_cible"] = cible


# ---------------------------------------------------------------------------------------------------
# Dossier courant
# ---------------------------------------------------------------------------------------------------
def dossier() -> dict | None:
    ref = st.session_state.get("ref")
    if not ref:
        return None
    d = st.session_state.get("_dossier")
    if not d or d.get("reference") != ref:
        d = calcul_conformite.charger(ref)
        st.session_state["_dossier"] = d
    return d


def ouvrir(ref: str, page: str = "recommandation"):
    st.session_state["ref"] = ref
    st.session_state.pop("_dossier", None)
    for k in [k for k in st.session_state if str(k).startswith(("w_", "q_"))]:
        del st.session_state[k]
    aller(page)


def nouveau():
    d = calcul_conformite.nouveau_dossier()
    calcul_conformite.enregistrer(d)
    ouvrir(d["reference"], "questionnaire")


def sauver(evenement: str | None = None):
    d = dossier()
    if d:
        calcul_conformite.enregistrer(d, evenement)


def nom_profil(p: int) -> str:
    return calcul_profil.nom_profil(p, L())


def nom_env(env: str | None) -> str:
    return NOMS_ENVELOPPES[L()].get(env, env or "—")


def nom_classe(c: str) -> str:
    return CLASSES[L()].get(c, c)


# ---------------------------------------------------------------------------------------------------
# Calculs mis en cache (clé = contenu JSON des arguments)
# ---------------------------------------------------------------------------------------------------
@st.cache_data(show_spinner=False, max_entries=256)
def _profil(rep_json: str, langue: str) -> dict:
    return calcul_profil.calculer_profil(json.loads(rep_json), langue)


@st.cache_data(show_spinner=False, max_entries=256)
def _reco(rep_json: str, dec_json: str, meta_json: str, langue: str) -> dict:
    r, d, meta = json.loads(rep_json), json.loads(dec_json), json.loads(meta_json)
    prof = calcul_profil.calculer_profil(r, langue)
    return calcul_portefeuille.recommander(r, prof, d.get("profil_retenu"), d.get("ajustements"), {**meta, **d}, langue)


def _j(x) -> str:
    return json.dumps(x, sort_keys=True, default=str)


def profil(d: dict | None = None) -> dict:
    d = d or dossier()
    return _profil(_j(d["reponses"]), L())


def meta(d: dict) -> dict:
    return {"date_signature": d.get("date_signature_questionnaire"), "reference": d["reference"]}


def reco(d: dict | None = None, decisions: dict | None = None) -> dict:
    d = d or dossier()
    return _reco(_j(d["reponses"]), _j(decisions if decisions is not None else d.get("decisions", {})), _j(meta(d)), L())


def controles(d: dict | None = None) -> list[dict]:
    d = d or dossier()
    return calcul_conformite.controler(d["reponses"], profil(d), reco(d), d.get("decisions", {}),
                                       d.get("date_signature_questionnaire"), L())


@st.cache_data(show_spinner=False, max_entries=64)
def simuler(pf_json: str, env: str, montant: float, versement: float, retrait: float, ans: int, cible: float) -> dict:
    return calcul_analyses.simuler(json.loads(pf_json), env, montant, versement, retrait, ans, cible)


@st.cache_data(show_spinner=False, max_entries=64)
def indicateurs(pf_json: str) -> dict:
    import calcul_marches
    return calcul_marches.indicateurs(json.loads(pf_json))


def horizon_ans(r: dict) -> int:
    return {"<2": 2, "2-5": 5, "5-8": 8, ">8": 15}.get(r.get("horizon"), 10)


def questionnaire_complet(d: dict) -> bool:
    return bool(d.get("date_signature_questionnaire")) and bool(d["reponses"].get("montant")) and not calcul_profil.manquantes(d["reponses"])


# ---------------------------------------------------------------------------------------------------
# Composants visuels
# ---------------------------------------------------------------------------------------------------
def entete(titre: str, sous_titre: str = "", sur_titre: str = ""):
    st.markdown((f"<div class='ra-surtitre'>{sur_titre}</div>" if sur_titre else "") + f"<div class='ra-titre'>{titre}</div>"
                + (f"<div class='ra-sous-titre'>{sous_titre}</div>" if sous_titre else ""), unsafe_allow_html=True)


def kpi(label: str, valeur: str, aide: str = "", couleur: str = TEXTE) -> str:
    return (f"<div class='ra-kpi'><div class='ra-kpi-l'>{label}</div><div class='ra-kpi-v' style='color:{couleur}'>{valeur}</div>"
            + (f"<div class='ra-kpi-a'>{aide}</div>" if aide else "") + "</div>")


def rangee_kpi(elements: list[str]):
    st.markdown("<div class='ra-kpis'>" + "".join(elements) + "</div>", unsafe_allow_html=True)


def badge(statut: str) -> str:
    c = {"ok": ("#E6F4EA", VERT, tr("Conforme", "Compliant")), "attention": ("#FFF4DB", AMBRE, tr("À documenter", "To document")),
         "bloquant": ("#FDE8E8", ROUGE, tr("Bloquant", "Blocking"))}[statut]
    return f"<span class='ra-badge' style='background:{c[0]};color:{c[1]}'>{c[2]}</span>"


def badge_statut(statut: str) -> str:
    c = {"brouillon": ("#EEF1F5", DISCRET), "à signer": ("#FFF4DB", AMBRE), "signé": ("#E6F4EA", VERT), "archivé": ("#EEF1F5", DISCRET)}
    bg, fg = c.get(statut, ("#EEF1F5", DISCRET))
    txt = statut if L() == "fr" else calcul_conformite.STATUTS_EN.get(statut, statut)
    return f"<span class='ra-badge' style='background:{bg};color:{fg}'>{txt}</span>"


def jauge(v: int, n: int = 5) -> str:
    return "".join(f"<span class='ra-cran {'plein' if i < v else ''}'></span>" for i in range(n))


def barre_classes(classes: dict, hauteur: int = 12) -> str:
    seg = "".join(f"<div style='width:{w * 100:.2f}%;background:{COULEURS_CLASSES[c]}'></div>" for c, w in classes.items() if w > 1e-6)
    leg = "".join(f"<span><span style='color:{COULEURS_CLASSES[c]}'>●</span> {nom_classe(c)} {pct(w, 0)}</span>"
                  for c, w in classes.items() if w > 1e-6)
    return (f"<div class='ra-barre' style='height:{hauteur}px'>{seg}</div><div class='ra-legende'>{leg}</div>")


def refs_html(refs: list[int], reponses: dict) -> str:
    """Badges « Q12 » avec, au survol, la question et la réponse signée du client."""
    out = []
    for n in refs:
        q = next(x for x in calcul_profil.QUESTIONS if x["num"] == n)
        rep = calcul_profil.libelle(q["id"], reponses.get(q["id"]), L()) if q["id"] in reponses else "—"
        titre = f"Q{n} · {q[L()]} → {rep}".replace("'", "’")
        out.append(f"<span class='ra-ref' title='{titre}'>Q{n}</span>")
    return " ".join(out)


def fil_html(fil: list[dict], reponses: dict, ouvertes: tuple[int, ...] = ()) -> str:
    """Le fil de décision en frise verticale ; chaque étape se déplie ; chaque « Q.. » montre la réponse signée."""
    html = "<div class='ra-fil'>"
    for e in fil:
        dets = "".join(f"<li>{t} {refs_html(r, reponses)}</li>" for t, r in e["details"])
        src = f"<div class='ra-fil-src'>{tr('Source', 'Source')} : {e['source']}</div>" if e.get("source") else ""
        html += (f"<details class='ra-fil-etape' {'open' if e['n'] in ouvertes else ''}><summary><span class='ra-fil-n'>{e['n']}</span>"
                 f"<span class='ra-fil-t'>{e['titre']}</span><span class='ra-fil-r'>{e['resultat']}</span></summary>"
                 f"<div class='ra-fil-corps'><div class='ra-fil-regle'>{tr('Règle', 'Rule')} : {e['regle']}</div><ul>{dets}</ul>{src}</div></details>")
    return html + "</div>"


def etape_fil(fil: list[dict], n: int, reponses: dict):
    """Contenu d'une étape du fil, pour les fenêtres « Pourquoi ? »."""
    e = fil[n - 1]
    st.markdown(f"**{e['n']}. {e['titre']}** — {e['resultat']}")
    st.caption(f"{tr('Règle', 'Rule')} : {e['regle']}")
    st.markdown("<ul class='ra-pourquoi'>" + "".join(f"<li>{t} {refs_html(r, reponses)}</li>" for t, r in e["details"]) + "</ul>",
                unsafe_allow_html=True)
    if e.get("source"):
        st.caption(f"{tr('Source', 'Source')} : {e['source']}")


def exiger_dossier(questionnaire: bool = True) -> dict | None:
    d = dossier()
    if d is None:
        with st.container(border=True):
            st.markdown(f"#### {tr('Aucun dossier ouvert', 'No client file open')}")
            st.write(tr("Ouvrez un dossier depuis le tableau de bord ou créez-en un.", "Open a file from the dashboard or create one."))
            c1, c2, _ = st.columns([1, 1, 3])
            c1.button(tr("Tableau de bord", "Dashboard"), on_click=aller, args=("tableau",), key="ex_tab")
            c2.button(tr("Nouveau dossier", "New file"), type="primary", on_click=nouveau, key="ex_nouv")
        return None
    if questionnaire and not questionnaire_complet(d):
        with st.container(border=True):
            st.markdown(f"#### {tr('Questionnaire à compléter', 'Questionnaire to complete')}")
            st.write(tr("La recommandation s'établit à partir du questionnaire signé : saisissez toutes les réponses et la date de signature.",
                        "The recommendation needs the full signed questionnaire and its signature date."))
            st.button(tr("Compléter le questionnaire", "Complete the questionnaire"), type="primary", on_click=aller,
                      args=("questionnaire",), key="ex_q")
        return None
    return d
