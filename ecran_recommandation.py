"""
ecran_recommandation.py — La recommandation, son fil de décision et les ajustements du conseiller.

- Chaque chiffre clé a son « Pourquoi ? » : l'étape du fil de décision qui l'explique, jusqu'aux réponses signées.
- Le conseiller peut abaisser le profil, déplacer actions et obligations de ±10 points ou choisir une autre enveloppe :
  tout est recalculé à l'instant ; un réglage trop risqué est refusé avec sa raison ; chaque dérogation exige un motif.
- Rééquilibrage : poids actuels (dérive depuis la signature) comparés à la cible, ordres en euros par classe.
"""

from __future__ import annotations

import json
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import calcul_analyses
import calcul_conformite
import calcul_marches
import calcul_portefeuille as cpf
import commun
import donnees
from commun import eur, pct, tr
from textes import NOMS_COURTS


def _decisions_widgets(d: dict, reco_base: dict) -> dict:
    """Lit les réglages du conseiller (widgets) et renvoie les décisions candidates."""
    dec = dict(d.get("decisions") or {})
    s = st.session_state
    dec["profil_retenu"] = s.get("w_profil", dec.get("profil_retenu") or reco_base["profil_calcule"])
    dec["ajustements"] = {"actions": s.get("w_actions", (dec.get("ajustements") or {}).get("actions", 0) * 100) / 100,
                          "obligations": s.get("w_oblig", (dec.get("ajustements") or {}).get("obligations", 0) * 100) / 100}
    env = s.get("w_env", dec.get("enveloppe_forcee") or "auto")
    dec["enveloppe_forcee"] = None if env == "auto" else env
    for k in ("motif_profil", "motif_ajustement", "motif_enveloppe"):
        dec[k] = s.get(f"w_{k}", dec.get(k, ""))
    if dec["profil_retenu"] == reco_base["profil_calcule"]:
        dec["profil_retenu"] = None
    return dec


def _appliquer():
    """Callback des réglages : enregistre si le réglage est accepté, sinon garde l'ancien et explique."""
    d = commun.dossier()
    base = commun.reco(d, {})
    dec = _decisions_widgets(d, base)
    ok, msg, _ = cpf.verifier_ajustement(d["reponses"], commun.profil(d), dec.get("profil_retenu"), dec["ajustements"], {**commun.meta(d), **dec})
    if ok:
        d["decisions"] = dec
        st.session_state["_refus"] = None
        commun.sauver()
    else:
        st.session_state["_refus"] = msg
        old = d.get("decisions") or {}
        st.session_state["w_actions"] = int(round((old.get("ajustements") or {}).get("actions", 0) * 100))
        st.session_state["w_oblig"] = int(round((old.get("ajustements") or {}).get("obligations", 0) * 100))


def _reinitialiser():
    d = commun.dossier()
    d["decisions"] = {}
    for k in [k for k in st.session_state if str(k).startswith("w_")]:
        del st.session_state[k]
    commun.sauver("Réglages du conseiller annulés")


def _emettre():
    d = commun.dossier()
    calcul_conformite.figer_recommandation(d, commun.reco(d), commun.controles(d))
    commun.sauver("Déclaration d'adéquation émise, à faire signer")


def _annuler_emission():
    d = commun.dossier()
    d["recommandation"], d["statut"] = None, "brouillon"
    commun.sauver("Émission annulée")


def _signer():
    d = commun.dossier()
    v = st.session_state.get("w_date_signature") or date.today()
    d["recommandation"]["date_signature"] = v.isoformat()
    d["statut"] = "signé"
    commun.sauver(f"Déclaration signée par le client le {v.isoformat()}")


def _pourquoi(label: str, reco: dict, etapes: list[int], d: dict, cle: str):
    with st.popover(label, width="stretch"):
        for n in etapes:
            commun.etape_fil(reco["fil"], n, d["reponses"])


