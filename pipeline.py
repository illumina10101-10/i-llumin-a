"""
Entry point della pipeline. Eseguito da GitHub Actions 2 volte al giorno.
Sequenza: content → audio → video → publish → notify → track
"""
import os
import sys
import logging
import tempfile
from pathlib import Path
from datetime import date

from dotenv import load_dotenv

load_dotenv()

# Configura logging su file + stdout
Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(f"logs/publish_{date.today().isoformat()}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("pipeline")

from modules.content import generate_script
from modules.audio import generate_voiceover, generate_captions, get_audio_duration
from modules.video import build_video
from modules.publish import publish_all
from modules.notify import notify_success, notify_error
from modules.tracker import record_video, generate_weekly_report


def load_config() -> dict:
    config_path = Path("config/niche.json")
    if config_path.exists():
        import json
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}

    return {
        "niche": os.environ.get("NICHE") or data.get("selected_niche") or "tecnologia",
        "voice": os.environ.get("VOICE") or data.get("voice") or "it-IT-ElsaNeural",
        "affiliate_url": os.environ.get("AFFILIATE_URL") or data.get("affiliate_url") or "",
        "affiliate_product": os.environ.get("AFFILIATE_PRODUCT") or data.get("affiliate_product") or "",
    }


def run_pipeline() -> bool:
    """Esegue la pipeline completa. Restituisce True se almeno 1 piattaforma pubblicata."""
    config = load_config()
    logger.info("=== Pipeline avviata | Niche: %s | Data: %s ===", config["niche"], date.today())

    with tempfile.TemporaryDirectory() as work_dir_str:
        work_dir = Path(work_dir_str)
        audio_path = str(work_dir / "voiceover.mp3")
        captions_path = str(work_dir / "captions.ass")
        video_path = str(work_dir / "output.mp4")

        # 1. Genera script
        try:
            logger.info("--- Step 1: Generazione script ---")
            script = generate_script(
                niche=config["niche"],
                affiliate_product=config["affiliate_product"],
                affiliate_url=config["affiliate_url"],
            )
            logger.info("Script OK: '%s'", script.get("trending_topic"))
        except Exception as e:
            logger.error("Step 1 FALLITO: %s", e)
            notify_error("content.py", str(e))
            return False

        # 2. Genera voiceover
        try:
            logger.info("--- Step 2: Voiceover ---")
            generate_voiceover(script["voiceover"], audio_path, config["voice"])
            duration = get_audio_duration(audio_path)
            logger.info("Audio OK: %.1f secondi", duration)
        except Exception as e:
            logger.error("Step 2 FALLITO: %s", e)
            notify_error("audio.py - voiceover", str(e))
            return False

        # 3. Genera captions (con fallback timing-stimato, niente faster-whisper)
        try:
            logger.info("--- Step 3: Captions ---")
            generate_captions(audio_path, captions_path, voiceover_text=script.get("voiceover", ""))
        except Exception as e:
            logger.warning("Captions fallite (continuo senza): %s", e)
            with open(captions_path, "w") as f:
                f.write("[Script Info]\nScriptType: v4.00+\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")

        # 4. Assembla video
        try:
            logger.info("--- Step 4: Assemblaggio video ---")
            build_video(script, audio_path, captions_path, video_path, duration, work_dir)
        except Exception as e:
            logger.error("Step 4 FALLITO: %s", e)
            notify_error("video.py", str(e))
            return False

        # 5. Pubblica
        logger.info("--- Step 5: Pubblicazione ---")
        urls = publish_all(video_path, script)
        published = any(v for v in urls.values() if v)

        # 6. Notifica e registra
        if published:
            notify_success(script, urls)
            record_video(script, urls)
            logger.info("=== Pipeline completata con successo ===")
        else:
            notify_error("publish.py", "Nessuna piattaforma ha pubblicato il video")
            logger.error("Nessuna pubblicazione riuscita.")

        return published


def run_weekly_report() -> None:
    """Genera e invia il report settimanale (chiamato la domenica)."""
    from modules.notify import notify_report
    try:
        report = generate_weekly_report()
        notify_report(report)
        logger.info("Report settimanale inviato.")
    except Exception as e:
        logger.error("Report settimanale fallito: %s", e)
        notify_error("tracker.py", str(e))


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--report":
        run_weekly_report()
    else:
        success = run_pipeline()
        sys.exit(0 if success else 1)
