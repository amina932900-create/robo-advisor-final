"""
ecran_questionnaire.py — Saisie du questionnaire signé par le client.

Le formulaire suit l'ordre et les numéros du questionnaire papier. À droite, le profil se construit en direct :
chaque réponse saisie met à jour les 4 notes et le profil. Une fois la déclaration émise, le questionnaire est figé ;
une revue (annuelle ou à la demande) ouvre une nouvelle version, l'ancienne reste dans l'historique.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

import calcul_conformite
import calcul_profil as qn
import commun
from commun import eur, tr
from textes import NOTES


def _d() -> dict:
    return commun.dossier()


def _maj(qid: str):
    d = _d()
    v = st.session_state[f"q_{qid}"]
    question = qn.PAR_ID.get(qid)
    if question and question["type"] in ("euros",) or qid == "montant":
        chiffres = "".join(c for c in str(v) if c.isdigit())
        v = int(chiffres) if chiffres else None
        st.session_state[f"q_{qid}"] = "" if v is None else f"{v:,}".replace(",", " ")
    if question and question["type"] == "multi":
        v = list(v or [])
    d["reponses"][qid] = v
    d["reponses"] = qn.nettoyer(d["reponses"])
    commun.sauver()


def _maj_date():
    v = st.session_state["q_date_signature"]
    _d()["date_signature_questionnaire"] = v.isoformat() if v else None
    commun.sauver()


def _aller_bloc(b: str):
    st.session_state["q_bloc_actif"] = b


def demarrer_revue():
    """Nouvelle version du questionnaire : la recommandation signée passe dans l'historique."""
    d = _d()
    if d.get("recommandation"):
        d.setdefault("historique", []).append(d["recommandation"])
    d.update(recommandation=None, statut="brouillon", date_signature_questionnaire=None, decisions={})
    for k in [k for k in st.session_state if str(k).startswith("q_")]:
        del st.session_state[k]
    commun.sauver("Revue ouverte : nouvelle version du questionnaire")


def _widget(q: dict, fige: bool):
    k = f"q_{q['id']}"
    val = _d()["reponses"].get(q["id"])
    L = commun.L()
    fmt = lambda v, q=q: qn.libelle(q["id"], v, L)
    st.markdown(f"<div style='margin-top:10px;font-size:14px'><span class='ra-ref'>Q{q['num']}</span> <b>{q[L]}</b></div>",
                unsafe_allow_html=True)
    commun_args = dict(key=k, on_change=_maj, args=(q["id"],), label_visibility="collapsed", disabled=fige)
    if q["type"] == "nombre":
        if k not in st.session_state:
            st.session_state[k] = val
        st.number_input(q["id"], min_value=q["min"], max_value=q["max"], step=1, placeholder=tr("à saisir", "enter"), **commun_args)
    elif q["type"] == "euros":
        if k not in st.session_state:
            st.session_state[k] = "" if val is None else f"{val:,}".replace(",", " ")
        st.text_input(q["id"], placeholder="0 €", **commun_args)
    elif q["type"] == "choix":
        valeurs = [o[0] for o in q["options"]]
        if k not in st.session_state:
            st.session_state[k] = val if val in valeurs else None
        st.radio(q["id"], valeurs, format_func=fmt, horizontal=len(valeurs) <= 5, **commun_args)
    elif q["type"] == "multi":
        valeurs = [o[0] for o in q["options"]]
        if k not in st.session_state:
            st.session_state[k] = [v for v in (val or []) if v in valeurs]
        st.pills(q["id"], valeurs, selection_mode="multi", format_func=fmt, **commun_args)
    else:
        if k not in st.session_state:
            st.session_state[k] = val
        st.segmented_control(q["id"], [True, False], format_func=fmt, **commun_args)


def _panneau(d: dict):
    """Le profil qui se construit en direct."""
    L = commun.L()
    r = d["reponses"]
    manq = qn.manquantes(r)
    prof = commun.profil(d)
    total = len([q for q in qn.QUESTIONS if qn.visible(q, r)])
    fait = total - len(manq)
    with st.container(border=True, key="panneau_profil"):
        st.markdown(f"<div class='ra-surtitre'>{tr('Profil en construction', 'Profile taking shape')}</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='display:flex;align-items:baseline;gap:12px;margin:6px 0 2px'><span class='ra-profil-num'>{prof['profil']}</span>"
                    f"<span style='font-size:20px;font-weight:650;color:#14213D'>{prof['nom']}</span></div>"
                    f"<div class='ra-note'>{tr('La plus petite des 4 notes', 'The lowest of the 4 scores')} · {fait}/{total} {tr('réponses', 'answers')}</div>",
                    unsafe_allow_html=True)
        st.progress(fait / total if total else 0)
        lignes = ""
        for k, v in prof["notes"].items():
            limite = k in prof["limitant"]
            dernier = prof["detail"][k][-1][0] if prof["detail"][k] else ""
            lignes += (f"<div style='margin:9px 0 0'><div style='display:flex;justify-content:space-between;font-size:13px'>"
                       f"<span style='font-weight:{650 if limite else 500};color:{'#B08D57' if limite else '#14213D'}'>{NOTES[L][k]}"
                       f"{' ◂' if limite else ''}</span><b>{v}/5</b></div>{commun.jauge(v)}"
                       f"<div class='ra-note' style='font-size:11.5px'>{dernier}</div></div>")
        st.markdown(lignes, unsafe_allow_html=True)
        if prof["alertes"]:
            st.markdown("<div style='margin-top:10px'>" + "".join(
                f"<div class='ra-note' style='color:#8A5A00;margin:3px 0'>⚠ {a}</div>" for a in prof["alertes"]) + "</div>", unsafe_allow_html=True)
        complet = commun.questionnaire_complet(d)
        if not complet:
            reste = [f"Q{q['num']}" for q in manq][:12]
            if not d.get("date_signature_questionnaire"):
                reste.insert(0, tr("date de signature", "signature date"))
            if not r.get("montant"):
                reste.insert(0, tr("montant", "amount"))
            st.caption(tr("Manque : ", "Missing: ") + ", ".join(reste) + ("…" if len(manq) > 12 else ""))
        st.button(tr("Voir la recommandation →", "See the recommendation →"), type="primary", width="stretch",
                  disabled=not complet, on_click=commun.aller, args=("recommandation",), key="btn_vers_reco")