def _reglages(d: dict, reco: dict, fige: bool):
    s = st.session_state
    dec = d.get("decisions") or {}
    p_calc = reco["profil_calcule"]
    s.setdefault("w_profil", dec.get("profil_retenu") or p_calc)
    s.setdefault("w_actions", int(round((dec.get("ajustements") or {}).get("actions", 0) * 100)))
    s.setdefault("w_oblig", int(round((dec.get("ajustements") or {}).get("obligations", 0) * 100)))
    s.setdefault("w_env", dec.get("enveloppe_forcee") or "auto")
    for k in ("motif_profil", "motif_ajustement", "motif_enveloppe"):
        s.setdefault(f"w_{k}", dec.get(k, ""))
    modifie = reco["profil"] < p_calc or s["w_actions"] or s["w_oblig"] or s["w_env"] != "auto"
    with st.expander(tr("Ajuster la recommandation (conseiller)", "Adjust the recommendation (adviser)"), expanded=bool(modifie)):
        if fige:
            st.caption(tr("Déclaration émise : réglages verrouillés. Annulez l'émission ou ouvrez une revue pour les modifier.",
                          "Statement issued: settings locked."))
        c1, c2, c3 = st.columns([1.2, 1.4, 1.1], gap="medium")
        with c1:
            st.markdown(f"**{tr('Profil retenu', 'Chosen profile')}**")
            st.segmented_control("profil", list(range(1, p_calc + 1)), key="w_profil", on_change=_appliquer, disabled=fige,
                                 format_func=lambda n: f"{n}", label_visibility="collapsed")
            st.caption(tr(f"Calculé : {p_calc}. Il peut être abaissé, jamais relevé (MiFID II).",
                          f"Computed: {p_calc}. May be lowered, never raised."))
            if reco["profil"] < p_calc:
                st.text_input(tr("Motif (obligatoire)", "Reason (required)"), key="w_motif_profil", on_change=_appliquer, disabled=fige)
        with c2:
            st.markdown(f"**{tr('Actions et obligations (points)', 'Equities and bonds (points)')}**")
            st.slider(tr("Actions", "Equities"), -10, 10, key="w_actions", on_change=_appliquer, disabled=fige, format="%+d")
            st.slider(tr("Obligations", "Bonds"), -10, 10, key="w_oblig", on_change=_appliquer, disabled=fige, format="%+d")
            st.caption(tr("Le monétaire compense. Refusé si le risque dépasse le maximum du profil.",
                          "Money market offsets. Refused if risk exceeds the profile maximum."))
            if s["w_actions"] or s["w_oblig"]:
                st.text_input(tr("Motif (obligatoire)", "Reason (required)"), key="w_motif_ajustement", on_change=_appliquer, disabled=fige)
        with c3:
            st.markdown(f"**{tr('Enveloppe', 'Wrapper')}**")
            noms_env = {e: (tr("Selon la règle", "As per the rule") if e == "auto" else commun.nom_env(e)) for e in ["auto", "assurance-vie", "PEA", "CTO"]}
            st.selectbox("env", list(noms_env), key="w_env", on_change=_appliquer, disabled=fige,
                         label_visibility="collapsed", format_func=noms_env.get)
            st.caption(tr("Règle : ", "Rule: ") + commun.nom_env(reco["enveloppe_auto"]))
            if s["w_env"] != "auto":
                st.text_input(tr("Motif (obligatoire)", "Reason (required)"), key="w_motif_enveloppe", on_change=_appliquer, disabled=fige)
            st.button(tr("Revenir à la recommandation calculée", "Back to computed recommendation"), on_click=_reinitialiser,
                      disabled=fige, key="btn_reinit_reglages", width="stretch")
        if st.session_state.get("_refus"):
            st.error(tr("Réglage refusé : ", "Adjustment refused: ") + st.session_state["_refus"])


