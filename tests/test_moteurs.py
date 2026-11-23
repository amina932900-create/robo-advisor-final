"""Tests des règles de conseil : chaque règle annoncée dans la Méthodologie est vérifiée ici."""
import itertools

import pytest

import calcul_analyses as ca
import calcul_conformite as cc
import calcul_portefeuille as cpf
import calcul_profil as cp
import donnees


EXPERT = {"priorite": "max", "reaction_baisse": "renforcer", "perte_max": "30", "choix_portefeuille": "D", "quiz_fonds_euros": True,
          "anciennete": ">5", "niveau": "confirme", "produits_detenus": ["actions", "etf", "obligations"]}


def reco(r, **k):
    return cpf.recommander(r, cp.calculer_profil(r), **k)


# ------------------------------------------------------------------ Profil
def test_profil_est_la_plus_petite_note(client_type):
    p = cp.calculer_profil(client_type)
    assert p["profil"] == min(p["notes"].values()) == 3
    assert "tolerance" in p["limitant"]


def test_horizon_court_plafonne(client_type):
    assert cp.calculer_profil({**client_type, "horizon": "<2"})["profil"] == 1


def test_pas_epargne_precaution_plafonne_capacite(client_type):
    p = cp.calculer_profil({**client_type, "epargne_precaution": False})
    assert p["notes"]["capacite"] == 3 and p["alertes"]


def test_quiz_rate_plafonne_connaissances(client_type):
    r = {**client_type, "quiz_etf": False, "quiz_diversification": False, "quiz_perte": False}
    assert cp.calculer_profil(r)["notes"]["connaissances"] == 3


def test_chaque_note_est_justifiee_par_des_questions(client_type):
    p = cp.calculer_profil(client_type)
    for k in p["notes"]:
        assert p["detail"][k], k
    nums = {q["num"] for q in cp.QUESTIONS}
    for k in p["detail"]:
        for _, refs in p["detail"][k]:
            assert set(refs) <= nums


def test_questions_numerotees_et_conditionnelles(client_type):
    assert [q["num"] for q in cp.QUESTIONS] == list(range(1, len(cp.QUESTIONS) + 1))
    assert not cp.visible(cp.q("taux_effort"), client_type)
    assert cp.visible(cp.q("taux_effort"), {**client_type, "credits": True})
    assert cp.manquantes(client_type) == []


# ------------------------------------------------------------------ Portefeuille
def test_aucun_hasard_memes_reponses_meme_portefeuille(client_type):
    assert reco(client_type)["portefeuille"] == reco(dict(client_type))["portefeuille"]


def test_age_sans_effet_sur_les_supports(client_type):
    """Changer l'âge de 45 à 46 ans ne change pas le portefeuille (plus de tirage lié aux réponses)."""
    assert reco(client_type)["portefeuille"] == reco({**client_type, "age": 46})["portefeuille"]


@pytest.mark.parametrize("p,env,zone,dura", list(itertools.product(range(1, 6), ["assurance-vie", "PEA", "CTO"],
                                                              ["Monde", "Europe", "France"], ["aucune", "article 8"])))
def test_contraintes_et_grille_respectees(client_type, p, env, zone, dura):
    r = {**client_type, **EXPERT, "enveloppe_souhaitee": env, "zone": zone, "durabilite": dura}
    x = reco(r, profil_retenu=p)
    pf = x["portefeuille"]
    assert abs(sum(pf.values()) - 1) < 1e-9
    assert max(pf.values()) <= cpf.MAX_LIGNE + 1e-9
    u = donnees.univers()
    assert sum(w for i, w in pf.items() if u.loc[i, "sous_classe"] == "haut_rendement") <= cpf.MAX_HAUT_RENDEMENT + 1e-9
    assert sum(w for i, w in pf.items() if u.loc[i, "sous_classe"] == "emergents") <= cpf.MAX_EMERGENTS + 1e-9
    assert x["dans_les_limites"], (p, env, x["vol"])
    assert ("FONDS-EUROS" in pf) == (env == "assurance-vie" and cpf.PROFILS[p]["allocation"]["monetaire"] > 0)
    assert all(w >= cpf.MIN_LIGNE - 1e-9 or u.loc[i, "type"] == "action" for i, w in pf.items())


EXPERT = {"priorite": "max", "reaction_baisse": "renforcer", "perte_max": "30", "choix_portefeuille": "D", "quiz_fonds_euros": True,
          "anciennete": ">5", "niveau": "confirme", "produits_detenus": ["actions", "etf", "obligations"]}