def page():
    d = commun.exiger_dossier(questionnaire=False)
    if d is None:
        return
    L = commun.L()
    fige = d.get("statut") in ("à signer", "signé", "archivé")
    commun.entete(tr("Questionnaire signé", "Signed questionnaire"),
                  tr("Recopiez les réponses du questionnaire signé par le client : les numéros sont ceux du document papier.",
                     "Copy the answers from the client's signed questionnaire: numbers match the paper form."),
                  f"{d['reference']} · {d.get('statut')}")
    st.markdown(
        "<style>.st-key-panneau_profil {position:sticky; top:3.2rem;} "
        "[data-testid='stColumn']:has(.st-key-panneau_profil) {align-self:flex-start; position:sticky; top:3.2rem;}</style>",
        unsafe_allow_html=True)
    if fige:
        with st.container(border=True):
            c1, c2 = st.columns([4, 1.3], vertical_alignment="center")
            c1.markdown(tr("**Questionnaire figé** : une déclaration d'adéquation a été émise sur ces réponses. Pour les modifier "
                           "(revue annuelle, changement de situation), ouvrez une nouvelle version : l'actuelle reste dans l'historique.",
                           "**Questionnaire locked**: a statement was issued on these answers. Open a new version to change them."))
            c2.button(tr("Ouvrir une revue", "Start a review"), on_click=demarrer_revue, key="btn_revue", width="stretch")

    g, dr = st.columns([1.7, 1], gap="large")
    with g:
        with st.container(border=True):
            c1, c2, c3 = st.columns([1, 1, 1.4])
            c1.markdown(f"<div class='ra-note'>{tr('Référence client', 'Client reference')}</div><div style='font-size:20px;font-weight:650'>"
                        f"{d['reference']}</div>", unsafe_allow_html=True)
            if "q_date_signature" not in st.session_state:
                s = d.get("date_signature_questionnaire")
                st.session_state["q_date_signature"] = date.fromisoformat(s) if s else None
            c2.date_input(tr("Date de signature du questionnaire", "Questionnaire signature date"), key="q_date_signature",
                          on_change=_maj_date, max_value=date.today(), format="DD/MM/YYYY", disabled=fige)
            if "q_montant" not in st.session_state:
                m = d["reponses"].get("montant")
                st.session_state["q_montant"] = "" if m is None else f"{m:,}".replace(",", " ")
            c3.text_input(tr("Montant à investir (€)", "Amount to invest (€)"), key="q_montant", on_change=_maj, args=("montant",),
                          placeholder="300 000", disabled=fige)
            m = d["reponses"].get("montant")
            if m and not (qn.MONTANT_MIN <= m <= qn.MONTANT_MAX):
                st.warning(tr(f"Le service est conçu pour 100 000 € à 1 000 000 € ({eur(m)} saisi) : au-delà, orienter vers la banque privée.",
                              f"Designed for €100,000 to €1,000,000 ({eur(m)} entered)."))
        r = d["reponses"]
        blocs = list(qn.BLOCS)
        manquantes = qn.manquantes(r)
        reste = {b: len([q for q in manquantes if q["bloc"] == b]) for b in blocs}
        # Sélecteur de bloc à libellés FIXES (des libellés qui changent feraient revenir au bloc A à chaque réponse)
        noms_blocs = {b: f"{b}. {qn.BLOCS[b][L]}" for b in blocs}
        st.session_state.setdefault("q_bloc_actif", "A")
        bloc = st.segmented_control("bloc", blocs, key="q_bloc_actif", format_func=noms_blocs.get,
                                    label_visibility="collapsed") or st.session_state.get("_dernier_bloc", "A")
        st.session_state["_dernier_bloc"] = bloc
        st.markdown("<div style='display:flex;gap:14px;flex-wrap:wrap;margin:-4px 0 6px' class='ra-note'>" + "".join(
            f"<span style='color:{'#1E7F4F' if reste[b] == 0 else '#8A5A00'}'>{b} {'✓ complet' if reste[b] == 0 else f'· {reste[b]} à saisir'}</span>"
            if L == "fr" else
            f"<span style='color:{'#1E7F4F' if reste[b] == 0 else '#8A5A00'}'>{b} {'✓ done' if reste[b] == 0 else f'· {reste[b]} to fill'}</span>"
            for b in blocs) + "</div>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown(f"#### {noms_blocs[bloc]}")
            for q in qn.QUESTIONS:
                if q["bloc"] == bloc and qn.visible(q, r):
                    _widget(q, fige)
            i = blocs.index(bloc)
            c1, _, c2 = st.columns([1, 2, 1])
            if i > 0:
                c1.button("← " + noms_blocs[blocs[i - 1]], key="btn_bloc_prec", on_click=_aller_bloc, args=(blocs[i - 1],), width="stretch")
            if i < len(blocs) - 1:
                c2.button(noms_blocs[blocs[i + 1]] + " →", key="btn_bloc_suiv", type="primary", on_click=_aller_bloc,
                          args=(blocs[i + 1],), width="stretch")
    with dr:
        _panneau(d)
