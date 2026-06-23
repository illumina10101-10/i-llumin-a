"""
Raccoglie partite del giorno + quote + pronostico statistico da API-Football.
Free tier: 100 chiamate/giorno. Key gratis su dashboard.api-football.com
Env: FOOTBALL_API_KEY
Output: JSON con partite reali, quote reali, forma squadre.
"""
import os, json, sys
from datetime import date, timedelta

import requests, certifi
try:
    import truststore  # solo Windows locale (Python 3.15 SSL)
    truststore.inject_into_ssl()
except ImportError:
    pass  # cloud Linux: certifi basta
from dotenv import load_dotenv
load_dotenv()

API = "https://v3.football.api-sports.io"
KEY = os.environ.get("FOOTBALL_API_KEY", "")
HEAD = {"x-apisports-key": KEY}

# Priorita: Mondiale=1, Champions=2, Serie A=135, Premier=39, Liga=140, Bundes=78, Ligue1=61
# Sempre attive (estate): Brasileiro=71, MLS=253, Euro=4
TOP_LEAGUES = [1, 2, 4, 135, 39, 140, 78, 61, 71, 253]


def _get(path, params):
    r = requests.get(f"{API}/{path}", headers=HEAD, params=params,
                     verify=certifi.where(), timeout=20)
    r.raise_for_status()
    return r.json().get("response", [])


def fetch():
    if not KEY:
        return {"errore": "FOOTBALL_API_KEY mancante"}

    today = date.today().isoformat()
    out = {"data": today, "partite": []}

    # Partite di oggi nei campionati top
    fixtures = []
    try:
        allf = _get("fixtures", {"date": today})
        fixtures = [f for f in allf if f["league"]["id"] in TOP_LEAGUES]
        # se nessuna oggi, prova domani
        if not fixtures:
            tomorrow = (date.today() + timedelta(days=1)).isoformat()
            allf = _get("fixtures", {"date": tomorrow})
            fixtures = [f for f in allf if f["league"]["id"] in TOP_LEAGUES]
            out["data"] = tomorrow
    except Exception as e:
        return {"errore": f"fixtures: {e}"}

    # Prendi max 4 partite, arricchisci con quote multiple + analisi
    for f in fixtures[:4]:
        fid = f["fixture"]["id"]
        home = f["teams"]["home"]["name"]
        away = f["teams"]["away"]["name"]
        league = f["league"]["name"]
        match = {"home": home, "away": away, "league": league,
                 "ora": f["fixture"]["date"][11:16], "quote": {}}

        # Quote multiple in UNA chiamata (tutti i bet del primo bookmaker)
        try:
            odds = _get("odds", {"fixture": fid})
            if odds and odds[0].get("bookmakers"):
                bets = odds[0]["bookmakers"][0]["bets"]
                bm = {b["id"]: b["values"] for b in bets}
                # 1X2
                if 1 in bm:
                    match["quote"]["1X2"] = {v["value"]: v["odd"] for v in bm[1]}
                # Over/Under 2.5 (bet 5)
                if 5 in bm:
                    ou = {v["value"]: v["odd"] for v in bm[5] if v["value"] in ("Over 2.5", "Under 2.5")}
                    if ou:
                        match["quote"]["OverUnder"] = ou
                # Both Teams Score (bet 8)
                if 8 in bm:
                    match["quote"]["GolGol"] = {v["value"]: v["odd"] for v in bm[8]}
                # Double Chance (bet 12)
                if 12 in bm:
                    match["quote"]["DoppiaChance"] = {v["value"]: v["odd"] for v in bm[12]}
        except Exception:
            pass

        # Analisi statistica completa
        try:
            pred = _get("predictions", {"fixture": fid})
            if pred:
                p = pred[0]
                pr = p["predictions"]
                comp = p.get("comparison", {})
                match["analisi"] = {
                    "vincente_atteso": pr.get("winner", {}).get("name"),
                    "consiglio_api": pr.get("advice"),
                    "percent_1X2": pr.get("percent"),
                    "gol_attesi": {"casa": pr.get("goals", {}).get("home"),
                                   "ospite": pr.get("goals", {}).get("away")},
                    "under_over": pr.get("under_over"),
                    "forma_casa": p["teams"]["home"].get("league", {}).get("form", "")[-5:],
                    "forma_ospite": p["teams"]["away"].get("league", {}).get("form", "")[-5:],
                    "forza_attacco": {"casa": comp.get("att", {}).get("home"),
                                      "ospite": comp.get("att", {}).get("away")},
                    "forza_difesa": {"casa": comp.get("def", {}).get("home"),
                                     "ospite": comp.get("def", {}).get("away")},
                }
        except Exception:
            pass

        out["partite"].append(match)

    return out


if __name__ == "__main__":
    print(json.dumps(fetch(), ensure_ascii=False, indent=2))