def _lignes(d: dict, reco: dict):
    u = donnees.univers()
    pf, montant = reco["portefeuille"], d["reponses"]["montant"]
    env = cpf.repartition_enveloppes(pf, reco["enveloppe"], montant)
    cols = st.columns(2, gap="medium")
    classes = [c for c in cpf.CLASSES if reco["classes"].get(c, 0) > 1e-6]
    for k, c in enumerate(classes):
        with cols[k % 2]:
            with st.container(border=True):
                st.markdown(f"<div style='display:flex;justify-content:space-between'><b><span style='color:{commun.COULEURS_CLASSES[c]}'>●</span> "
                            f"{commun.nom_classe(c)}</b><span>{pct(reco['classes'][c], 1)} · {eur(reco['classes'][c] * montant)}</span></div>",
                            unsafe_allow_html=True)
                for isin, w in sorted(((i, w) for i, w in pf.items() if u.loc[i, "classe"] == c), key=lambda x: -x[1]):
                    l, info = u.loc[isin], reco["lignes"][isin]
                    sri, estime = donnees.sri(isin)
                    a, b, cc = st.columns([5, 1.4, 0.8], vertical_alignment="center")
                    sous = (donnees.secteur_pays(isin, commun.L()) if l["type"] == "action" else isin) + f" · {NOMS_COURTS[commun.L()].get(env[isin], env[isin])}"
                    a.markdown(f"<div style='font-size:13.5px;font-weight:600;color:#14213D;line-height:1.25'>{l['nom']}</div>"
                               f"<div class='ra-note'>{sous} · SRI {sri}{'*' if estime else ''}</div>", unsafe_allow_html=True)
                    b.markdown(f"<div style='text-align:right;font-size:13.5px'><b>{pct(w, 1)}</b><br><span class='ra-note'>{eur(w * montant)}</span></div>",
                               unsafe_allow_html=True)
                    with cc.popover("?", help=tr("Pourquoi cette ligne ?", "Why this holding?")):
                        st.markdown(f"**{l['nom']}**")
                        st.write(info["raison"].capitalize())
                        if l["description"]:
                            st.caption(l["description"])
                        alt = info.get("alternatives") or []
                        if len(alt) > 1:
                            st.markdown(f"**{tr('Candidats de la poche', 'Candidates in the sleeve')}** · {info['texte_poche']}")
                            oui = lambda v: "–" if v == "n/a" else ("✓" if v is True else ("✗" if v is False else "?"))
                            st.dataframe(pd.DataFrame([{
                                tr("Support", "Product"): ("▶ " if x["isin"] == isin else "") + x["nom"][:42],
                                tr("Frais", "Fees"): pct(x["ter"], 2), tr("Encours ≥ 500 M€", "AuM ≥ €500m"): oui(x["criteres"]["encours"]),
                                tr("Physique", "Physical"): oui(x["criteres"]["physique"]), tr("≥ 5 ans", "≥ 5 yrs"): oui(x["criteres"]["historique"]),
                                "PEA": "✓" if x["pea"] else "✗", tr("Motif", "Reason"): x["motif"]} for x in alt]),
                                hide_index=True, width="stretch")
                            if any(v is None for x in alt for v in x["criteres"].values()):
                                st.caption(tr("« ? » : donnée non vérifiée (TODO dans l'univers), comptée comme critère non rempli.",
                                              "'?': unverified data, counted as not met."))
                        if estime:
                            st.caption(tr("SRI suivi de * : action détenue en direct, sans DIC ; SRI estimé à partir de sa classe d'actifs.",
                                          "SRI with *: directly held stock, no KID; SRI estimated from its asset class."))


