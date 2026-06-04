"""
Genera sottotitoli ASS word-by-word dal testo del voiceover + durata audio.
Non richiede Whisper — sincronizza basandosi sulla velocita di parlato (3.2 parole/sec).
Uso: python gen_captions.py voiceover.txt durata_secondi output.ass
"""
import sys, re

def fmt_time(sec):
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    cs = int((sec % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def generate(text, duration, out_path):
    # Pulizia testo
    text = re.sub(r'[.!?]', ' . ', text)
    words = [w for w in text.split() if w.strip()]

    # Rimuovi punteggiatura standalone per la visualizzazione
    display_words = []
    for w in words:
        clean = re.sub(r'[^\w\']', '', w)
        if clean:
            display_words.append((w, clean))

    if not display_words:
        return

    # Timing: distribuisce le parole sulla durata (lascia 1.5s di margine finale)
    effective_dur = max(duration - 1.5, duration * 0.92)
    word_dur = effective_dur / len(display_words)

    header = """\
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Impact,88,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,2,2,60,60,960,1
Style: Hi,Impact,88,&H0000FFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,2,2,60,60,960,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    lines = [header]
    chunk_size = 3  # parole per riga

    chunks = [display_words[i:i+chunk_size] for i in range(0, len(display_words), chunk_size)]
    word_idx = 0

    for chunk in chunks:
        chunk_start = word_idx * word_dur
        chunk_end = (word_idx + len(chunk)) * word_dur

        for focus_i, (orig, clean) in enumerate(chunk):
            seg_start = fmt_time((word_idx + focus_i) * word_dur)
            seg_end = fmt_time((word_idx + focus_i + 1) * word_dur)

            parts = []
            for j, (_, w) in enumerate(chunk):
                if j == focus_i:
                    parts.append(r"{\c&H00FFFF&}" + w.upper() + r"{\c&HFFFFFF&}")
                else:
                    parts.append(w.upper())
            text_line = " ".join(parts)
            lines.append(f"Dialogue: 0,{seg_start},{seg_end},Default,,0,0,0,,{text_line}")

        word_idx += len(chunk)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"OK: {out_path} ({len(display_words)} parole)")

if __name__ == "__main__":
    text_file = sys.argv[1]
    duration = float(sys.argv[2])
    out_file = sys.argv[3]
    text = open(text_file, encoding="utf-8").read()
    generate(text, duration, out_file)
