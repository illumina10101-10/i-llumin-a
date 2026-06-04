"""
Raccoglie contenuto reale e verificabile per il video del giorno.
Fonti: Wikipedia Accadde Oggi + Google News IT + ScienceDaily RSS
Output: JSON con fatti reali da passare al modello LLM.
"""
import json, sys, re
from datetime import date
from xml.etree import ElementTree as ET

import requests, certifi, truststore
truststore.inject_into_ssl()  # fix Python 3.15 SSL cert validation
from dotenv import load_dotenv
load_dotenv()

today = date.today()
month, day = today.month, today.day
result = {
    "data_oggi": today.strftime("%d/%m/%Y"),
    "accadde_oggi": [],
    "notizie": [],
    "scienza": []
}

# ── 1. Wikipedia "Accadde Oggi" ─────────────────────────────────────────────
try:
    url = f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{month}/{day}"
    r = requests.get(url, timeout=10, verify=certifi.where(),
                     headers={"User-Agent": "I-llumin-A-Bot/1.0"})
    events = r.json().get("events", [])
    # Prendi i 6 eventi piu interessanti (con piu pagine Wikipedia = piu rilevanti)
    events_sorted = sorted(events, key=lambda e: len(e.get("pages", [])), reverse=True)[:6]
    for e in events_sorted:
        pages = e.get("pages", [])
        subject = pages[0]["titles"]["normalized"] if pages else ""
        result["accadde_oggi"].append({
            "anno": e.get("year", ""),
            "fatto": e.get("text", "")[:250],
            "soggetto": subject
        })
except Exception as ex:
    result["accadde_oggi"].append({"errore": str(ex)})

# ── 2. Google News RSS italiano ─────────────────────────────────────────────
try:
    rss = requests.get("https://news.google.com/rss?hl=it&gl=IT&ceid=IT:it",
                       timeout=10, verify=certifi.where())
    tree = ET.fromstring(rss.content)
    for item in tree.findall(".//item")[:8]:
        title = item.findtext("title", "").split(" - ")[0]  # rimuovi fonte
        pub = item.findtext("pubDate", "")[:16]
        result["notizie"].append({"titolo": title, "data": pub})
except Exception as ex:
    result["notizie"].append({"errore": str(ex)})

# ── 3. ScienceDaily RSS (scoperte scientifiche recenti) ─────────────────────
try:
    rss = requests.get("https://www.sciencedaily.com/rss/top/science.xml",
                       timeout=10, verify=certifi.where())
    tree = ET.fromstring(rss.content)
    for item in tree.findall(".//item")[:6]:
        title = item.findtext("title", "")
        desc = item.findtext("description", "")
        # Rimuovi tag HTML
        desc_clean = re.sub(r"<[^>]+>", "", desc)[:300]
        result["scienza"].append({"titolo": title, "abstract": desc_clean})
except Exception as ex:
    result["scienza"].append({"errore": str(ex)})

print(json.dumps(result, ensure_ascii=False, indent=2))
