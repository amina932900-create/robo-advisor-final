"""
telecharger_prix.py — Télécharge les cours réels et crée data/prix_snapshot.csv (copie locale lue par l'outil).

À lancer sur votre ordinateur (les serveurs gratuits sont souvent bloqués par Yahoo), puis pousser le fichier sur GitHub :
    python telecharger_prix.py                 # télécharge et écrit le snapshot
    python telecharger_prix.py --maj-univers   # écrit aussi dans univers.csv les tickers trouvés à partir des ISIN

Lignes téléchargées : tous les ETF et fonds cotés de data/univers.csv (pas le fonds en euros ni la SCPI, qui ont un taux)
et les actions européennes cotées en euros de data/univers_titres.csv (satellite). Une colonne par ticker Yahoo.
"""

import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

DOSSIER = Path(__file__).resolve().parent
UNIVERS = DOSSIER / "data" / "univers.csv"
TITRES = DOSSIER / "data" / "univers_titres.csv"
SNAPSHOT = DOSSIER / "data" / "prix_snapshot.csv"
DEBUT = "2005-01-01"
PLACES_EURO = (".PA", ".DE", ".AS", ".MC", ".MI", ".IR", ".BR", ".HE", ".LS", ".VI")


def chercher_ticker(isin: str) -> str | None:
    """Cherche sur Yahoo un ticker correspondant à l'ISIN (privilégie les cotations en euros)."""
    try:
        resultats = yf.Search(isin, max_results=8).quotes
    except Exception as e:
        print(f"  recherche impossible pour {isin} : {e}")
        return None
    preferes = [q for q in resultats if str(q.get("symbol", "")).endswith(PLACES_EURO + (".F",))]
    return (preferes or resultats or [{}])[0].get("symbol")


def main(maj_univers: bool = False) -> None:
    u = pd.read_csv(UNIVERS, dtype=str, keep_default_na=False)
    tickers = {}
    for _, l in u[u["taux_annuel"] == ""].iterrows():
        t = l["ticker_yahoo"]
        if t in ("", "TODO"):
            print(f"Recherche du ticker de {l['nom']} ({l['isin']})…")
            t = chercher_ticker(l["isin"])
            print(f"  -> {t or 'introuvable'}")
            if t and maj_univers:
                u.loc[u["isin"] == l["isin"], "ticker_yahoo"] = t
        if t:
            tickers[l["isin"]] = t
    if TITRES.exists():
        t2 = pd.read_csv(TITRES, dtype=str, keep_default_na=False)
        t2 = t2[(t2["type"] == "action") & t2["sous_classe"].isin(["action_europe", "action_france"])]
        for _, l in t2[t2["ticker_yahoo"].str.endswith(PLACES_EURO)].iterrows():
            tickers[l["isin"]] = l["ticker_yahoo"]

    print(f"\nTéléchargement de {len(set(tickers.values()))} séries depuis {DEBUT}…")
    data = yf.download(sorted(set(tickers.values())), start=DEBUT, auto_adjust=True, progress=True, threads=True)
    close = data["Close"] if isinstance(data.columns, pd.MultiIndex) else data[["Close"]]
    close.index = pd.to_datetime(close.index).tz_localize(None)
    close = close.dropna(how="all").sort_index()

    print("\nBilan :")
    for isin, t in tickers.items():
        s = close[t].dropna() if t in close.columns else pd.Series(dtype=float)
        print(f"  {t:12s} {f'{len(s):5d} jours depuis {s.index[0].date()}' if len(s) else 'AUCUNE DONNÉE : corriger ticker_yahoo'}")
    close.round(6).to_csv(SNAPSHOT)
    print(f"\nÉcrit : {SNAPSHOT} ({close.shape[0]} dates × {close.shape[1]} séries)")
    if maj_univers:
        u.to_csv(UNIVERS, index=False)
        print("univers.csv mis à jour avec les tickers trouvés : relisez-le avant de le pousser.")


if __name__ == "__main__":
    main(maj_univers="--maj-univers" in sys.argv)
