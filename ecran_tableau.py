"""
ecran_tableau.py — Tableau de bord du conseiller : clients, encours conseillé, tâches du jour (déclarations à signer,
revues annuelles, alertes de rééquilibrage), ouverture et création des dossiers.
"""

from __future__ import annotations

import json
from datetime import date

import streamlit as st

import calcul_conformite
import calcul_marches
import calcul_portefeuille
import commun
import livrables
from commun import eur, pct, tr


@st.cache_data(show_spinner=False, max_entries=64)
def _derive(pf_json: str, depuis: str) -> tuple[dict, list]:
    pf = json.loads(pf_json)
    actuel = calcul_marches.poids_derives(pf, depuis)
    return actuel, calcul_portefeuille.alerte_reequilibrage(pf, actuel)


def etat_dossier(d: dict) -> dict:
    rec = d.get("recommandation") or {}
    res = {"revue": calcul_conformite.revue_due(d), "derive": [], "ecart_max": None}
    if d.get("statut") == "signé" and rec.get("portefeuille"):
        actuel, alerte = _derive(json.dumps(rec["portefeuille"], sort_keys=True), rec.get("date_signature") or rec["date"])
        cible = calcul_portefeuille.poids_par_classe(rec["portefeuille"])
        act = calcul_portefeuille.poids_par_classe(actuel)
        res["derive"] = alerte
        res["ecart_max"] = max(abs(act[c] - cible[c]) for c in cible)
    return res


def _importer():
    f = st.session_state.get("import_json")
    if f is None:
        return
    try:
        d = json.loads(f.getvalue().decode("utf-8"))
        assert str(d.get("reference", "")).startswith("RA-")
        calcul_conformite.enregistrer(d, "Dossier importé")
        st.session_state["_msg"] = tr(f"Dossier {d['reference']} importé.", f"File {d['reference']} imported.")
    except Exception:
        st.session_state["_msg"] = tr("Fichier non reconnu.", "File not recognised.")


def _reinitialiser():
    for d in calcul_conformite.lister():
        if d.get("demo"):
            calcul_conformite.supprimer(d["reference"])
    calcul_conformite.creer_demo(force=True)
    st.session_state["ref"] = None


