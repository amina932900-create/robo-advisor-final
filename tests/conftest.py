"""Configuration des tests : cours fictifs (aucun appel internet) et dossiers dans un répertoire temporaire."""
import os
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
os.environ["ROBO_DONNEES"] = "demo"


@pytest.fixture(autouse=True)
def dossiers_temporaires(tmp_path, monkeypatch):
    import calcul_conformite
    monkeypatch.setattr(calcul_conformite, "DOSSIER", tmp_path / "dossiers")
    yield


@pytest.fixture
def client_type():
    """Questionnaire complet d'un client équilibré (profil 3), assurance-vie, horizon long."""
    return {"montant": 300_000, "age": 45, "situation_familiale": "couple", "revenus": "100-200k", "patrimoine": 900_000,
            "epargne_precaution": True, "credits": False, "statut_pro": "salarie_cdi", "stabilite_revenus": "stables",
            "objectif": "retraite", "horizon": ">8", "priorite": "equilibre", "rendement_attendu": "4-5", "versement_mensuel": 500,
            "cible": 0, "besoin_liquidite": False, "quiz_etf": True, "quiz_taux": False, "quiz_diversification": True,
            "quiz_perte": True, "quiz_fonds_euros": False, "anciennete": "2-5", "niveau": "intermediaire", "produits_detenus": ["etf"],
            "reaction_baisse": "attendre", "perte_max": "10", "choix_portefeuille": "C", "durabilite": "aucune", "zone": "Monde",
            "enveloppe_souhaitee": "auto"}