def _table_derive(pf_initial: dict, depuis: str, cible: dict, montant: float, libelle_initial: str):
    """Poids actuels après dérive depuis `depuis`, comparés à la cible ; ordres en euros pour revenir à la cible."""
    actuel = calcul_marches.poids_derives(pf_initial, depuis)
    perf = calcul_marches.performance_depuis(pf_initial, depuis)
    act, ini = cpf.poids_par_classe(actuel), cpf.poids_par_classe(pf_initial)
    valeur = montant * (1 + (perf or 0))
    alerte = [c for c in cpf.CLASSES if abs(act[c] - cible[c]) > 0.05]
    ecart = max(abs(act[c] - cible[c]) for c in cpf.CLASSES)
    st.markdown(tr(f"Investi le {commun.dt(depuis)} · performance depuis : <b>{pct(perf, 1, signe=True)}</b> · valeur estimée {eur(valeur)} · "
                   f"écart maximal {pct(ecart, 1)}"
                   + (" · <b style='color:#B3261E'>rééquilibrage conseillé</b> (classe à plus de 5 points de sa cible)" if alerte else
                      " · sous le seuil de 5 points : pas de rééquilibrage nécessaire"),
                   f"Invested on {commun.dt(depuis)} · return since: <b>{pct(perf, 1, signe=True)}</b> · estimated value {eur(valeur)} · "
                   f"max drift {pct(ecart, 1)}" + (" · <b>rebalancing advised</b>" if alerte else " · below the 5-point threshold")),
                unsafe_allow_html=True)
    lignes = [{tr("Classe", "Class"): commun.nom_classe(c), libelle_initial: pct(ini[c], 1), tr("Aujourd'hui", "Today"): pct(act[c], 1),
               tr("Cible", "Target"): pct(cible[c], 1), tr("Écart (pts)", "Drift (pts)"): commun.nb((act[c] - cible[c]) * 100, 1).replace("-", "−") if act[c] < cible[c]
               else "+" + commun.nb((act[c] - cible[c]) * 100, 1),
               tr("Ordre pour revenir à la cible", "Order back to target"): ("—" if abs(cible[c] - act[c]) < 0.001 else
                   (tr("Acheter ", "Buy ") if cible[c] > act[c] else tr("Vendre ", "Sell ")) + eur(abs(cible[c] - act[c]) * valeur))}
              for c in cpf.CLASSES if max(act[c], cible[c], ini[c]) > 1e-6]
    st.dataframe(pd.DataFrame(lignes), hide_index=True, width="stretch")
    st.caption(tr("Cours : ", "Prices: ") + calcul_marches.nom_mode(commun.L())
               + tr(". Les ordres ramènent chaque classe à sa cible ; le seuil d'alerte est de 5 points.", ". Orders bring each class back to target; alert threshold 5 points."))


SCENARIOS_SUIVI = {"1a": ("Il y a 1 an", "1 year ago"), "3a": ("Il y a 3 ans", "3 years ago"), "5a": ("Il y a 5 ans", "5 years ago"),
                   "covid": ("Juste avant le Covid", "Just before Covid"), "taux": ("Juste avant 2022", "Just before 2022")}


def _date_suivi(cle: str) -> str:
    aujourd = pd.Timestamp.today().normalize()
    return {"1a": aujourd - pd.DateOffset(years=1), "3a": aujourd - pd.DateOffset(years=3), "5a": aujourd - pd.DateOffset(years=5),
            "covid": pd.Timestamp("2020-02-19"), "taux": pd.Timestamp("2021-12-31")}[cle].date().isoformat()