def page():
    liste = calcul_conformite.lister()
    etats = {d["reference"]: etat_dossier(d) for d in liste}
    commun.entete(tr("Tableau de bord", "Dashboard"),
                  tr("Vos clients, leurs recommandations et ce qui demande votre attention.", "Your clients, their recommendations and what needs attention."),
                  commun.dt(date.today().isoformat()))
    signes = [d for d in liste if d.get("statut") == "signé"]
    a_signer = [d for d in liste if d.get("statut") == "à signer"]
    revues = [d for d in liste if etats[d["reference"]]["revue"]]
    alertes = [d for d in liste if etats[d["reference"]]["derive"]]
    commun.rangee_kpi([
        commun.kpi(tr("Clients", "Clients"), str(len(liste))),
        commun.kpi(tr("Encours conseillé", "Assets advised"), eur(sum(d["reponses"].get("montant") or 0 for d in signes)),
                   tr("déclarations signées", "signed statements")),
        commun.kpi(tr("À faire signer", "To be signed"), str(len(a_signer)), couleur=commun.AMBRE if a_signer else commun.TEXTE),
        commun.kpi(tr("Revues annuelles", "Annual reviews"), str(len(revues)), tr("dues sous un mois", "due within a month"),
                   couleur=commun.AMBRE if revues else commun.TEXTE),
        commun.kpi(tr("Rééquilibrages", "Rebalancing"), str(len(alertes)), tr("classe à plus de 5 pts de sa cible", "class over 5 pts off target"),
                   couleur=commun.ROUGE if alertes else commun.TEXTE),
    ])
    if st.session_state.get("_msg"):
        st.info(st.session_state.pop("_msg"))

    g, d_ = st.columns([2.2, 1], gap="large")
    with g:
        st.markdown(f"##### {tr('Clients', 'Clients')}")
        tete = "".join(f"<span>{x}</span>" for x in [tr("Référence", "Reference"), tr("Situation", "Situation"), tr("Statut", "Status"),
                                                      tr("Profil", "Profile"), tr("Montant", "Amount"), tr("Suivi", "Follow-up")])
        st.markdown(f"<div class='ra-client ra-client-t'>{tete}</div>", unsafe_allow_html=True)
        for dos in liste:
            e = etats[dos["reference"]]
            rec = dos.get("recommandation") or {}
            prof = f"{rec['profil']} · {commun.nom_profil(rec['profil'])}" if rec else "—"
            suivi = []
            if e["revue"]:
                suivi.append(f"<span class='ra-badge' style='background:#FFF4DB;color:#8A5A00'>{tr('Revue annuelle', 'Annual review')}</span>")
            if e["derive"]:
                suivi.append(f"<span class='ra-badge' style='background:#FDE8E8;color:#B3261E'>{tr('Rééquilibrer', 'Rebalance')}</span>")
            elif e["ecart_max"] is not None:
                suivi.append(f"<span class='ra-note'>{tr('écart max', 'max drift')} {pct(e['ecart_max'], 1)}</span>")
            c1, c2 = st.columns([12, 1.4], vertical_alignment="center")
            c1.markdown(f"<div class='ra-client'><b>{dos['reference']}</b><span class='ra-note'>{dos.get('note') or tr('Dossier en cours', 'Ongoing file')}</span>"
                        f"<span>{commun.badge_statut(dos.get('statut', 'brouillon'))}</span><span>{prof}</span>"
                        f"<span>{eur(dos['reponses'].get('montant'))}</span><span>{' '.join(suivi) or '—'}</span></div>", unsafe_allow_html=True)
            c2.button(tr("Ouvrir", "Open"), key=f"ouvrir_{dos['reference']}", on_click=commun.ouvrir, args=(dos["reference"],
                      "questionnaire" if dos.get("statut") == "brouillon" else "recommandation"), width="stretch")
    with d_:
        st.markdown(f"##### {tr('Actions', 'Actions')}")
        st.button(tr("＋ Nouveau dossier client", "＋ New client file"), type="primary", width="stretch", on_click=commun.nouveau, key="btn_nouveau")
        st.download_button(tr("Questionnaire vierge à faire signer (PDF)", "Blank questionnaire to sign (PDF)"),
                           livrables.questionnaire_vierge(commun.L()), file_name="questionnaire_client.pdf", mime="application/pdf",
                           width="stretch", key="dl_vierge")
        with st.container(border=True):
            st.markdown(f"**{tr('À faire', 'To do')}**")
            taches = ([tr(f"Faire signer la déclaration de {x['reference']}", f"Get {x['reference']}'s statement signed") for x in a_signer]
                      + [tr(f"Revue annuelle de {x['reference']}", f"Annual review for {x['reference']}") for x in revues]
                      + [tr(f"Rééquilibrer {x['reference']}", f"Rebalance {x['reference']}") for x in alertes]
                      + [tr(f"Compléter le questionnaire de {x['reference']}", f"Complete {x['reference']}'s questionnaire")
                         for x in liste if x.get("statut") == "brouillon"])
            st.markdown("\n".join(f"- {t}" for t in taches) or tr("Rien en attente.", "Nothing pending."))
        with st.expander(tr("Importer ou réinitialiser", "Import or reset")):
            st.file_uploader(tr("Importer un dossier (JSON)", "Import a file (JSON)"), type="json", key="import_json", on_change=_importer)
            st.button(tr("Recréer les clients de démonstration", "Recreate demo clients"), on_click=_reinitialiser, key="btn_reinit", width="stretch")
            st.caption(tr("Le serveur gratuit efface les dossiers à chaque redémarrage : exportez-les depuis la page Documents.",
                          "The free server wipes files on restart: export them from the Documents page."))
