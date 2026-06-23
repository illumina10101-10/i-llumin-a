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
        events_sorted = sorted(events, key=lambda e: len(e.get("pages", [])), reverse=True)[:3]
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

    # 3. ScienceDaily — top science + strange/offbeat + animali (filone "wow" che converte)
    science_feeds = [
        "https://www.sciencedaily.com/rss/strange_offbeat.xml",   # bizzarro = piu virale
        "https://www.sciencedaily.com/rss/plants_animals.xml",    # animali (filone polpo)
        "https://www.sciencedaily.com/rss/top/science.xml",
    ]
    for feed in science_feeds:
        try:
            r = session.get(feed, timeout=10)
            tree = ET.fromstring(r.content)
            for item in tree.findall(".//item")[:4]:
                title = item.findtext("title", "")
                desc = re.sub(r"<[^>]+>", "", item.findtext("description", ""))[:300]
                result["scienza"].append({"titolo": title, "abstract": desc})
        except Exception as ex:
            logger.warning("ScienceDaily feed %s fallito: %s", feed, ex)

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


_STOPWORDS = {
    "del","della","dello","di","il","la","lo","le","gli","una","uno","un",
    "the","and","of","in","at","by","for","with","from","that","this",
    "was","were","has","have","had","been","not","are","its","their",
    "also","after","when","which","what","who","how","per","con","che",
    "nel","nei","tra","sul","sulla","sulle","sui","agli","alle","alla",
}

def _filter_used(data: dict, used_keywords: list[str]) -> dict:
    """
    Rimuove dal JSON i topic già usati oggi.
    Estrae parole significative (>3 char, non stopword, non numeri) da ogni topic usato.
    Filtra qualsiasi entry che contiene ALMENO UNA di quelle parole.
    """
    if not used_keywords:
        return data
    import copy, re
    d = copy.deepcopy(data)

    # Estrai tutte le keyword significative da tutti i topic usati
    all_keywords = set()
    for topic in used_keywords:
        words = re.sub(r'\d+', '', topic.lower()).split()
        for w in words:
            w = w.strip(".,;:!?-")
            if len(w) > 3 and w not in _STOPWORDS:
                all_keywords.add(w)

    if not all_keywords:
        return d

    def _contains_any(text: str) -> bool:
        text_lower = text.lower()
        return any(kw in text_lower for kw in all_keywords)

    d["scienza"] = [
        s for s in d["scienza"]
        if not _contains_any(s.get("titolo", "") + " " + s.get("abstract", ""))
    ]
    d["accadde_oggi"] = [
        e for e in d["accadde_oggi"]
        if not _contains_any(e.get("fatto", "") + " " + e.get("soggetto", ""))
    ]
    d["notizie"] = [
        n for n in d["notizie"]
        if not _contains_any(n.get("titolo", ""))
    ]
    logger.info("Filtro topic usati: keywords=%s", sorted(all_keywords))
    return d


