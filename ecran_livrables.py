"""
ecran_livrables.py — Documents du dossier : déclaration d'adéquation (PDF), fichier Excel, e-mail au client rédigé
par IA et relu par le conseiller, questionnaire vierge, export du dossier.
"""

from __future__ import annotations

import json
from email.message import EmailMessage
from urllib.parse import quote

import streamlit as st

import calcul_conformite
import commun
import livrables
from commun import tr


@st.cache_data(show_spinner=False, max_entries=16)
def _contexte(dossier_json: str, langue: str) -> dict:
    return livrables.contexte(json.loads(dossier_json), langue)


@st.cache_data(show_spinner=False, max_entries=16)
def _pdf(dossier_json: str, langue: str) -> bytes:
    return livrables.declaration_pdf(_contexte(dossier_json, langue))


@st.cache_data(show_spinner=False, max_entries=16)
def _xl(dossier_json: str, langue: str) -> tuple[bytes, str]:
    return livrables.excel(_contexte(dossier_json, langue))


def _generer_email():
    d = commun.dossier()
    ctx = _contexte(json.dumps(d, sort_keys=True, default=str), commun.L())
    objet, corps, source = livrables.email_client(ctx)
    st.session_state["mail_objet"], st.session_state["mail_corps"], st.session_state["mail_source"] = objet, corps, source


def page():
    d = commun.exiger_dossier()
    if d is None:
        return
    L = commun.L()
    dj = json.dumps(d, sort_keys=True, default=str)
    synth = calcul_conformite.synthese(commun.controles(d))
    commun.entete(tr("Documents", "Documents"), tr("Tout ce qu'il faut remettre au client et conserver au dossier.",
                                                    "Everything to hand to the client and keep on file."), f"{d['reference']} · {d.get('statut')}")
    if synth == "bloquant":
        st.warning(tr("Un contrôle bloquant subsiste : la déclaration est générée pour relecture mais ne peut pas être remise au client.",
                      "A blocking check remains: the statement is for review only."))
    c1, c2 = st.columns(2, gap="medium")
    with c1, st.container(border=True):
        st.markdown(f"#### {tr('Déclaration d’adéquation', 'Suitability statement')}")
        st.caption(tr("Situation, profil et ses justifications, recommandation, risques et frais, fil de décision complet, contrôles, "
                      "signatures du client et du conseiller, annexe des réponses.",
                      "Situation, profile, recommendation, risks and fees, full decision trail, checks, signatures, answers."))
        with st.spinner(tr("Préparation…", "Preparing…")):
            pdf = _pdf(dj, L)
        st.download_button(tr("Télécharger le PDF", "Download the PDF"), pdf, file_name=f"declaration_adequation_{d['reference']}.pdf",
                           mime="application/pdf", type="primary", width="stretch", key="dl_pdf")
    with c2, st.container(border=True):
        st.markdown(f"#### {tr('Fichier Excel du conseiller', 'Adviser Excel file')}")
        contenu, ext = _xl(dj, L)
        st.caption(tr("Synthèse, portefeuille (formules), fil de décision, projection (graphique), conformité, réponses. "
                      + ("Macro VBA de mise en forme incluse." if ext == "xlsm" else
                         "Ajoutez data/modele.xlsm (voir vba/LISEZMOI.md) pour inclure la macro VBA de mise en forme."),
                      "Summary, portfolio, trail, projection, checks, answers."))
        st.download_button(tr("Télécharger le fichier Excel", "Download the Excel file"), contenu, file_name=f"dossier_{d['reference']}.{ext}",
                           width="stretch", key="dl_xl")

    with st.container(border=True):
        st.markdown(f"#### {tr('E-mail au client', 'E-mail to the client')}")
        st.caption(tr("Rédigé par l'IA à partir des seuls chiffres calculés : tout nombre absent des données est refusé et remplacé par un modèle "
                      "sobre. Relisez et modifiez avant envoi.",
                      "Drafted by AI from computed figures only; any invented number is rejected. Review before sending."))
        st.button(tr("Rédiger l'e-mail", "Draft the e-mail"), on_click=_generer_email, key="btn_mail")
        if st.session_state.get("mail_corps"):
            st.text_input(tr("Objet", "Subject"), key="mail_objet")
            st.text_area(tr("Message", "Message"), key="mail_corps", height=300)
            st.caption(tr("Rédaction : ", "Written by: ") + st.session_state.get("mail_source", ""))
            m = EmailMessage()
            m["Subject"] = st.session_state["mail_objet"]
            m.set_content(st.session_state["mail_corps"])
            m.add_attachment(pdf, maintype="application", subtype="pdf", filename=f"declaration_adequation_{d['reference']}.pdf")
            b1, b2 = st.columns(2)
            b1.download_button(tr("Télécharger l'e-mail avec la déclaration jointe (.eml)", "Download e-mail with statement attached (.eml)"),
                               bytes(m), file_name=f"email_{d['reference']}.eml", width="stretch", key="dl_eml")
            b2.link_button(tr("Ouvrir dans ma messagerie", "Open in my mail app"),
                           f"mailto:?subject={quote(st.session_state['mail_objet'])}&body={quote(st.session_state['mail_corps'])}", width="stretch")

    c3, c4 = st.columns(2, gap="medium")
    with c3, st.container(border=True):
        st.markdown(f"#### {tr('Questionnaire vierge', 'Blank questionnaire')}")
        st.caption(tr("À faire remplir et signer par le client ; mêmes numéros que l'écran de saisie.", "For the client to fill and sign."))
        st.download_button(tr("Télécharger", "Download"), livrables.questionnaire_vierge(L), file_name="questionnaire_client.pdf",
                           mime="application/pdf", width="stretch", key="dl_vierge2")
    with c4, st.container(border=True):
        st.markdown(f"#### {tr('Sauvegarde du dossier', 'File backup')}")
        st.caption(tr("Le serveur de démonstration efface les dossiers au redémarrage : exportez le dossier (JSON) pour le réimporter.",
                      "The demo server wipes files on restart: export to re-import later."))
        st.download_button(tr("Exporter le dossier (JSON)", "Export the file (JSON)"), json.dumps(d, ensure_ascii=False, indent=1, default=str),
                           file_name=f"{d['reference']}.json", mime="application/json", width="stretch", key="dl_json")
    with st.expander(tr("Journal du dossier", "File log")):
        for e in reversed(d.get("journal", [])):
            st.markdown(f"<span class='ra-note'>{str(e['date']).replace('T', ' ')} · {e['auteur']}</span> — {e['evenement']}", unsafe_allow_html=True)
