"""
Notifiche Telegram per conferma pubblicazione ed errori.
"""
import os
import logging
import requests

logger = logging.getLogger(__name__)


def _send(text: str) -> bool:
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        logger.warning("Telegram: credenziali mancanti, notifica non inviata.")
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        logger.error("Telegram send fallito: %s", e)
        return False


def send_video(video_path: str, caption: str) -> bool:
    """Invia il file video su Telegram con caption pronta per TikTok."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        return False
    try:
        with open(video_path, "rb") as f:
            r = requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendVideo",
                data={"chat_id": chat_id, "caption": caption[:1024], "parse_mode": "HTML"},
                files={"video": f},
                timeout=120,
            )
        r.raise_for_status()
        logger.info("Video inviato su Telegram per pubblicazione TikTok manuale")
        return True
    except Exception as e:
        logger.error("Telegram send_video fallito: %s", e)
        return False


def notify_success(script: dict, urls: dict) -> None:
    topic = script.get("trending_topic", "Video")
    youtube = urls.get("youtube") or "❌ non pubblicato"
    hook = script.get("hook", "")

    msg = (
        f"✅ <b>Short pubblicato!</b>\n\n"
        f"📌 <b>Topic:</b> {topic}\n"
        f"🪝 <b>Hook:</b> {hook}\n\n"
        f"▶️ {youtube}\n\n"
        f"👁️ Analytics domani in YouTube Studio"
    )
    _send(msg)


def notify_error(step: str, error: str) -> None:
    msg = (
        f"❌ <b>Errore pipeline</b>\n\n"
        f"📍 <b>Step:</b> {step}\n"
        f"🔴 <b>Errore:</b> {error[:500]}\n\n"
        f"Controlla i log e intervieni."
    )
    _send(msg)


def notify_report(report_text: str) -> None:
    _send(f"📊 <b>Report settimanale</b>\n\n{report_text[:4000]}")