def _build_prompt(real_data: dict) -> str:
    data_json = json.dumps(real_data, ensure_ascii=False)
    today = date.today().strftime("%d/%m/%Y")
    return (
        f"Sei il narratore di un canale YouTube italiano che spiega fatti reali. Data: {today}.\n\n"
        f"DATI REALI VERIFICATI:\n{data_json}\n\n"
        "COMPITO: Scegli IL fatto piu SCONVOLGENTE tra quelli forniti. Un fatto solo. "
        "Crea uno short ULTRA-CORTO da 15-20 secondi che la gente guarda fino in fondo e RIGUARDA.\n"
        "Usa SOLO fatti presenti nei dati. Non inventare nomi, statistiche o studi.\n\n"
        "PRIORITA SCELTA TOPIC (i dati del canale dicono cosa funziona):\n"
        "1. SCIENZA e NATURA shock (animali assurdi, spazio, corpo umano) — categoria 'scienza'\n"
        "2. MISTERI e fatti inspiegabili/disastri curiosi — alta curiosita\n"
        "3. SOLO se niente di meglio: fatti storici (ma evita storia oscura e poco nota)\n"
        "EVITA: politici minori, battaglie sconosciute, fatti che richiedono contesto storico.\n"
        "PREFERISCI: cose che fanno dire 'COSA?! non lo sapevo' a chiunque, senza prerequisiti.\n\n"
        "VIETATO nel titolo: NON iniziare MAI con 'Il giorno in cui'. Varia ogni titolo. "
        "Usa formati diversi: domanda, numero shock, affermazione assurda.\n\n"
        "REGOLA D'ORO: durata corta = guardato intero = algoritmo spinge. NO riempitivi. Ogni parola conta.\n\n"
        "STRUTTURA VOICEOVER (45-60 parole MASSIMO, 15-20 secondi):\n"
        "1. HOOK SHOCK (2s): il fatto piu assurdo SUBITO, max 7 parole. La rivelazione, non l'introduzione.\n"
        "   NO 'oggi', NO 'sapevi che', NO 'in questo video'. Spara il fatto shock in faccia.\n"
        "2. SPIEGAZIONE RAPIDA (10s): 2-3 frasi che spiegano il fatto. Concrete, sorprendenti.\n"
        "3. LOOP (3s): l'ultima frase deve collegarsi alla prima, così riguardano senza accorgersi.\n"
        "   La fine prepara l'inizio. Esempio: se inizi 'Questo animale non muore mai', "
        "finisci 'Ecco perche non muore mai' così il loop e perfetto.\n\n"
        "HOOK_TEXT: testo GIGANTE da mostrare sullo schermo nei primi 2 secondi (oltre alla voce). "
        "Max 5 parole, tutto maiuscolo, choc. Esempio: 'NON MUORE MAI' o 'BRUCIO PER 50 ANNI'.\n\n"
        "REGOLE VOCE (neural TTS italiano):\n"
        "- Numeri in lettere: 'millenovecentoquarantuno' non '1941'\n"
        "- Zero abbreviazioni\n"
        "- Frasi max 8 parole, punto dopo ogni concetto\n"
        "- Ritmo incalzante, energico\n"
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
        "HASHTAG — scegli esattamente 5, TUTTI obbligatori:\n"
        "Sempre: #Shorts e #imparaconme\n"
        "Poi 3 specifici in base al topic (NON usare #tag1 o placeholder):\n"
        "Se scienza: #scienza #curiosita #facts\n"
        "Se storia: #storia #curiosita #didyouknow\n"
        "Se tecnologia/AI: #AITech #tecnologia #futuro\n"
        "Se attualita/notizie: #notizie #viral #fyp\n\n"
        "ESEMPIO OUTPUT COMPLETO per un topic di scienza (NOTA durata corta!):\n"
        '{"trending_topic":"Cometa aliena con metano","tipo":"scienza","categoria":"scienza",'
        '"hook":"Una cometa aliena ci ha portato metano.","hook_text":"COMETA ALIENA",'
        '"voiceover":"Una cometa aliena ci ha portato metano. Viene da un altro sistema solare. '
        'Il telescopio Webb ha trovato gas mai visti prima. Materiale di una stella lontana, ora vicino a noi. '
        'Ecco perche questa cometa aliena e speciale.",'
        '"pexels_keywords":["comet space","telescope","astronomy"],'
        '"title_youtube":"La cometa aliena che ci ha portato metano",'
        '"description":"Lo sapevi? Scrivi SI o NO nei commenti! \U0001f447",'
        '"hashtags":["#Shorts","#imparaconme","#scienza","#curiosita","#facts"]}\n\n'
        "ESEMPIO per storia:\n"
        '{"hashtags":["#Shorts","#imparaconme","#storia","#curiosita","#didyouknow"]}\n\n'
        "ESEMPIO per tecnologia:\n"
        '{"hashtags":["#Shorts","#imparaconme","#AITech","#tecnologia","#futuro"]}\n\n'
        "Ricorda: voiceover 45-60 parole MAX, formato loop, hook_text gigante. "
        "Ora genera il JSON completo per il topic scelto. SOLO JSON su una riga, zero markdown:"
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


_HASHTAG_BY_CAT = {
    "scienza":    ["#scienza", "#curiosita", "#facts"],
    "storia":     ["#storia", "#curiosita", "#didyouknow"],
    "tecnologia": ["#AITech", "#tecnologia", "#futuro"],
    "attualita":  ["#notizie", "#viral", "#fyp"],
}

def _normalize_script(s: dict) -> dict:
    """Garantisce 5 hashtag validi indipendente dal modello."""
    cat = (s.get("categoria") or s.get("tipo") or "scienza").lower()
    if cat in ("notizia", "news"):
        cat = "attualita"
    if cat not in _HASHTAG_BY_CAT:
        cat = "scienza"
    s["categoria"] = cat

    tags = s.get("hashtags") or []
    # tieni solo hashtag veri (no placeholder tipo #tag1)
    tags = [t for t in tags if isinstance(t, str) and t.startswith("#")
            and not re.match(r"#tag\d", t.lower()) and len(t) > 2]

    base = ["#Shorts", "#imparaconme"]
    forced = base + _HASHTAG_BY_CAT[cat]
    # unisci: prima i forced, poi extra del modello, dedup, max 5
    seen, final = set(), []
    for t in forced + tags:
        tl = t.lower()
        if tl not in seen:
            seen.add(tl)
            final.append(t)
        if len(final) == 5:
            break
    s["hashtags"] = final
    return s


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
            result = _normalize_script(_parse_json(text))
            logger.info("Script generato con %s. Topic: %s | hashtags: %s",
                        model, result.get("trending_topic"), result.get("hashtags"))
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
    return _normalize_script(_parse_json(text))


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
