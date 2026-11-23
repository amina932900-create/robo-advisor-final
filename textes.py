"""
textes.py — Mise en forme commune (nombres, pourcentages, dates) et petits textes partagés, en français et en anglais.

Les libellés des questions sont dans calcul_profil.py ; ceux des écrans sont écrits directement avec tr(fr, en).
"""

from __future__ import annotations

NOMS_ENVELOPPES = {
    "fr": {"assurance-vie": "Assurance-vie", "PEA": "PEA (+ compte-titres en complément)", "CTO": "Compte-titres"},
    "en": {"assurance-vie": "Life insurance", "PEA": "PEA (+ securities account)", "CTO": "Securities account"},
}
# Nom court de l'enveloppe d'UNE ligne (une ligne est soit dans le PEA, soit dans le compte-titres)
NOMS_COURTS = {
    "fr": {"assurance-vie": "Assurance-vie", "PEA": "PEA", "CTO": "Compte-titres"},
    "en": {"assurance-vie": "Life insurance", "PEA": "PEA", "CTO": "Securities account"},
}
CLASSES = {
    "fr": {"actions": "Actions", "obligations": "Obligations", "monetaire": "Monétaire et fonds en euros",
           "diversifiants": "Or et immobilier coté", "scpi": "SCPI", "actif": "Fonds actifs"},
    "en": {"actions": "Equities", "obligations": "Bonds", "monetaire": "Money market & euro fund",
           "diversifiants": "Gold & listed real estate", "scpi": "SCPI", "actif": "Active funds"},
}
NOTES = {
    "fr": {"tolerance": "Tolérance au risque", "horizon": "Horizon", "capacite": "Capacité à subir des pertes",
           "connaissances": "Connaissances et expérience"},
    "en": {"tolerance": "Risk tolerance", "horizon": "Horizon", "capacite": "Capacity to bear losses",
           "connaissances": "Knowledge & experience"},
}
AVERTISSEMENT = {
    "fr": "Projet pédagogique de M2 Banque-Finance : outil d'aide à la décision simulé, ce n'est pas un conseil en investissement réel.",
    "en": "Master's student project (Banking & Finance): simulated decision-support tool, not real investment advice.",
}


def nd(langue: str = "fr") -> str:
    return "n.d." if langue == "fr" else "n/a"


def pct_txt(x, d: int = 1, langue: str = "fr", signe: bool = False) -> str:
    """0.123 -> « 12,3 % » en français, « 12.3% » en anglais (n.d. si absent)."""
    if x is None or x != x:
        return nd(langue)
    txt = f"{x * 100:+.{d}f}" if signe else f"{x * 100:.{d}f}"
    return txt + "%" if langue == "en" else txt.replace(".", ",") + " %"


def nombre_txt(x, d: int = 2, langue: str = "fr") -> str:
    """1234.5 -> « 1 234,50 » en français, « 1,234.50 » en anglais."""
    if x is None or x != x:
        return nd(langue)
    txt = f"{x:,.{d}f}"
    return txt if langue == "en" else txt.replace(",", " ").replace(".", ",")


def eur_txt(x, langue: str = "fr", signe: bool = False) -> str:
    if x is None or x != x:
        return nd(langue)
    if langue == "en":
        return ("+" if signe and x >= 0 else "-" if x < 0 else "") + f"€{abs(x):,.0f}"
    return (f"{x:+,.0f} €" if signe else f"{x:,.0f} €").replace(",", " ")


MOIS = {"fr": ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."],
        "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]}


def date_txt(iso, langue: str = "fr") -> str:
    """« 2030-05-11 » -> « 11/05/2030 » (fr) ou « 11 May 2030 » (en) ; renvoie le texte tel quel s'il n'est pas une date."""
    s = str(iso or "")
    if len(s) < 10 or s[4] != "-":
        return s
    try:
        a, m, j = int(s[:4]), int(s[5:7]), int(s[8:10])
    except ValueError:
        return s
    return f"{j} {MOIS['en'][m - 1]} {a}" if langue == "en" else f"{j:02d}/{m:02d}/{a}"
