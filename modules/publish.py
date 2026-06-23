"""
Pubblica il video su TikTok, Instagram Reels e YouTube Shorts.
Ogni piattaforma ha il proprio fallback in caso di errore.
"""
import os
import re
import json
import time
import logging
import base64
from pathlib import Path

logger = logging.getLogger(__name__)


# ── TikTok ──────────────────────────────────────────────────────────────────

_TIKTOK_CACHE = "tiktok_token.json"

def _refresh_tiktok_token() -> str | None:
    """
    Rinnova access token TikTok. Usa refresh_token da cache file (se esiste, più recente)
    altrimenti da env. Salva il nuovo refresh_token in cache (TikTok lo ruota).
    """
    import requests, json as _json
    key = os.environ.get("TIKTOK_CLIENT_KEY")
    secret = os.environ.get("TIKTOK_CLIENT_SECRET")

    # refresh_token: priorità al cache file (aggiornato da run precedenti)
    refresh = None
    try:
        with open(_TIKTOK_CACHE, encoding="utf-8") as f:
            refresh = _json.load(f).get("refresh_token")
    except Exception:
        pass
    if not refresh:
        refresh = os.environ.get("TIKTOK_REFRESH_TOKEN")

    if not (refresh and key and secret):
        return None
    try:
        r = requests.post(
            "https://open.tiktokapis.com/v2/oauth/token/",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_key": key,
                "client_secret": secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh,
            },
            timeout=30,
        )
        data = r.json()
        if "access_token" in data:
            logger.info("TikTok: token rinnovato via refresh_token")
            # Salva il nuovo refresh_token (TikTok lo ruota) per il prossimo run
            try:
                with open(_TIKTOK_CACHE, "w", encoding="utf-8") as f:
                    _json.dump({"refresh_token": data.get("refresh_token", refresh)}, f)
            except Exception as e:
                logger.warning("Salvataggio cache token fallito: %s", e)
            return data["access_token"]
        logger.error("TikTok refresh fallito: %s", data)
    except Exception as e:
        logger.error("TikTok refresh errore: %s", e)
    return None


def publish_tiktok(video_path: str, title: str, description: str) -> str | None:
    """
    Carica video nell'INBOX TikTok come bozza (scope video.upload).
    Arriva nelle notifiche app TikTok -> apri -> pubblica. Restituisce 'inbox'.
    """
    import requests

    token = os.environ.get("TIKTOK_ACCESS_TOKEN")
    if not token:
        logger.warning("TikTok: TIKTOK_ACCESS_TOKEN non configurato, skip.")
        return None

    # Refresh token (TikTok access token scade in 24h)
    refreshed = _refresh_tiktok_token()
    if refreshed:
        token = refreshed

    video_size = Path(video_path).stat().st_size

    # 1. Init INBOX (no post_info)
    try:
        r = requests.post(
            "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            json={
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": video_size,
                    "chunk_size": video_size,
                    "total_chunk_count": 1,
                },
            },
            timeout=30,
        )
        r.raise_for_status()
        data = r.json().get("data", {})
        publish_id = data.get("publish_id")
        upload_url = data.get("upload_url")
        if not upload_url:
            logger.error("TikTok inbox init: risposta inattesa %s", r.json())
            return None
    except Exception as e:
        logger.error("TikTok inbox init fallito: %s", e)
        return None

    # 2. Upload video
    try:
        with open(video_path, "rb") as f:
            video_bytes = f.read()
        upload_r = requests.put(
            upload_url,
            data=video_bytes,
            headers={
                "Content-Type": "video/mp4",
                "Content-Range": f"bytes 0-{video_size - 1}/{video_size}",
                "Content-Length": str(video_size),
            },
            timeout=120,
        )
        upload_r.raise_for_status()
    except Exception as e:
        logger.error("TikTok upload video fallito: %s", e)
        return None

    logger.info("TikTok: video in inbox. Publish ID: %s", publish_id)
    return "inbox"


# ── Instagram Reels ──────────────────────────────────────────────────────────

def _upload_to_cdn(video_path: str) -> str:
    """
    Carica il video su un CDN accessibile pubblicamente.
    Usa transfer.sh (gratuito, nessuna registrazione, file disponibili 14 giorni).
    """
    import requests
    filename = Path(video_path).name
    with open(video_path, "rb") as f:
        r = requests.put(
            f"https://transfer.sh/{filename}",
            data=f,
            headers={"Max-Days": "1"},
            timeout=120,
        )
    r.raise_for_status()
    url = r.text.strip()
    logger.info("Video caricato su CDN: %s", url)
    return url


