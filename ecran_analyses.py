"""
ecran_analyses.py — Projection (Monte Carlo), stress tests et rejeu des crises, frontière efficiente, fiscalité,
durabilité. Tout porte sur le portefeuille recommandé du dossier ouvert.
"""

from __future__ import annotations

import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import calcul_analyses as ca
import calcul_marches
import calcul_portefeuille as cpf
import commun
import donnees
from commun import eur, nb, pct, tr

GRILLE = "#EEE9DF"


def _style(fig):
    """Séparateurs français (1 234,5) et fond blanc pour tous les graphiques."""
    fig.update_layout(separators=", " if commun.L() == "fr" else ".,", plot_bgcolor="white", font=dict(family="Inter, sans-serif"))
    return fig


def _projection(d, reco):
    r, L = d["reponses"], commun.L()
    pf, env, montant = reco["portefeuille"], reco["enveloppe"], r["montant"]
    h0 = commun.horizon_ans(r)
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns(4)
        ans = c1.slider(tr("Horizon (années)", "Horizon (years)"), 1, 30, h0, key="a_ans")
        vers = c2.number_input(tr("Versement mensuel (€)", "Monthly contribution (€)"), 0, 50_000, int(r.get("versement_mensuel") or 0), 100, key="a_vers")
        retr = c3.number_input(tr("Retrait mensuel (€)", "Monthly withdrawal (€)"), 0, 50_000, int(r.get("retrait_mensuel") or 0), 100, key="a_retr")
        cible = c4.number_input(tr("Montant visé (€)", "Target (€)"), 0, 100_000_000, int(r.get("cible") or 0), 10_000, key="a_cible")
        reel = st.toggle(tr("Afficher en euros d'aujourd'hui (inflation 2 %)", "Show in today's euros (2% inflation)"), key="a_reel")
    if ans != h0 or vers != (r.get("versement_mensuel") or 0):
        st.caption(tr("Scénario « et si » : les documents restent établis sur les réponses signées du client.",
                      "'What if' scenario: documents keep the client's signed answers."))
    sim = commun.simuler(json.dumps(pf, sort_keys=True), env, montant, vers, retr, ans, cible)
    defl = [(1 + ca.INFLATION) ** -a for a in range(ans + 1)]
    f = (lambda xs: [x * k for x, k in zip(xs, defl)]) if reel else (lambda xs: xs)
    trad = ca.capital_deterministe(montant, vers - retr, ans, sim["mu"] + ca.frais_totaux(pf, env)["total"] - 0.018)
    fe = ca.capital_deterministe(montant, vers - retr, ans, ca.taux_fonds_euros() - 0.0)
    commun.rangee_kpi([
        commun.kpi(tr("Défavorable (10 %)", "Unfavourable (10%)"), eur(f(sim["p10"])[-1]), tr("1 chance sur 10 de faire moins", "1 in 10 chance of less")),
        commun.kpi(tr("Central (50 %)", "Central (50%)"), eur(f(sim["p50"])[-1]), couleur=commun.BLEU),
        commun.kpi(tr("Favorable (90 %)", "Favourable (90%)"), eur(f(sim["p90"])[-1]), tr("1 chance sur 10 de faire plus", "1 in 10 chance of more")),
        commun.kpi(tr("Capital versé", "Capital contributed"), eur(f(sim["verse"])[-1])),
        commun.kpi(tr("Objectif atteint", "Target reached"), "—" if sim["proba_cible"] is None else pct(sim["proba_cible"], 0),
                   eur(cible) if cible else tr("pas d'objectif saisi", "no target")),
    ] + ([commun.kpi(tr("Capital épuisé", "Capital depleted"), pct(sim["proba_epuisement"], 0), tr("probabilité à l'horizon", "probability at horizon"),
                     couleur=commun.ROUGE)] if sim["proba_epuisement"] is not None else []))
    an0 = pd.Timestamp.today().year
    x = [an0 + a for a in range(ans + 1)]
    fig = go.Figure()
    fig.add_trace(go.Scatter(mode="lines", x=x, y=f(sim["p90"]), line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(mode="lines", x=x, y=f(sim["p10"]), fill="tonexty", fillcolor="rgba(20,33,61,0.10)", line=dict(width=0),
                             name=tr("8 trajectoires sur 10", "8 paths out of 10")))
    fig.add_trace(go.Scatter(mode="lines", x=x, y=f(sim["p50"]), name=tr("Scénario central", "Central scenario"), line=dict(color="#14213D", width=3)))
    fig.add_trace(go.Scatter(mode="lines", x=x, y=f(sim["ref_6040"]), name=tr("60/40 (médiane)", "60/40 (median)"), line=dict(color="#9AA5B1", dash="dash")))
    fig.add_trace(go.Scatter(mode="lines", x=x, y=f(trad), name=tr("Gestion traditionnelle (1,8 % de frais)", "Traditional management (1.8% fees)"),
                             line=dict(color="#B08D57", width=2)))
    fig.add_trace(go.Scatter(mode="lines", x=x, y=f(fe), name=tr("Fonds en euros seul", "Euro fund only"), line=dict(color="#7A9E7E", width=1.5, dash="dot")))
    fig.add_trace(go.Scatter(mode="lines", x=x, y=f(sim["verse"]), name=tr("Capital versé", "Contributed"), line=dict(color="#C8C8C8", dash="dot")))
    if cible:
        fig.add_hline(y=cible * (defl[-1] if reel else 1), line_dash="dot", line_color="#B3261E", annotation_text=tr("Objectif", "Target"))
    fig.update_layout(height=430, margin=dict(l=0, r=0, t=10, b=0), hovermode="x unified", plot_bgcolor="white",
                      yaxis=dict(tickformat=",.0f", ticksuffix=" €", gridcolor=GRILLE), xaxis=dict(dtick=1 if ans <= 15 else 2),
                      legend=dict(orientation="h", y=-0.15))
    st.plotly_chart(_style(fig), width="stretch", key="fig_proj")
    st.caption(tr(f"10 000 trajectoires ; rendement attendu net de tous les frais {pct(sim['mu'], 2)}, volatilité attendue {pct(sim['vol'], 1)}. "
                  f"Hypothèses : {ca.SOURCE_HYPOTHESES}. La gestion traditionnelle suppose 1,8 % de frais annuels (fonds actifs + contrat), "
                  "valeur de démonstration à sourcer.",
                  f"10,000 paths; expected return net of fees {pct(sim['mu'], 2)}, expected volatility {pct(sim['vol'], 1)}."))


def _stress(d, reco):
    pf, montant = reco["portefeuille"], d["reponses"]["montant"]
    res = ca.tous_les_stress(pf, montant, commun.L())
    ind = commun.indicateurs(json.dumps(pf, sort_keys=True))
    lignes = "".join(f"<tr><td style='padding:8px'><b>{x['nom']}</b><div class='ra-note'>{x['periode']}</div></td>"
                     f"<td style='text-align:right;color:{commun.ROUGE if x['variation'] < 0 else commun.VERT};font-weight:650'>{pct(x['variation'], 1, True)}</td>"
                     f"<td style='text-align:right'>{eur(x['euros'], True)}</td><td style='text-align:right'>{eur(x['apres'])}</td>"
                     f"<td style='text-align:right'>{'—' if x['recuperation'] is None else tr(f'{nb(x['recuperation'], 1)} ans', f'{x['recuperation']:.1f} yrs')}</td>"
                     f"<td style='text-align:right' class='ra-note'>{pct(ind['crises'].get(x['cle']), 1, True) if ind['crises'].get(x['cle']) is not None else '—'}</td></tr>"
                     for x in res)
    st.markdown(f"<div class='ra-carte'><table style='width:100%;font-size:13.5px;border-collapse:collapse'><tr class='ra-note'>"
                f"<th style='text-align:left;padding:6px 8px'>{tr('Scénario', 'Scenario')}</th><th style='text-align:right'>{tr('Choc', 'Shock')}</th>"
                f"<th style='text-align:right'>{tr('En euros', 'In euros')}</th><th style='text-align:right'>{tr('Valeur après', 'Value after')}</th>"
                f"<th style='text-align:right'>{tr('Retour au capital', 'Recovery')}</th><th style='text-align:right'>{tr('Rejeu des cours', 'Price replay')}</th></tr>"
                f"{lignes}</table></div>", unsafe_allow_html=True)
    st.caption(tr("Choc : ordre de grandeur de la crise appliqué à chaque classe d'actifs. Rejeu : ce qu'auraient fait les supports eux-mêmes "
                  "sur leurs cours (simulation rétrospective). Retour au capital : au rendement attendu du portefeuille.",
                  "Shock: crisis order of magnitude by asset class. Replay: what the products did on their own prices."))
    st.markdown(f"##### {tr('Machine à remonter le temps', 'Time machine')}")
    noms = {k: v["nom"][commun.L() == "en"] for k, v in ca.SCENARIOS.items() if v["dates"]}
    choix = st.segmented_control("crise", list(noms), format_func=noms.get, default="crise_2008", key="a_crise",
                                 label_visibility="collapsed") or "crise_2008"
    s = calcul_marches.rejeu(pf, choix)
    ref = calcul_marches.rejeu({"IE00B4L5Y983": 1.0}, choix)
    fe = calcul_marches.rejeu({"FONDS-EUROS": 1.0}, choix)
    if s is None:
        st.caption(tr("Historique insuffisant pour rejouer cette crise.", "Not enough history to replay this crisis."))
        return
    fig = go.Figure()
    for serie, nom_, coul, w in ((ref, tr("MSCI World seul", "MSCI World only"), "#B3261E", 1.5), (fe, tr("Fonds en euros", "Euro fund"), "#7A9E7E", 1.5),
                                 (s, tr("Portefeuille recommandé", "Recommended portfolio"), "#14213D", 3)):
        if serie is not None:
            fig.add_trace(go.Scatter(mode="lines", x=serie.index, y=serie.values * montant / 100, name=nom_, line=dict(color=coul, width=w)))
    sc = ca.SCENARIOS[choix]
    fig.add_vrect(x0=sc["dates"][0], x1=sc["dates"][1], fillcolor="rgba(179,38,30,0.07)", line_width=0,
                  annotation_text=tr("crise", "crisis"), annotation_position="top left")
    fig.update_layout(height=340, margin=dict(l=0, r=0, t=10, b=0), plot_bgcolor="white", hovermode="x unified",
                      yaxis=dict(tickformat=",.0f", ticksuffix=" €", gridcolor=GRILLE), legend=dict(orientation="h", y=-0.18))
    st.plotly_chart(_style(fig), width="stretch", key="fig_rejeu")
    pire = float(s.min() / 100 - 1)
    st.caption(tr(f"Si {eur(montant)} avaient été investis selon cette recommandation juste avant la crise, le point bas aurait été de "
                  f"{eur(montant * (1 + pire))} ({pct(pire, 1, True)}). Cours : {calcul_marches.nom_mode('fr')}.",
                  f"Trough would have been {eur(montant * (1 + pire))} ({pct(pire, 1, True)}). Prices: {calcul_marches.nom_mode('en')}."))


def _frontiere(reco):
    a = ca.analyse_markowitz(reco["portefeuille"])
    i = 1 if commun.L() == "en" else 0
    commun.rangee_kpi([
        commun.kpi(tr("Rendement attendu", "Expected return"), pct(a["mu"], 2), tr("brut de frais", "gross of fees")),
        commun.kpi(tr("Volatilité attendue", "Expected volatility"), pct(a["vol"], 1)),
        commun.kpi("Sharpe", "—" if a["sharpe"] is None else nb(a["sharpe"]), tr(f"sans risque {pct(a['rf'], 1)}", f"risk-free {pct(a['rf'], 1)}")),
        commun.kpi(tr("Écart à la frontière", "Gap to frontier"), "—" if a["ecart"] is None else f"{nb(a['ecart'] * 100)} pt",
                   tr("rendement cédé à risque égal", "return given up at equal risk")),
    ])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[p["vol"] * 100 for p in a["frontiere"]], y=[p["mu"] * 100 for p in a["frontiere"]], mode="lines",
                             name=tr("Frontière efficiente", "Efficient frontier"), line=dict(color="#14213D", width=3)))
    if a["frontiere_fe"]:
        fig.add_trace(go.Scatter(x=[p["vol"] * 100 for p in a["frontiere_fe"]], y=[p["mu"] * 100 for p in a["frontiere_fe"]], mode="lines",
                                 name=tr("avec fonds en euros", "with euro fund"), line=dict(color="#3E6E8E", dash="dash")))
    for p in cpf.PROFILS:
        vmin, vmax = cpf.PROFILS[p]["vol"]
        fig.add_vrect(x0=vmin * 100, x1=vmax * 100, fillcolor=["#F7F4EE", "#FBFAF7"][p % 2], line_width=0, layer="below",
                      annotation_text=str(p), annotation_position="bottom")
    v64, m64 = a["ref_6040"]
    fig.add_trace(go.Scatter(x=[v64 * 100], y=[m64 * 100], mode="markers", name="60/40", marker=dict(size=11, symbol="diamond", color="#9AA5B1")))
    ms = a["max_sharpe"]
    fig.add_trace(go.Scatter(x=[ms["vol"] * 100], y=[ms["mu"] * 100], mode="markers", name=tr("Meilleur Sharpe", "Max Sharpe"),
                             marker=dict(size=11, symbol="square", color="#7A9E7E")))
    fig.add_trace(go.Scatter(x=[a["vol"] * 100], y=[a["mu"] * 100], mode="markers", name=tr("Recommandation", "Recommendation"),
                             marker=dict(size=20, symbol="star", color="#B08D57", line=dict(color="white", width=1))))
    fig.update_layout(height=380, margin=dict(l=0, r=0, t=10, b=0), plot_bgcolor="white",
                      xaxis=dict(title=tr("Volatilité attendue (%)", "Expected volatility (%)"), gridcolor=GRILLE, rangemode="tozero"),
                      yaxis=dict(title=tr("Rendement attendu (%)", "Expected return (%)"), gridcolor=GRILLE), legend=dict(orientation="h", y=-0.2))
    g, dr = st.columns([1.5, 1], gap="large")
    g.plotly_chart(_style(fig), width="stretch", key="fig_front")
    with dr:
        st.markdown(f"**{tr('D’où vient le risque ?', 'Where does the risk come from?')}**")
        st.markdown("".join(
            f"<div style='font-size:12.5px;margin:7px 0 2px;display:flex;justify-content:space-between'><span>{ca.NOMS_CLASSES[c][i]}</span>"
            f"<span class='ra-note'>{tr('poids', 'weight')} {pct(w, 0)} · <b style='color:#14213D'>{tr('risque', 'risk')} {pct(rc, 0)}</b></span></div>"
            f"<div style='position:relative;height:8px;background:#EEE9DF;border-radius:4px'><div style='position:absolute;height:8px;width:{w * 100:.0f}%;background:#D9C7A7;border-radius:4px'></div>"
            f"<div style='position:absolute;height:8px;width:{max(rc, 0) * 100:.0f}%;background:#14213D;border-radius:4px;opacity:.85'></div></div>"
            for c, (w, rc) in list(a["contributions"].items())[:7]), unsafe_allow_html=True)
        st.caption(tr("Clair : part du capital · foncé : part du risque total. Bandes du graphique : zones de volatilité des 5 profils.",
                      "Light: share of capital · dark: share of risk. Bands: the 5 profiles' volatility ranges."))
    st.caption(tr("Moyenne-variance de Markowitz sur 10 classes d'actifs, sans vente à découvert. L'écart à la frontière est le prix des "
                  "contraintes de conseil (30 % par ligne, satellite, préférences du client) : il est assumé pour la diversification.",
                  "Markowitz mean-variance on 10 asset classes, long only."))


