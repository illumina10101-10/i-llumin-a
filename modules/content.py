"""
Genera script video con dati reali verificati.
Fonti: Wikipedia Accadde Oggi + Google News + ScienceDaily RSS + OpenRouter LLM.
"""
import os, json, re, logging
from datetime import date
from xml.etree import ElementTree as ET

import requests

logger = logging.getLogger(__name__)

# ── Fetch dati reali ─────────────────────────────────────────────────────────

def _fetch_real_content() -> dict:
    today = date.today()
    result = {
        "data_oggi": today.strftime("%d/%m/%Y"),
        "accadde_oggi": [],
        "notizie": [],
        "scienza": [],
    }

    session = requests.Session()
    session.headers["User-Agent"] = "I-llumin-A-Bot/2.0"

    # 1. Wikipedia On This Day
    try:
        r = session.get(
            f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{today.month}/{today.day}",
            timeout=10
        )
        events = r.json().get("events", [])
        events_sorted = sorted(events, key=lambda e: len(e.get("pages", [])), reverse=True)[:5]
        for e in events_sorted:
            pages = e.get("pages", [])
            subject = pages[0]["titles"]["normalized"] if pages else ""
            result["accadde_oggi"].append({
                "anno": e.get("year", ""),
                "fatto": e.get("text", "")[:250],
                "soggetto": subject,
            })
    except Exception as ex:
        logger.warning("Wikipedia OnThisDay fallito: %s", ex)

    # 2. Google News RSS italiano
    try:
        r = session.get("https://news.google.com/rss?hl=it&gl=IT&ceid=IT:it", timeout=10)
        tree = ET.fromstring(r.content)
        for item in tree.findall(".//item")[:6]:
            title = item.findtext("title", "").split(" - ")[0]
            result["notizie"].append({"titolo": title})
    except Exception as ex:
        logger.warning("Google News RSS fallito: %s", ex)

    # 3. ScienceDaily RSS
    try:
        r = session.get("https://www.sciencedaily.com/rss/top/science.xml", timeout=10)
        tree = ET.fromstring(r.content)
        for item in tree.findall(".//item")[:5]:
            title = item.findtext("title", "")
            desc = re.sub(r"<[^>]+>", "", item.findtext("description", ""))[:300]
            result["scienza"].append({"titolo": title, "abstract": desc})
    except Exception as ex:
        logger.warning("ScienceDaily RSS fallito: %s", ex)

    return result


def _load_used_topics() -> list[str]:
    """Carica topic usati oggi per evitare ripetizioni."""
    today_prefix = date.today().isoformat()
    path = "used_topics_today.txt"
    used = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(today_prefix + "|"):
                    used.append(line.split("|", 1)[1].lower())
    except FileNotFoundError:
        pass
    return used


def _save_used_topic(topic: str):
    today_prefix = date.today().isoformat()
    with open("used_topics_today.txt", "a", encoding="utf-8") as f:
        f.write(f"{today_prefix}|{topic}\n")


def _filter_used(data: dict, used_keywords: list[str]) -> dict:
    """Rimuove fisicamente dal JSON i topic già usati."""
    if not used_keywords:
        return data
    import copy
    d = copy.deepcopy(data)
    for kw in used_keywords:
        key_words = kw.split()[:2]
        first_word = key_words[0] if key_words else ""
        if not first_word:
            continue
        d["scienza"] = [
            s for s in d["scienza"]
            if first_word not in s.get("titolo", "").lower()
            and first_word not in s.get("abstract", "").lower()
        ]
        d["accadde_oggi"] = [
            e for e in d["accadde_oggi"]
            if first_word not in e.get("fatto", "").lower()
        ]
    return d