def test_volatilite_attendue_dans_la_fourchette_de_chaque_grille(client_type):
    for p in cpf.PROFILS:
        x = reco({**client_type, **EXPERT, "enveloppe_souhaitee": "assurance-vie"}, profil_retenu=p)
        assert x["profil"] == p
        vmin, vmax = cpf.PROFILS[p]["vol"]
        assert vmin - 0.005 <= x["vol"] <= vmax, (p, x["vol"])
        assert x["sri"] <= cpf.PROFILS[p]["sri_max"]


def test_profil_jamais_releve(client_type):
    assert reco(client_type, profil_retenu=5)["profil"] == 3


def test_scpi_seulement_assurance_vie_et_horizon_long(client_type):
    assert "SCPI-IMMORENTE" in reco(client_type)["portefeuille"]
    assert "SCPI-IMMORENTE" not in reco({**client_type, "horizon": "5-8"})["portefeuille"]
    assert "SCPI-IMMORENTE" not in reco({**client_type, "enveloppe_souhaitee": "CTO"})["portefeuille"]


def test_satellite_actions_reserve_aux_profils_4_5_hors_assurance_vie(client_type):
    expert = {**client_type, "priorite": "max", "reaction_baisse": "renforcer", "perte_max": "30", "choix_portefeuille": "D",
              "quiz_fonds_euros": True, "anciennete": ">5", "niveau": "confirme", "produits_detenus": ["actions", "etf", "obligations"],
              "objectif": "valorisation"}
    u = donnees.univers()
    titres = lambda x: [i for i in x["portefeuille"] if u.loc[i, "type"] == "action"]
    assert len(titres(reco(expert))) == 8                                   # profil 5, PEA
    assert titres(reco({**expert, "enveloppe_souhaitee": "assurance-vie"})) == []
    assert titres(reco(expert, profil_retenu=3)) == []
    sect = [u.loc[i, "secteur"] for i in titres(reco(expert))]
    assert len(sect) == len(set(sect))                                      # un titre par secteur


def test_exclusions_respectees(client_type):
    expert = {**client_type, "priorite": "max", "reaction_baisse": "renforcer", "perte_max": "30", "choix_portefeuille": "D",
              "quiz_fonds_euros": True, "anciennete": ">5", "niveau": "confirme", "produits_detenus": ["actions", "etf", "obligations"],
              "objectif": "valorisation", "enveloppe_souhaitee": "CTO", "durabilite": "exclusions", "exclusions": ["fossiles", "alcool"]}
    u = donnees.univers()
    for i in reco(expert)["portefeuille"]:
        assert not ({"fossiles", "alcool"} & set(str(u.loc[i, "tags"]).split(";")))


def test_preference_durable_choisit_les_versions_isr(client_type):
    x = reco({**client_type, "durabilite": "article 8"})
    u = donnees.univers()
    assert all(u.loc[i, "version"] in ("durable", "commun") for i in x["portefeuille"]
               if (u.loc[i, "sous_classe"] in ("monde", "europe", "ig", "etat")))


def test_choix_etf_par_criteres_et_motive(client_type):
    cands = cpf.classer_etf("monde", False, "assurance-vie")
    assert cands[0]["isin"] == "IE00B4L5Y983"                              # remplit les 3 critères, frais 0,20 %
    assert all(c.get("motif") for c in cands)
    assert cpf.classer_etf("monde", False, "PEA")[0]["pea"]                 # en PEA, l'éligible passe devant


def test_ajustement_refuse_au_dela_du_risque_maximum(client_type, monkeypatch):
    p = cp.calculer_profil(client_type)
    ok, _, _ = cpf.verifier_ajustement(client_type, p, 3, {"actions": 0.10, "obligations": 0.0})
    assert ok                                                        # 55 % d'actions : 9,8 %, sous le maximum de 10 %
    monkeypatch.setitem(cpf.PROFILS[3], "vol", (0.07, 0.09))
    ok, msg, _ = cpf.verifier_ajustement(client_type, p, 3, {"actions": 0.10, "obligations": 0.0})
    assert not ok and "volatilité" in msg
    e = {**client_type, **EXPERT}
    ok, msg, _ = cpf.verifier_ajustement(e, cp.calculer_profil(e), 5, {"actions": 0.10, "obligations": 0.0})
    assert not ok and "monétaire" in msg
    with pytest.raises(cpf.AjustementRefuse):
        cpf.allocation_cible(3, {"actions": 0.2})


def test_fil_de_decision_complet(client_type):
    x = reco(client_type, meta={"date_signature": "2026-11-18", "reference": "RA-2026-001"})
    assert [e["n"] for e in x["fil"]] == list(range(1, 10))
    assert all(e["titre"] and e["resultat"] and e["regle"] for e in x["fil"])
    assert set(x["lignes"]) == set(x["portefeuille"])
    assert all(x["lignes"][i]["raison"] for i in x["portefeuille"])