def publish_instagram(video_path: str, caption: str) -> str | None:
    """Pubblica Reel su Instagram via Meta Graph API."""
    import requests

    ig_user_id = os.environ.get("IG_USER_ID")
    ig_token = os.environ.get("IG_ACCESS_TOKEN")

    if not ig_user_id or not ig_token:
        logger.warning("Instagram: credenziali mancanti, skip.")
        return None

    # 1. Carica video su CDN pubblico
    try:
        video_url = _upload_to_cdn(video_path)
    except Exception as e:
        logger.error("Instagram: caricamento CDN fallito: %s", e)
        return None

    # 2. Crea container Reels
    try:
        r = requests.post(
            f"https://graph.facebook.com/v19.0/{ig_user_id}/media",
            params={
                "media_type": "REELS",
                "video_url": video_url,
                "caption": caption[:2200],
                "access_token": ig_token,
            },
            timeout=30,
        )
        r.raise_for_status()
        container_id = r.json()["id"]
    except Exception as e:
        logger.error("Instagram: crea container fallito: %s", e)
        return None

    # 3. Poll stato processing video
    for attempt in range(24):
        time.sleep(10)
        try:
            status_r = requests.get(
                f"https://graph.facebook.com/v19.0/{container_id}",
                params={"fields": "status_code", "access_token": ig_token},
                timeout=15,
            )
            code = status_r.json().get("status_code", "")
            if code == "FINISHED":
                break
            elif code == "ERROR":
                logger.error("Instagram: processing video fallito")
                return None
        except Exception as e:
            logger.warning("Instagram status poll errore (tentativo %d): %s", attempt + 1, e)
    else:
        logger.error("Instagram: timeout processing video")
        return None

    # 4. Pubblica
    try:
        pub_r = requests.post(
            f"https://graph.facebook.com/v19.0/{ig_user_id}/media_publish",
            params={"creation_id": container_id, "access_token": ig_token},
            timeout=30,
        )
        pub_r.raise_for_status()
        media_id = pub_r.json()["id"]
        url = f"https://www.instagram.com/reel/{media_id}/"
        logger.info("Instagram pubblicato: %s", url)
        return url
    except Exception as e:
        logger.error("Instagram: pubblicazione fallita: %s", e)
        return None


# ── YouTube Shorts ───────────────────────────────────────────────────────────

def _get_youtube_credentials():
    """Carica le credenziali YouTube dalle variabili d'ambiente."""
    import json
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    token_json = os.environ.get("YOUTUBE_TOKEN_JSON")
    if not token_json:
        raise RuntimeError("YOUTUBE_TOKEN_JSON non configurato. Esegui prima: python setup.py")

    token_data = json.loads(token_json)
    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=token_data.get("client_id"),
        client_secret=token_data.get("client_secret"),
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def publish_youtube(video_path: str, title: str, description: str, script: dict = None) -> str | None:
    """Pubblica su YouTube Shorts via YouTube Data API v3."""
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        logger.error("YouTube: google-api-python-client non installato")
        return None

    try:
        creds = _get_youtube_credentials()
    except Exception as e:
        logger.warning("YouTube: credenziali non disponibili (%s), skip.", e)
        return None

    try:
        youtube = build("youtube", "v3", credentials=creds)

        # Shorts richiede #Shorts nel titolo o descrizione
        yt_title = title[:100]
        if "#Shorts" not in yt_title and "#shorts" not in yt_title:
            yt_title = yt_title[:93] + " #Shorts"

        # Categoria ottimizzata per algoritmo:
        # 27=Education, 28=Science&Tech, 22=People&Blogs, 25=News
        categoria = script.get("categoria", "scienza") if isinstance(script, dict) else "scienza"
        cat_map = {"scienza": "28", "tecnologia": "28", "storia": "27", "attualita": "25", "sport": "17"}
        category_id = cat_map.get(categoria, "28")

        request = youtube.videos().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": yt_title,
                    "description": description[:5000],
                    "categoryId": category_id,
                    "defaultLanguage": "it",
                    "tags": script.get("hashtags", []) if isinstance(script, dict) else [],
                },
                "status": {
                    "privacyStatus": "public",
                    "selfDeclaredMadeForKids": False,
                    # Dichiarazione contenuto AI-generated (obbligatorio 2026)
                    "containsSyntheticMedia": True,
                },
            },
            media_body=MediaFileUpload(video_path, mimetype="video/mp4", resumable=True),
        )
        response = None
        while response is None:
            _, response = request.next_chunk()

        video_id = response["id"]
        url = f"https://www.youtube.com/shorts/{video_id}"
        logger.info("YouTube pubblicato: %s", url)
        return url

    except Exception as e:
        logger.error("YouTube: pubblicazione fallita: %s", e)
        return None


# ── Pubblicazione combinata ──────────────────────────────────────────────────

def publish_all(video_path: str, script: dict) -> dict:
    """
    Pubblica su tutte le piattaforme. Continua anche se una fallisce.
    Restituisce dict con risultati per piattaforma.
    """
    title = script.get("title_youtube", script.get("trending_topic", "Video"))
    description = script.get("description", "")
    hashtags = " ".join(script.get("hashtags", []))

    # Estrai la domanda finale del voiceover (stessa del video) per la description
    voiceover = script.get("voiceover", "")
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', voiceover) if s.strip()]
    final_question = ""
    for s in reversed(sentences):
        if "?" in s:
            final_question = s
            break

    # Description engagement:
    # 1. domanda parlata del video (genera commenti e condivisione)
    # 2. descrizione/CTA del modello
    # 3. salva
    # 4. hashtags (tutti e 5, cliccabili)
    parts = []
    if final_question:
        parts.append(final_question)
    if description and description not in final_question:
        parts.append(description)
    # Identità serie = motivo per seguire (converte view in iscritti)
    parts.append("🔔 SEGUI: un fatto incredibile ogni giorno. Domani te ne svelo un altro.")
    parts.append("Salva e condividi 💾")
    parts.append(hashtags)
    caption = "\n\n".join(parts).strip()

    # Solo YouTube Shorts (TikTok/Instagram rimossi per focus crescita)
    results = {}
    logger.info("=== Pubblicazione YouTube ===")
    results["youtube"] = publish_youtube(video_path, title, caption, script=script)

    published = sum(1 for v in results.values() if v)
    logger.info("Pubblicato su YouTube: %s", results.get("youtube"))
    return results
