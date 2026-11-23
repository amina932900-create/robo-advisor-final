"""Tests des documents : PDF, Excel, questionnaire vierge, e-mail et garde-fou anti-chiffres inventés."""
import io

from openpyxl import load_workbook

import calcul_conformite as cc
import livrables


def _ctx(langue="fr"):
    cc.creer_demo()
    return livrables.contexte(cc.charger("RA-2025-021"), langue)


def test_declaration_pdf():
    for lg in ("fr", "en"):
        b = livrables.declaration_pdf(_ctx(lg))
        assert b[:4] == b"%PDF" and len(b) > 5_000


def test_questionnaire_vierge():
    assert livrables.questionnaire_vierge("fr")[:4] == b"%PDF"


def test_excel():
    contenu, ext = livrables.excel(_ctx())
    wb = load_workbook(io.BytesIO(contenu))
    assert ext in ("xlsx", "xlsm") and len(wb.sheetnames) == 6


def test_email_modele_et_garde_fou(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    ctx = _ctx()
    objet, corps, source = livrables.email_client(ctx)
    assert "RA-2025-021" in objet and source.startswith("modèle")
    assert livrables.chiffres_inventes(corps, ctx) == []
    assert livrables.chiffres_inventes(corps + " Rendement garanti de 12,7 % par an.", ctx) == [12.7]