def _reequilibrage(d: dict, reco: dict):
    """Suivi réel (dossier signé ou revue) et simulation du suivi « et si ce portefeuille avait été investi le… »."""
    montant = d["reponses"]["montant"]
    hist = d.get("historique") or []
    signe = d.get("statut") == "signé" and d.get("recommandation")
    ancien = d.get("recommandation") if signe else (hist[-1] if hist else None)
    if ancien and ancien.get("portefeuille"):
        with st.container(border=True):
            if signe:
                st.markdown(f"<div class='ra-surtitre'>{tr('Suivi : dérive depuis la signature', 'Monitoring: drift since signature')}</div>",
                            unsafe_allow_html=True)
                _table_derive(ancien["portefeuille"], ancien.get("date_signature") or ancien["date"],
                              cpf.poids_par_classe(ancien["portefeuille"]), montant, tr("Cible signée", "Signed target"))
            else:
                st.markdown(f"<div class='ra-surtitre'>{tr('Revue : de l’allocation signée à la nouvelle', 'Review: from the signed allocation to the new one')}</div>",
                            unsafe_allow_html=True)
                _table_derive(ancien["portefeuille"], ancien.get("date_signature") or ancien["date"], reco["classes"], montant,
                              tr("Allocation signée", "Signed allocation"))
    pf = ancien["portefeuille"] if signe else reco["portefeuille"]
    with st.expander(tr("Simuler le suivi : et si ce portefeuille avait été investi plus tôt ?",
                        "Simulate monitoring: what if this portfolio had been invested earlier?")):
        st.caption(tr("Rejoue la recommandation sur les cours passés pour montrer au client comment elle aurait vécu, de combien elle "
                      "aurait dérivé de sa cible, et quels ordres auraient rééquilibré le portefeuille. Simulation : rien n'est enregistré.",
                      "Replays the recommendation on past prices: drift from target and rebalancing orders. Simulation only."))
        noms = {k: v[commun.L() == "en"] for k, v in SCENARIOS_SUIVI.items()}
        choix = st.segmented_control("suivi", list(noms), format_func=noms.get, default="1a", key="w_sim_suivi",
                                     label_visibility="collapsed") or "1a"
        _table_derive(pf, _date_suivi(choix), cpf.poids_par_classe(pf), montant, tr("Cible", "Target") + " " + tr("initiale", "at start"))


