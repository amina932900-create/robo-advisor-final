"""Chaque écran s'affiche sans erreur pour chaque client de démonstration, en français et en anglais."""
import pytest
from streamlit.testing.v1 import AppTest

import calcul_conformite

PAGES = ["tableau", "questionnaire", "recommandation", "analyses", "livrables", "methodologie"]


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_tous_les_ecrans(langue):
    calcul_conformite.creer_demo()
    for d in calcul_conformite.lister():
        at = AppTest.from_file("../app.py", default_timeout=300)
        at.session_state["langue"] = langue
        at.session_state["ref"] = d["reference"]
        for p in PAGES:
            at.session_state["_cible"] = p
            at.run()
            assert not at.exception, (d["reference"], p, [e.value for e in at.exception])


def test_ajustement_et_motif():
    calcul_conformite.creer_demo()
    at = AppTest.from_file("../app.py", default_timeout=300)
    at.session_state["ref"] = "RA-2026-014"
    at.session_state["_cible"] = "recommandation"
    at.run()
    at.slider(key="w_actions").set_value(-5).run()
    d = calcul_conformite.charger("RA-2026-014")
    assert d["decisions"]["ajustements"]["actions"] == -0.05
    assert any("Bloquant" in m.value for m in at.markdown)
    at.text_input(key="w_motif_ajustement").input("Le client souhaite réduire son exposition").run()
    assert calcul_conformite.charger("RA-2026-014")["decisions"]["motif_ajustement"]