def _build_prompt(real_data: dict) -> str:
    data_json = json.dumps(real_data, ensure_ascii=False)
    today = date.today().strftime("%d/%m/%Y")
    return (
        f"Sei il narratore di un canale YouTube italiano che spiega fatti reali. Data: {today}.\n\n"
        f"DATI REALI VERIFICATI:\n{data_json}\n\n"
        "COMPITO: Scegli IL fatto piu interessante tra quelli forniti. Spiegalo in italiano in 35-42 secondi.\n"
        "Usa SOLO fatti presenti nei dati. Non inventare nomi, statistiche o studi.\n\n"
        "STRUTTURA VOICEOVER (95-110 parole):\n"
        "1. HOOK (3s): stato sorprendente o domanda provocatoria, max 8 parole. NO 'oggi' o 'sapevi che'\n"
        "2. CONTESTO (8s): quando, dove, chi - solo dati presenti sopra\n"
        "3. FATTO CENTRALE (15s): spiega il meccanismo in modo che chiunque capisca\n"
        "4. PERCHE CONTA OGGI (10s): impatto concreto sulla vita di chi guarda\n"
        "5. CHIUSURA ENGAGEMENT (5s): fai UNA domanda diretta che invita a commentare.\n"
        "   Esempi: 'Tu lo sapevi? Scrivi SI o NO.' / 'Cosa ne pensi? Dimmelo.' / 'Ti ha sorpreso? Commenta.'\n"
        "   NON usare solo 'salva questo video' — serve la domanda per i commenti.\n\n"
        "REGOLE VOCE (neural TTS italiano):\n"
        "- Numeri in lettere: 'millenovecentoquarantuno' non '1941'\n"
        "- Zero abbreviazioni\n"
        "- Frasi max 9 parole, punto dopo ogni concetto\n"
        "- Una sola pausa con '...' prima del dato piu impattante\n"
        "- MAX un '!' per video\n\n"
        "TITOLO YOUTUBE: max 55 char. Usa formato curiosity gap:\n"
        "- Per scienza: 'La scoperta che cambia [X]' o '[Anno]: quando [fatto shock]'\n"
        "- Per storia: 'Il giorno in cui [evento] cambiò tutto'\n"
        "- Per notizie: 'Perché [fatto] interessa anche te'\n"
        "NON mettere #Shorts nel titolo JSON (lo aggiunge il sistema).\n\n"
        "DESCRIPTION (primi 100 char visibili nel feed): inizia con UNA domanda che spinge a commentare.\n"
        "Esempio: 'Lo sapevi? Lascia un commento! 👇'\n\n"
        "CATEGORIA: indica il tipo di contenuto nel campo 'categoria':\n"
        "- 'scienza' per scoperte scientifiche\n"
        "- 'storia' per fatti storici\n"
        "- 'tecnologia' per AI e tech\n"
        "- 'attualita' per notizie\n\n"
        "Hashtag: esattamente 5. Usa sempre #Shorts + #imparaconme, poi 3 topic-specific:\n"
        "- scienza: #scienza #curiosita #facts\n"
        "- storia: #storia #curiosita #didyouknow\n"
        "- tecnologia: #AITech #tecnologia #futuro\n"
        "- attualita: #notizie #viral #fyp\n\n"
        "Rispondi SOLO con JSON valido su una riga, zero markdown:\n"
        '{"trending_topic":"nome breve","tipo":"storia|scienza|notizia|tecnologia","categoria":"scienza|storia|tecnologia|attualita",'
        '"hook":"max 8 parole","voiceover":"testo 95-110 parole con domanda finale per commenti",'
        '"pexels_keywords":["kw1_english","kw2_english","kw3_english"],'
        '"title_youtube":"titolo curiosity gap max 55 char senza #Shorts",'
        '"description":"domanda per commenti max 100 char",'
        '"hashtags":["#Shorts","#imparaconme","#tag1","#tag2","#tag3"]}'
    )


# ── Generatori LLM ────────────────────────────────────────────────────────────

def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1])
    m = re.search(r'\{[\s\S]*\}', text)
    if m:
        text = m.group(0)
    return json.loads(text)


def generate_with_openrouter(prompt: str) -> dict:
    models = [
        "openai/gpt-oss-120b:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "google/gemma-4-31b-it:free",
        "nousresearch/hermes-3-llama-3.1-405b:free",
        "openai/gpt-oss-20b:free",
        "moonshotai/kimi-k2.6:free",
        "qwen/qwen3-next-80b-a3b-instruct:free",
        "google/gemma-4-26b-a4b-it:free",
    ]
    headers = {
        "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
        "HTTP-Referer": "https://github.com/i-llumin-a",
        "Content-Type": "application/json; charset=utf-8",
        "X-Title": "I-llumin-A",
    }
    for model in models:
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json={"model": model, "messages": [{"role": "user", "content": prompt}],
                      "temperature": 0.7, "max_tokens": 1000},
                timeout=90,
            )
            r.raise_for_status()
            data = r.json()
            choices = data.get("choices") or []
            if not choices:
                continue
            text = choices[0]["message"]["content"].strip()
            result = _parse_json(text)
            logger.info("Script generato con %s. Topic: %s", model, result.get("trending_topic"))
            return result
        except Exception as e:
            logger.warning("Modello %s fallito: %s", model, e)
    raise RuntimeError("Tutti i modelli OpenRouter hanno fallito o sono rate-limited")


def generate_with_claude(prompt: str) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
    )
    text = next((b.text for b in reversed(response.content) if hasattr(b, "text")), None)
    return _parse_json(text)


def generate_script(niche: str = "", affiliate_product: str = "", affiliate_url: str = "") -> dict:
    """Entry point: fetch dati reali → genera script verificato."""
    logger.info("Raccogliendo dati reali (Wikipedia + News + Science)...")
    real_data = _fetch_real_content()

    used = _load_used_topics()
    if used:
        logger.info("Topic da escludere: %s", used)
        real_data = _filter_used(real_data, used)

    prompt = _build_prompt(real_data)

    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            script = generate_with_claude(prompt)
            _save_used_topic(script.get("trending_topic", ""))
            return script
        except Exception as e:
            logger.warning("Claude API fallita (%s), provo OpenRouter...", e)

    if os.environ.get("OPENROUTER_API_KEY"):
        script = generate_with_openrouter(prompt)
        _save_used_topic(script.get("trending_topic", ""))
        return script

    raise RuntimeError("Nessuna API key configurata")