def page():
    d = commun.exiger_dossier()
    if d is None:
        return
    L = commun.L()
    reco = commun.reco(d)
    prof = commun.profil(d)
    ctrl = commun.controles(d)
    synth = calcul_conformite.synthese(ctrl)
    fige = d.get("statut") in ("à signer", "signé", "archivé")
    r = d["reponses"]
    montant = r["montant"]
    frais = calcul_analyses.frais_totaux(reco["portefeuille"], reco["enveloppe"])
    mu_net = calcul_analyses.rendement_net(reco["portefeuille"], reco["enveloppe"])
    n_ans = commun.horizon_ans(r)
    flux = (r.get("versement_mensuel") or 0) - (r.get("retrait_mensuel") or 0)
    capital = calcul_analyses.capital_deterministe(montant, flux, n_ans, mu_net)[-1]

    commun.entete(tr("Recommandation", "Recommendation"),
                  tr("Chaque chiffre s'explique : cliquez sur « Pourquoi ? » ou dépliez le fil de décision.",
                     "Every figure is explained: click 'Why?' or unfold the decision trail."),
                  f"{d['reference']} · {d.get('note') or ''}")
    if d.get("statut") == "signé" and d.get("recommandation"):
        figee = d["recommandation"]["portefeuille"]
        if any(abs(figee.get(i, 0) - w) > 1e-6 for i, w in reco["portefeuille"].items()) or set(figee) != set(reco["portefeuille"]):
            st.info(tr("Les données ont changé depuis la signature : la recommandation affichée est recalculée ; la version signée reste dans le dossier.",
                       "Data changed since signature: the displayed recommendation is recomputed; the signed version stays on file."))

    # --- Bandeau principal : profil, risque, enveloppe
    c1, c2, c3 = st.columns([1, 1.9, 1], gap="medium")
    with c1, st.container(border=True):
        st.markdown(f"<div class='ra-surtitre'>{tr('Profil', 'Profile')}</div><div style='display:flex;gap:10px;align-items:baseline'>"
                    f"<span class='ra-profil-num'>{reco['profil']}</span><span style='font-size:19px;font-weight:650'>{commun.nom_profil(reco['profil'])}</span></div>"
                    f"<div class='ra-note'>{tr('calculé', 'computed')} {reco['profil_calcule']} · "
                    + " · ".join(f"{a} {v}" for a, v in zip(tr("Tol. Hor. Cap. Conn.", "Tol. Hor. Cap. Know.").split(), prof["notes"].values())) + "</div>", unsafe_allow_html=True)
        _pourquoi(tr("Pourquoi ce profil ?", "Why this profile?"), reco, [2, 3], d, "p1")
    with c2, st.container(border=True):
        vmin, vmax = cpf.PROFILS[reco["profil"]]["vol"]
        pos = min(max((reco["vol"] - 0) / 0.18, 0), 1) * 100
        st.markdown(f"<div class='ra-surtitre'>{tr('Allocation et risque attendu', 'Allocation and expected risk')}</div>"
                    + commun.barre_classes(reco["classes"], 14)
                    + f"<div style='position:relative;height:30px;margin-top:12px'><div style='position:absolute;top:10px;left:0;right:0;height:6px;background:#EEE9DF;border-radius:3px'></div>"
                      f"<div style='position:absolute;top:10px;left:{vmin / 0.18 * 100:.1f}%;width:{(vmax - vmin) / 0.18 * 100:.1f}%;height:6px;background:#D9C7A7;border-radius:3px'></div>"
                      f"<div style='position:absolute;top:3px;left:calc({pos:.1f}% - 9px);width:18px;height:18px;border-radius:50%;background:{'#14213D' if reco['dans_les_limites'] else '#B3261E'};border:3px solid #fff;box-shadow:0 0 0 1px #14213D'></div></div>"
                      f"<div class='ra-note'>{tr('Volatilité attendue', 'Expected volatility')} <b style='color:#14213D'>{pct(reco['vol'], 1)}</b> · "
                      f"{tr('zone du profil', 'profile range')} {pct(vmin, 0)}–{pct(vmax, 0)} · SRI {reco['sri']}/7 (max. {cpf.PROFILS[reco['profil']]['sri_max']})</div>",
                    unsafe_allow_html=True)
        p1, p2 = st.columns(2)
        with p1:
            _pourquoi(tr("Pourquoi cette allocation ?", "Why this allocation?"), reco, [4, 6, 7], d, "p2")
        with p2:
            _pourquoi(tr("Pourquoi ce niveau de risque ?", "Why this risk level?"), reco, [9], d, "p3")
    with c3, st.container(border=True):
        st.markdown(f"<div class='ra-surtitre'>{tr('Enveloppe', 'Wrapper')}</div><div style='font-size:19px;font-weight:650;margin:6px 0'>"
                    f"{commun.nom_env(reco['enveloppe'])}</div><div class='ra-note'>{len(reco['portefeuille'])} {tr('lignes', 'holdings')} · "
                    f"{tr('frais', 'fees')} {pct(frais['total'], 2)}/{tr('an', 'yr')}</div>", unsafe_allow_html=True)
        _pourquoi(tr("Pourquoi cette enveloppe ?", "Why this wrapper?"), reco, [5], d, "p4")

    commun.rangee_kpi([
        commun.kpi(tr("Montant", "Amount"), eur(montant)),
        commun.kpi(tr("Rendement attendu", "Expected return"), pct(mu_net, 2), tr("par an, net de tous les frais", "a year, net of all fees")),
        commun.kpi(tr(f"Capital dans {n_ans} ans", f"Capital in {n_ans} years"), eur(capital),
                   tr("scénario central, versements compris", "central scenario, contributions included")),
        commun.kpi(tr("Frais annuels", "Annual fees"), pct(frais["total"], 2),
                   tr(f"fonds {pct(frais['fonds'], 2)} · contrat {pct(frais['contrat'], 2)}", f"funds {pct(frais['fonds'], 2)} · wrapper {pct(frais['contrat'], 2)}")),
        commun.kpi(tr("Conformité", "Compliance"), {"ok": tr("Conforme", "Compliant"), "attention": tr("À documenter", "To document"),
                                                     "bloquant": tr("Bloquant", "Blocking")}[synth],
                   tr(f"{sum(c['statut'] == 'ok' for c in ctrl)}/{len(ctrl)} contrôles conformes", f"{sum(c['statut'] == 'ok' for c in ctrl)}/{len(ctrl)} checks pass"),
                   couleur={"ok": commun.VERT, "attention": commun.AMBRE, "bloquant": commun.ROUGE}[synth]),
    ])

    _reglages(d, reco, fige)
    _reequilibrage(d, reco)

    o1, o2, o3 = st.tabs([tr("Portefeuille", "Portfolio"), tr("Fil de décision", "Decision trail"), tr("Conformité", "Compliance")])
    with o1:
        _lignes(d, reco)
    with o2:
        st.caption(tr("Survolez une référence « Q.. » pour voir la question et la réponse signée du client.",
                      "Hover a 'Q..' reference to see the question and the client's signed answer."))
        fil = reco["fil"] + [{"n": len(reco["fil"]) + 1, "titre": tr("Contrôles d'adéquation", "Suitability checks"),
                              "resultat": {"ok": tr("Conforme", "Compliant"), "attention": tr("À documenter", "To document"),
                                           "bloquant": tr("Bloquant", "Blocking")}[synth],
                              "regle": tr("La déclaration ne peut être émise qu'en l'absence de contrôle bloquant.", "No statement while a check is blocking."),
                              "details": [(f"{commun.badge(c['statut'])} <b>{c['titre']}</b> — {c['detail']}", []) for c in ctrl],
                              "source": "MiFID II art. 25 ; orientations ESMA"}]
        st.markdown(commun.fil_html(fil, r, ouvertes=(3, 9)), unsafe_allow_html=True)
    with o3:
        for c in ctrl:
            st.markdown(f"{commun.badge(c['statut'])} **{c['titre']}** — {c['detail']}  \n<span class='ra-note'>{c['regle']}</span>",
                        unsafe_allow_html=True)

    st.divider()
    a, b, c_ = st.columns([2.2, 1.2, 1.2], vertical_alignment="center")
    statut = d.get("statut")
    if statut == "brouillon":
        a.markdown(tr("**Étape suivante** : émettre la déclaration d'adéquation, à faire signer au client.",
                      "**Next step**: issue the suitability statement for signature.") if synth != "bloquant" else
                   tr("**Un contrôle bloquant empêche l'émission** : voir l'onglet Conformité.", "**A blocking check prevents issuing.**"))
        b.button(tr("Émettre la déclaration", "Issue the statement"), type="primary", disabled=synth == "bloquant", on_click=_emettre,
                 key="btn_emettre", width="stretch")
        c_.button(tr("Projection et risques →", "Projection & risk →"), on_click=commun.aller, args=("analyses",), key="btn_proj", width="stretch")
    elif statut == "à signer":
        a.date_input(tr("Date de signature du client", "Client signature date"), value=date.today(), key="w_date_signature",
                     max_value=date.today(), format="DD/MM/YYYY")
        b.button(tr("Enregistrer la signature", "Record signature"), type="primary", on_click=_signer, key="btn_signer", width="stretch")
        c_.button(tr("Annuler l'émission", "Cancel issue"), on_click=_annuler_emission, key="btn_annuler", width="stretch")
    else:
        a.markdown(tr(f"**Déclaration signée le {commun.dt(d['recommandation'].get('date_signature'))}.** "
                      "Pour toute modification, ouvrez une revue depuis le questionnaire.",
                      f"**Statement signed on {commun.dt(d['recommandation'].get('date_signature'))}.**"))
        b.button(tr("Documents →", "Documents →"), on_click=commun.aller, args=("livrables",), key="btn_docs", width="stretch")
        c_.button(tr("Ouvrir une revue", "Start a review"), on_click=_revue_et_aller, key="btn_revue_reco", width="stretch")


def _revue_et_aller():
    import ecran_questionnaire
    ecran_questionnaire.demarrer_revue()
    commun.aller("questionnaire")