def _fiscalite(d, reco):
    r = d["reponses"]
    c1, c2 = st.columns(2)
    ans = c1.slider(tr("Durée de détention (années)", "Holding period (years)"), 1, 30, commun.horizon_ans(r), key="a_fisc_ans")
    foyer = c2.segmented_control(tr("Foyer fiscal", "Tax household"), ["seul", "couple"], default=ca.foyer(r), key="a_foyer",
                                 format_func={"seul": tr("Personne seule", "Single"), "couple": tr("Couple", "Couple")}.get) or "seul"
    res = ca.comparer_enveloppes(reco["portefeuille"], r["montant"], r.get("versement_mensuel") or 0, ans, foyer, commun.L())
    cartes = ""
    for x in res:
        if not x["applicable"]:
            cartes += (f"<div class='ra-carte' style='opacity:.6'><b>{x['nom']}</b><div class='ra-note' style='margin-top:8px'>"
                       + tr("Non applicable : aucune ligne de ce portefeuille n'est éligible au PEA.", "Not applicable: no PEA-eligible holding.")
                       + "</div></div>")
            continue
        tag = (f"<span class='ra-badge' style='background:#E6F4EA;color:#1E7F4F'>{tr('Meilleur net', 'Best net')}</span>" if x["meilleur"] else "")
        tag += (f" <span class='ra-badge' style='background:#F3EEE3;color:#7A5C2E'>{tr('Recommandée', 'Recommended')}</span>"
                if x["enveloppe"] == reco["enveloppe"] else "")
        part = f"<div class='ra-note'>{tr('part logée dans le PEA', 'share held in the PEA')} : {pct(x['part_pea'], 0)}</div>" if x["part_pea"] is not None else ""
        cartes += (f"<div class='ra-carte' style='border:2px solid {'#14213D' if x['meilleur'] else '#E8E2D6'}'><div style='display:flex;justify-content:space-between'>"
                   f"<b>{x['nom']}</b><span>{tag}</span></div><div style='font-size:25px;font-weight:700;margin-top:6px'>{eur(x['net'])}</div>"
                   f"<div class='ra-note'>{tr('net de frais et d’impôts', 'net of fees and tax')}</div>{part}"
                   f"<table style='width:100%;font-size:13px;margin-top:8px'><tr><td>{tr('Capital brut', 'Gross')}</td><td style='text-align:right'>{eur(x['brut'])}</td></tr>"
                   f"<tr><td>{tr('Impôt sur le revenu', 'Income tax')}</td><td style='text-align:right'>{eur(-x['ir'])}</td></tr>"
                   f"<tr><td>{tr('Prélèvements sociaux', 'Social charges')}</td><td style='text-align:right'>{eur(-x['ps'])}</td></tr>"
                   f"<tr><td>{tr('Taux effectif', 'Effective rate')}</td><td style='text-align:right'><b>{pct(x['taux'], 1)}</b></td></tr></table></div>")
    st.markdown(f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px'>{cartes}</div>", unsafe_allow_html=True)
    meilleur = next(x for x in res if x["meilleur"])
    if meilleur["enveloppe"] != reco["enveloppe"]:
        st.info(tr(f"Sur le seul critère fiscal, {meilleur['nom']} rapporte le plus. L'enveloppe recommandée l'est pour d'autres raisons "
                   "(fonds en euros, transmission, souhait du client) : voir le fil de décision, étape 5.",
                   f"On tax alone, {meilleur['nom']} leaves the most; the recommended wrapper is chosen for other reasons (step 5)."))
    st.caption(tr("Règles 2026 : flat tax 31,4 % (12,8 % + 18,6 % de prélèvements sociaux) ; PEA après 5 ans : 18,6 % ; assurance-vie : "
                  "prélèvements sociaux 17,2 % (exclue de la hausse de CSG), après 8 ans abattement 4 600 € / 9 200 € puis 7,5 % "
                  "(12,8 % au-delà de 150 000 € de primes). Même portefeuille dans chaque enveloppe ; en PEA, seules les lignes éligibles y sont logées. "
                  "Simplifications : retrait total à l'horizon, pas d'imposition annuelle des dividendes ni de droits de garde en compte-titres ; "
                  "l'avantage successoral de l'assurance-vie (abattement de 152 500 € par bénéficiaire) n'est pas chiffré ici.",
                  "2026 rules; same portfolio in each wrapper; simplified full withdrawal at horizon."))


def _durabilite(d, reco):
    pf = reco["portefeuille"]
    u = donnees.univers()
    x = ca.durabilite(pf)
    r = d["reponses"]
    commun.rangee_kpi([
        commun.kpi(tr("Préférence du client", "Client preference"), str(r.get("durabilite"))),
        commun.kpi(tr("Part en versions ISR", "Share in SRI versions"), pct(x["part_isr"], 0)),
        commun.kpi(tr("Intensité carbone estimée", "Estimated carbon intensity"), "—" if x["intensite"] is None else f"{x['intensite']:.0f}",
                   tr(f"t CO2e / M€ de CA · indice monde ≈ {x['reference']}", f"t CO2e / €m revenue · world ≈ {x['reference']}")),
        commun.kpi(tr("Exclusions", "Exclusions"), ", ".join(r.get("exclusions") or []) or "—"),
    ])
    lignes = [{tr("Support", "Product"): u.loc[i, "nom"], tr("Poids", "Weight"): pct(w, 1), "Version": u.loc[i, "version"],
               "SFDR": u.loc[i, "sfdr"] if u.loc[i, "sfdr"] not in ("", "TODO", "n/a") else tr("à vérifier", "to check"),
               tr("Secteurs sensibles", "Sensitive sectors"): u.loc[i, "tags"] or "—"} for i, w in sorted(pf.items(), key=lambda t: -t[1])]
    st.dataframe(pd.DataFrame(lignes), hide_index=True, width="stretch")
    st.caption(tr("Article SFDR : lu dans la documentation des fonds quand il est vérifié ; « à vérifier » sinon (jamais inventé). "
                  "Les exclusions s'appliquent aux actions en direct ; pour les ETF, la préférence se traduit par le choix de la version ISR. "
                  "Intensité carbone : moyennes sectorielles indicatives, pas une donnée publiée par entreprise.",
                  "SFDR article read from fund documents when verified. Carbon intensity: indicative sector averages."))


def page():
    d = commun.exiger_dossier()
    if d is None:
        return
    reco = commun.reco(d)
    commun.entete(tr("Projection et risques", "Projection & risk"),
                  tr("Ce que la recommandation peut devenir, comment elle réagit aux crises, et ce qu'elle laisse après impôts.",
                     "What the recommendation may become, how it reacts to crises, and what it leaves after tax."),
                  f"{d['reference']} · {commun.nom_profil(reco['profil'])} · {commun.nom_env(reco['enveloppe'])}")
    o = st.tabs([tr("Projection", "Projection"), tr("Crises et stress tests", "Crises & stress tests"), tr("Frontière efficiente", "Efficient frontier"),
                 tr("Fiscalité", "Tax"), tr("Durabilité", "Sustainability")])
    with o[0]:
        _projection(d, reco)
    with o[1]:
        _stress(d, reco)
    with o[2]:
        _frontiere(reco)
    with o[3]:
        _fiscalite(d, reco)
    with o[4]:
        _durabilite(d, reco)