def test_enveloppe(client_type):
    assert cpf.choisir_enveloppe(client_type, 3)[0] == "assurance-vie"
    assert cpf.choisir_enveloppe({**client_type, "objectif": "valorisation"}, 4)[0] == "PEA"
    assert cpf.choisir_enveloppe({**client_type, "enveloppe_souhaitee": "CTO"}, 1)[0] == "CTO"


def test_reequilibrage():
    cible = {"IE00B4L5Y983": 0.5, "IE00B4WXJJ64": 0.5}
    assert cpf.alerte_reequilibrage(cible, {"IE00B4L5Y983": 0.57, "IE00B4WXJJ64": 0.43})
    assert not cpf.alerte_reequilibrage(cible, {"IE00B4L5Y983": 0.53, "IE00B4WXJJ64": 0.47})


# ------------------------------------------------------------------ Conformité
def test_controles_conformes_sans_derogation(client_type):
    p = cp.calculer_profil(client_type)
    x = cpf.recommander(client_type, p)
    assert cc.synthese(cc.controler(client_type, p, x, {}, "2026-11-18")) == "ok"


def test_derogation_sans_motif_bloquante(client_type):
    p = cp.calculer_profil(client_type)
    dec = {"ajustements": {"actions": -0.05, "obligations": 0.0}}
    x = cpf.recommander(client_type, p, None, dec["ajustements"])
    assert cc.synthese(cc.controler(client_type, p, x, dec, "2026-11-18")) == "bloquant"
    dec["motif_ajustement"] = "Le client souhaite réduire son exposition"
    assert cc.synthese(cc.controler(client_type, p, x, dec, "2026-11-18")) != "bloquant"


def test_questionnaire_non_signe_bloquant(client_type):
    p = cp.calculer_profil(client_type)
    x = cpf.recommander(client_type, p)
    assert cc.synthese(cc.controler(client_type, p, x, {}, None)) == "bloquant"


def test_dossiers_demo_et_revue():
    cc.creer_demo()
    liste = cc.lister()
    assert len(liste) == len(cc.DEMO)
    assert any(cc.revue_due(d) for d in liste)
    assert all(d["reference"].startswith("RA-") for d in liste)


# ------------------------------------------------------------------ Analyses
def test_simulation_coherente(client_type):
    x = reco(client_type)
    s = ca.simuler(x["portefeuille"], x["enveloppe"], 300_000, 0, 0, 10, 400_000, n=2000)
    assert s["p10"][-1] < s["p50"][-1] < s["p90"][-1]
    assert 0 <= s["proba_cible"] <= 1
    retraits = ca.simuler(x["portefeuille"], x["enveloppe"], 300_000, 0, 3_000, 15, 0, n=2000)
    assert retraits["proba_epuisement"] is not None


def test_frais_contrat_hors_fonds_euros(client_type):
    x = reco(client_type)
    assert ca.frais_contrat(x["portefeuille"], "assurance-vie") < 0.006
    assert ca.frais_contrat(x["portefeuille"], "CTO") == 0


def test_fiscalite(client_type):
    x = reco(client_type)
    res = ca.comparer_enveloppes(x["portefeuille"], 300_000, 0, 10, "couple")
    assert sum(r["meilleur"] for r in res) == 1
    cto = next(r for r in res if r["enveloppe"] == "CTO")
    assert abs(cto["taux"] - 0.314) < 1e-9


def test_classement_etf_coherent_partout():
    """Pour chaque poche, enveloppe et préférence : aucune donnée inconnue, et un motif exact (pas « frais plus élevés » à frais égaux)."""
    import calcul_portefeuille as cpf, donnees
    u = donnees.univers()
    for sc in u[u["type"] == "fonds"]["sous_classe"].unique():
        for env in ("CTO", "PEA", "assurance-vie"):
            for durable in (False, True):
                res = cpf.classer_etf(sc, durable, env)
                for k, c in enumerate(res):
                    assert all(v is not None for v in c["criteres"].values()), (sc, c["nom"])
                    assert c["motif"]
                    if k and c["motif"] == "frais plus élevés":
                        assert c["ter"] > res[0]["ter"], (sc, c["nom"])


def test_sans_preference_durable_le_pea_prime_sur_la_version():
    """Client sans préférence durable en PEA : l'ETF émergent éligible au PEA (version ESG) passe devant les versions non éligibles."""
    import calcul_portefeuille as cpf
    res = cpf.classer_etf("emergents", False, "PEA")
    assert res[0]["pea"] and res[0]["version"] == "durable"
    res = cpf.classer_etf("emergents", False, "CTO")
    assert res[0]["version"] == "standard"
