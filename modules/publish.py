"""
Pubblica il video su TikTok, Instagram Reels e YouTube Shorts.
Ogni piattaforma ha il proprio fallback in caso di errore.
"""
import os
import json
import time
import logging
import base64
from pathlib import Path

logger = logging.getLogger(__name__)


# ── TikTok ──────────────────────────────────────────────────────────────────

def publish_tiktok(video_path: str, title: str, description: str) -> str | None:
    """
    Pubblica su TikTok via Content Posting API v2.
    Modalità: Direct Post (se approvata) oppure Upload to Inbox.
    Restituisce l'URL del video o None in caso di errore.
    """
    import requests

    token = os.environ.get("TIKTOK_ACCESS_TOKEN")
    if not token:
        logger.warning("TikTok: TIKTOK_ACCESS_TOKEN non configurato, skip.")
        return None

    video_size = Path(video_path).stat().st_size
    caption = f"{title}\n\n{description}"[:2200]  # TikTok max 2200 char

    # 1. Init upload
    try:
        r = requests.post(
            "https://open.tiktokapis.com/v2/post/publish/video/init/",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            json={
                "post_info": {
                    "title": caption,
                    "privacy_level": "PUBLIC_TO_EVERYONE",
                    "disable_comment": False,
                    "disable_duet": False,
                    "disable_stitch": False,
                    "video_cover_timestamp_ms": 1000,
                    "brand_content_toggle": False,
                    "brand_organic_toggle": False,
                },
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
    except Exception as e:
        logger.error("TikTok init upload fallito: %s", e)
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

    # 3. Poll stato pubblicazione
    for attempt in range(12):
        time.sleep(10)
        try:
            status_r = requests.post(
                "https://open.tiktokapis.com/v2/post/publish/status/fetch/",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
                json={"publish_id": publish_id},
                timeout=15,
            )
            status = status_r.json().get("data", {}).get("status", "")
            if status == "PUBLISH_COMPLETE":
                url = f"https://www.tiktok.com/@me/video/{publish_id}"
                logger.info("TikTok pubblicato: %s", url)
                return url
            elif status in ("FAILED", "PUBLISH_FAILED"):
                logger.error("TikTok pubblicazione fallita: %s", status_r.json())
                return None
        except Exception as e:
            logger.warning("TikTok status poll errore (tentativo %d): %s", attempt + 1, e)

    logger.error("TikTok: timeout in attesa della pubblicazione")
    return None


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


def publish_youtube(video_path: str, title: str, description: str) -> str | None:
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

        request = youtube.videos().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": yt_title,
                    "description": description[:5000],
                    "categoryId": "22",  # People & Blogs
                    "defaultLanguage": "it",
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
    caption = f"{description}\n{hashtags}".strip()

    results = {}

    logger.info("=== Pubblicazione TikTok ===")
    results["tiktok"] = publish_tiktok(video_path, title, caption)

    logger.info("=== Pubblicazione Instagram ===")
    results["instagram"] = publish_instagram(video_path, caption)

    logger.info("=== Pubblicazione YouTube ===")
    results["youtube"] = publish_youtube(video_path, title, caption)

    published = sum(1 for v in results.values() if v)
    logger.info("Pubblicato su %d/3 piattaforme: %s", published, results)
    return results
