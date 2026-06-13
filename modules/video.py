"""
Scarica clip Pexels, assembla il video finale con FFmpeg.
Fallback: immagini Pollinations.ai → slideshow.
"""
import os
import json
import logging
import subprocess
import tempfile
import urllib.request
import requests
from pathlib import Path

logger = logging.getLogger(__name__)

PEXELS_API = "https://api.pexels.com/videos/search"
PIXABAY_MUSIC_API = "https://pixabay.com/api/"
POLLINATIONS_API = "https://image.pollinations.ai/prompt/{prompt}?width=1080&height=1920&nologo=true"


def fetch_pexels_videos(keywords: list[str], api_key: str, work_dir: Path, max_clips: int = 5) -> list[Path]:
    """Scarica clip video da Pexels per le keyword fornite."""
    import requests
    clips = []
    seen_ids = set()

    for keyword in keywords:
        if len(clips) >= max_clips:
            break
        try:
            r = requests.get(
                PEXELS_API,
                params={"query": keyword, "orientation": "portrait", "per_page": 3, "size": "medium"},
                headers={"Authorization": api_key},
                timeout=30,
            )
            r.raise_for_status()
            videos = r.json().get("videos", [])
            for video in videos:
                if len(clips) >= max_clips:
                    break
                vid_id = video["id"]
                if vid_id in seen_ids:
                    continue
                seen_ids.add(vid_id)
                # Scegli il file HD più vicino a 1080p
                files = sorted(
                    [f for f in video.get("video_files", []) if f.get("quality") in ("hd", "sd")],
                    key=lambda x: abs(x.get("width", 0) - 1080),
                )
                if not files:
                    continue
                url = files[0]["link"]
                dest = work_dir / f"clip_{vid_id}.mp4"
                logger.info("Download clip Pexels: %s → %s", url[:60], dest.name)
                # usa requests con headers per evitare 403 su CDN
                dl = requests.get(url, headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": "https://www.pexels.com/"
                }, timeout=60, stream=True)
                dl.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in dl.iter_content(65536):
                        f.write(chunk)
                clips.append(dest)
        except Exception as e:
            logger.warning("Errore Pexels keyword '%s': %s", keyword, e)

    logger.info("Clip Pexels scaricati: %d", len(clips))
    return clips


def fetch_pollinations_images(keywords: list[str], work_dir: Path, count: int = 5, session=None) -> list[Path]:
    """Genera immagini AI da Pollinations come fallback."""
    import urllib.parse
    if session is None:
        import requests as _req
        session = _req.Session()
    images = []
    for i, kw in enumerate(keywords[:count]):
        prompt = f"cinematic {kw} vertical portrait 9:16 photorealistic"
        url = POLLINATIONS_API.format(prompt=urllib.parse.quote(prompt))
        dest = work_dir / f"img_{i}.jpg"
        try:
            logger.info("Download immagine Pollinations: %s", kw)
            r = session.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            r.raise_for_status()
            dest.write_bytes(r.content)
            images.append(dest)
        except Exception as e:
            logger.warning("Errore Pollinations '%s': %s", kw, e)
    return images


def images_to_clips(images: list[Path], work_dir: Path, duration_each: float = 4.0) -> list[Path]:
    """Converte immagini JPEG in clip video (slideshow)."""
    clips = []
    for i, img in enumerate(images):
        out = work_dir / f"slide_{i}.mp4"
        subprocess.run([
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(img),
            "-t", str(duration_each),
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,zoompan=z='min(zoom+0.0015,1.5)':d=125:s=1080x1920",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "25",
            str(out),
        ], check=True, capture_output=True)
        clips.append(out)
    return clips


def scale_clip(clip: Path, work_dir: Path, idx: int) -> Path:
    """Scala un clip a 1080x1920 (9:16)."""
    out = work_dir / f"scaled_{idx}.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-i", str(clip),
        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
        "-c:v", "libx264", "-an", "-r", "25", "-pix_fmt", "yuv420p",
        str(out),
    ], check=True, capture_output=True)
    return out


def get_music_path() -> Path | None:
    """Restituisce il percorso della musica di sottofondo se disponibile."""
    music_dir = Path(__file__).parent.parent / "assets" / "music"
    for ext in ("*.mp3", "*.wav", "*.m4a"):
        files = list(music_dir.glob(ext))
        if files:
            return files[0]
    return None


