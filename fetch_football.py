"""
Raccoglie partite del giorno + quote + pronostico statistico da API-Football.
Free tier: 100 chiamate/giorno. Key gratis su dashboard.api-football.com
Env: FOOTBALL_API_KEY
Output: JSON con partite reali, quote reali, forma squadre.
"""
import os, json, sys
from datetime import date, timedelta

import requests, truststore, certifi
truststore.inject_into_ssl()
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

    # Prendi max 5 partite, arricchisci con quote + pronostico
    for f in fixtures[:5]:
        fid = f["fixture"]["id"]
        home = f["teams"]["home"]["name"]
        away = f["teams"]["away"]["name"]
        league = f["league"]["name"]
        match = {"home": home, "away": away, "league": league, "ora": f["fixture"]["date"][11:16]}

        # Quote 1X2 (bookmaker medio)
        try:
            odds = _get("odds", {"fixture": fid, "bet": 1})  # bet 1 = Match Winner
            if odds:
                vals = odds[0]["bookmakers"][0]["bets"][0]["values"]
                match["quote"] = {v["value"]: v["odd"] for v in vals}
        except Exception:
            pass

        # Pronostico statistico api-football
        try:
            pred = _get("predictions", {"fixture": fid})
            if pred:
                p = pred[0]["predictions"]
                match["pronostico"] = {
                    "vincente": p.get("winner", {}).get("name"),
                    "consiglio": p.get("advice"),
                    "percentuali": p.get("percent"),
                }
        except Exception:
            pass

        out["partite"].append(match)

    return out


if __name__ == "__main__":
    print(json.dumps(fetch(), ensure_ascii=False, indent=2))
