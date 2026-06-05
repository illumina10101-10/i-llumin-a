"""
Genera il voiceover MP3 con edge-tts e i sottotitoli ASS con faster-whisper.
"""
import asyncio
import os
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


async def _tts_async(text: str, output_path: str, voice: str) -> list:
    """Genera MP3 e cattura i WordBoundary reali (timing preciso per ogni parola)."""
    import edge_tts
    communicate = edge_tts.Communicate(text, voice, rate="+8%")
    boundaries = []
    with open(output_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                # offset e duration in tick da 100ns -> secondi
                boundaries.append({
                    "start": chunk["offset"] / 10_000_000,
                    "end": (chunk["offset"] + chunk["duration"]) / 10_000_000,
                    "word": chunk["text"],
                })
    return boundaries


# memorizza i boundaries dell'ultima sintesi per generate_captions
_LAST_BOUNDARIES: list = []


def generate_voiceover(text: str, output_path: str, voice: str = "it-IT-GiuseppeNeural") -> str:
    """Genera MP3 voiceover. Restituisce il path del file."""
    global _LAST_BOUNDARIES
    logger.info("Generando voiceover con voce %s...", voice)
    _LAST_BOUNDARIES = asyncio.run(_tts_async(text, output_path, voice))
    size_kb = Path(output_path).stat().st_size // 1024
    logger.info("Voiceover salvato: %s (%d KB, %d word boundaries)",
                output_path, size_kb, len(_LAST_BOUNDARIES))
    return output_path


def generate_captions(audio_path: str, output_ass: str, voiceover_text: str = "") -> str:
    """
    Genera captions ASS word-by-word.
    Priorità: 1) WordBoundary reali da edge-tts (sync perfetto) 2) timing stimato.
    """
    # 1. Boundaries reali catturati durante la sintesi TTS (timing esatto)
    if _LAST_BOUNDARIES:
        words = [{"start": b["start"], "end": b["end"], "word": b["word"]}
                 for b in _LAST_BOUNDARIES if b["word"].strip()]
        if words:
            _write_ass(words, output_ass)
            logger.info("Captions (edge-tts WordBoundary REALE): %s (%d parole)",
                        output_ass, len(words))
            return output_ass

    # 2. Fallback: timing stimato dal testo
    if voiceover_text:
        logger.info("Generando captions (timing stimato dal testo)...")
        duration = get_audio_duration(audio_path)
        _write_ass_from_text(voiceover_text, duration, output_ass)
        logger.info("Captions (stimate): %s", output_ass)
        return output_ass

    raise RuntimeError("Impossibile generare captions: né boundaries né voiceover_text")


def _write_ass_from_text(text: str, duration: float, output_path: str) -> None:
    """Genera ASS con timing stimato (3.2 parole/sec) senza Whisper."""
    import re
    words_raw = [w for w in re.split(r'\s+', text) if w]
    display = [(w, re.sub(r'[^\w\']', '', w)) for w in words_raw if re.sub(r'[^\w\']', '', w)]
    if not display:
        return
    effective = max(duration - 1.5, duration * 0.92)
    word_dur = effective / len(display)
    chunks = [display[i:i+3] for i in range(0, len(display), 3)]
    header = """\
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Impact,88,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,2,2,60,60,960,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    word_idx = 0
    for chunk in chunks:
        for fi, (orig, clean) in enumerate(chunk):
            s = _fmt_time(word_idx * word_dur)
            e = _fmt_time((word_idx + 1) * word_dur)
            parts = []
            for j, (_, w) in enumerate(chunk):
                if j == fi:
                    parts.append(r"{\c&H00FFFF&}" + w.upper() + r"{\c&HFFFFFF&}")
                else:
                    parts.append(w.upper())
            lines.append(f"Dialogue: 0,{s},{e},Default,,0,0,0,,{' '.join(parts)}")
            word_idx += 1
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _write_ass(words: list[dict], output_path: str) -> None:
    """Scrive file ASS con highlight word-by-word stile virale."""
    header = """\
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Impact,85,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,80,80,200,1
Style: Highlight,Impact,85,&H0000FFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,80,80,200,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]

    # Raggruppa le parole in blocchi di 4 per riga
    chunk_size = 4
    chunks = [words[i:i + chunk_size] for i in range(0, len(words), chunk_size)]

    for chunk in chunks:
        chunk_start = chunk[0]["start"]
        chunk_end = chunk[-1]["end"]

        for focus_idx, focus_word in enumerate(chunk):
            seg_start = _fmt_time(focus_word["start"])
            seg_end = _fmt_time(focus_word["end"])

            # Testo: parole normali + parola evidenziata in giallo
            parts = []
            for i, w in enumerate(chunk):
                if i == focus_idx:
                    parts.append(r"{\c&H00FFFF&}" + w["word"].upper() + r"{\c&HFFFFFF&}")
                else:
                    parts.append(w["word"].upper())
            text = " ".join(parts)
            lines.append(f"Dialogue: 0,{seg_start},{seg_end},Default,,0,0,0,,{text}")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _fmt_time(seconds: float) -> str:
    """Converte secondi in formato ASS: H:MM:SS.cc"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def get_audio_duration(audio_path: str) -> float:
    """Restituisce la durata in secondi usando ffprobe."""
    import subprocess
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", audio_path],
        capture_output=True, text=True, check=True,
    )
    import json
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])