def assemble_video(
    clips: list[Path],
    audio_path: str,
    captions_path: str,
    output_path: str,
    audio_duration: float,
    script: dict = None,
) -> str:
    """Assembla il video finale con FFmpeg."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        # 1. Scala tutti i clip a 1080x1920
        scaled = [scale_clip(c, tmp, i) for i, c in enumerate(clips)]

        # 2. Crea concat list e looppala finché copre audio_duration
        total_needed = audio_duration + 2  # 2s buffer
        concat_file = tmp / "concat.txt"
        loop_clips = []
        total_dur = 0.0
        i = 0
        while total_dur < total_needed:
            clip = scaled[i % len(scaled)]
            loop_clips.append(clip)
            # Stima durata approssimativa (3-10 secondi per clip)
            total_dur += 6
            i += 1
            if i > 60:  # protezione loop infinito
                break

        with open(concat_file, "w") as f:
            for c in loop_clips:
                f.write(f"file '{c}'\n")

        # 3. Concatena video
        concat_out = tmp / "concat.mp4"
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-t", str(total_needed),
            "-c:v", "libx264", "-an",
            str(concat_out),
        ], check=True, capture_output=True)

        # 4. Costruisci filtro audio (voiceover + musica sottofondo)
        music_path = get_music_path()
        # Font path cross-platform (Linux GitHub Actions vs Windows)
        import platform
        if platform.system() == "Windows":
            font_bold = "C\\:/Windows/Fonts/arialbd.ttf"
            font_reg  = "C\\:/Windows/Fonts/arial.ttf"
        else:
            font_bold = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            font_reg  = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

        # Titolo safe zone: y=130 (sopra UI YouTube), branding y=1750 (sopra bottoni)
        safe_title = script.get("trending_topic", "")[:38].replace("'", "").replace(":", "")
        overlay = (
            f"ass={captions_path},"
            f"drawtext=fontfile='{font_bold}':text='{safe_title}':"
            f"fontcolor=white:fontsize=46:x=(w-text_w)/2:y=130:"
            f"box=1:boxcolor=black@0.55:boxborderw=12,"
            f"drawtext=fontfile='{font_reg}':text='I-llumin-A':"
            f"fontcolor=gold:fontsize=34:x=(w-text_w)/2:y=1750"
        )

        if music_path:
            audio_filter = (
                "[1:a]volume=1.0[voice];"
                "[2:a]volume=0.15,aloop=loop=-1:size=2e+09[music];"
                "[voice][music]amix=inputs=2:duration=first[aout]"
            )
            cmd = [
                "ffmpeg", "-y",
                "-i", str(concat_out), "-i", audio_path, "-i", str(music_path),
                "-filter_complex", audio_filter,
                "-map", "0:v", "-map", "[aout]",
                "-vf", overlay,
                "-c:v", "libx264", "-c:a", "aac", "-b:a", "128k",
                "-t", str(audio_duration + 1),
                "-pix_fmt", "yuv420p", output_path,
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-i", str(concat_out), "-i", audio_path,
                "-vf", overlay,
                "-map", "0:v", "-map", "1:a",
                "-c:v", "libx264", "-c:a", "aac", "-b:a", "128k",
                "-t", str(audio_duration + 1),
                "-pix_fmt", "yuv420p", output_path,
            ]

        logger.info("Assemblaggio video finale...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error("FFmpeg error:\n%s", result.stderr[-2000:])
            raise RuntimeError("FFmpeg fallito durante l'assemblaggio")

    size_mb = Path(output_path).stat().st_size / 1024 / 1024
    logger.info("Video finale: %s (%.1f MB)", output_path, size_mb)
    return output_path


def build_video(
    script: dict,
    audio_path: str,
    captions_path: str,
    output_path: str,
    audio_duration: float,
    work_dir: Path,
) -> str:
    """Pipeline completa: scarica clip → assembla video."""
    pexels_key = os.environ.get("PEXELS_API_KEY", "")
    keywords = script.get("pexels_keywords", [script.get("trending_topic", "nature")])

    clips = []
    if pexels_key:
        clips = fetch_pexels_videos(keywords, pexels_key, work_dir)

    if not clips:
        logger.warning("Nessun clip Pexels trovato, uso Pollinations.ai come fallback...")
        images = fetch_pollinations_images(keywords, work_dir, session=requests.Session())
        clips = images_to_clips(images, work_dir)

    if not clips:
        raise RuntimeError("Impossibile ottenere footage (Pexels e Pollinations falliti)")

    return assemble_video(clips, audio_path, captions_path, output_path, audio_duration, script)
