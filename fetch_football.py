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

    import time
    now_ts = time.time()
    today = date.today().isoformat()
    out = {"data": today, "partite": []}

    def _upcoming(flist):
        """Solo partite non ancora iniziate (status NS/TBD) con calcio d'inizio futuro."""
        res = []
        for f in flist:
            if f["league"]["id"] not in TOP_LEAGUES:
                continue
            status = f["fixture"]["status"]["short"]
            ts = f["fixture"].get("timestamp", 0)
            if status in ("NS", "TBD") and ts > now_ts + 600:  # almeno 10 min nel futuro
                res.append(f)
        # ordina per orario (le piu vicine prima)
        return sorted(res, key=lambda x: x["fixture"].get("timestamp", 0))

    # Cerca partite future: oggi, poi giorni successivi
    fixtures = []
    try:
        for d in range(0, 4):
            day = (date.today() + timedelta(days=d)).isoformat()
            allf = _get("fixtures", {"date": day})
            fixtures = _upcoming(allf)
            if fixtures:
                out["data"] = day
                break
    except Exception as e:
        return {"errore": f"fixtures: {e}"}

    # Prendi max 4 partite, arricchisci con quote multiple + analisi
    for f in fixtures[:4]:
        fid = f["fixture"]["id"]
        home = f["teams"]["home"]["name"]
        away = f["teams"]["away"]["name"]
        league = f["league"]["name"]
        match = {"home": home, "away": away, "league": league,
                 "ora": f["fixture"]["date"][11:16], "quote": {},
                 "home_logo": f["teams"]["home"].get("logo", ""),
                 "away_logo": f["teams"]["away"].get("logo", "")}

        # Mercati leggibili in italiano (id api-football -> nome)
        MERCATI = {
            1: "Esito 1X2", 5: "Over/Under Gol", 6: "Over/Under 1° Tempo",
            8: "Gol Gol", 12: "Doppia Chance", 13: "Vincente 1° Tempo",
            9: "Handicap", 21: "Pari/Dispari Gol", 7: "Primo/Secondo Tempo",
            45: "Calci d'Angolo", 80: "Tiri in Porta", 85: "Fuorigioco",
        }
        # Costruisci lista GIOCATE con quota >= 1.90 (floor in CODICE, non solo prompt)
        giocate = []
        try:
            odds = _get("odds", {"fixture": fid})
            if odds and odds[0].get("bookmakers"):
                bets = odds[0]["bookmakers"][0]["bets"]
                for b in bets:
                    mname = MERCATI.get(b["id"])
                    if not mname:
                        continue
                    for v in b["values"]:
                        try:
                            q = float(v["odd"])
                        except (ValueError, TypeError):
                            continue
                        # SOLO quote appetibili 1.90 - 4.50
                        if 1.90 <= q <= 4.50:
                            giocate.append({
                                "mercato": mname,
                                "selezione": v["value"],
                                "quota": v["odd"],
                            })
        except Exception:
            pass
        # ordina per quota crescente (le piu probabili prima)
        match["giocate_valore"] = sorted(giocate, key=lambda x: float(x["quota"]))[:12]

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
