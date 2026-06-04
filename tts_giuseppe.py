"""
Standalone Microsoft Edge TTS usando websocket-client — senza aiohttp.
Usa GiuseppeNeural, rate +12%, pitch -5Hz.
Uso: python tts_giuseppe.py input.txt output.mp3
"""
import sys, ssl, uuid, re
from pathlib import Path
import websocket
import truststore; truststore.inject_into_ssl()

# Use edge-tts constants/DRM — only the WebSocket client is replaced
sys.path.insert(0, r"D:\Social_Bot")
from edge_tts.constants import WSS_URL, WSS_HEADERS, SEC_MS_GEC_VERSION
from edge_tts.drm import DRM

VOICE = "it-IT-GiuseppeNeural"
RATE  = "+12%"
PITCH = "-5Hz"

def _connect_id():
    return uuid.uuid4().hex.upper()

def _date():
    import time
    return time.strftime("%a %b %d %Y %H:%M:%S GMT+0000 (Coordinated Universal Time)")

def _ssml(text):
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='it-IT'>"
        f"<voice name='{VOICE}'>"
        f"<prosody pitch='{PITCH}' rate='{RATE}'>{text}</prosody>"
        f"</voice></speak>"
    )

def synthesize(text: str, out_path: str):
    cid = _connect_id()
    url = (
        f"{WSS_URL}&ConnectionId={cid}"
        f"&Sec-MS-GEC={DRM.generate_sec_ms_gec()}"
        f"&Sec-MS-GEC-Version={SEC_MS_GEC_VERSION}"
    )
    headers = DRM.headers_with_muid(WSS_HEADERS)

    ssl_ctx = ssl.create_default_context()
    ws = websocket.WebSocket(sslopt={"context": ssl_ctx})
    ws.connect(url, header=dict(headers), timeout=30)

    # 1 — config request
    ws.send(
        f"X-Timestamp:{_date()}\r\n"
        "Content-Type:application/json; charset=utf-8\r\n"
        "Path:speech.config\r\n\r\n"
        '{"context":{"synthesis":{"audio":{"metadataoptions":{'
        '"sentenceBoundaryEnabled":"false","wordBoundaryEnabled":"false"}'
        ',"outputFormat":"audio-24khz-48kbitrate-mono-mp3"}}}}'
    )

    # 2 — SSML request
    req_id = _connect_id()
    ssml = _ssml(text)
    ws.send(
        f"X-RequestId:{req_id}\r\n"
        f"X-Timestamp:{_date()}\r\n"
        "Content-Type:application/ssml+xml\r\n"
        "Path:ssml\r\n\r\n"
        + ssml
    )

    # 3 — raccolta audio
    audio_chunks = []
    while True:
        msg = ws.recv()
        if isinstance(msg, bytes):
            # binary: header_len (2 bytes big-endian) + headers + audio
            if len(msg) < 2:
                continue
            hlen = int.from_bytes(msg[:2], "big")
            header = msg[2:2+hlen].decode("utf-8", errors="ignore")
            if "Path:audio" in header:
                audio_chunks.append(msg[2+hlen:])
        elif isinstance(msg, str):
            if "Path:turn.end" in msg:
                break

    ws.close()

    Path(out_path).write_bytes(b"".join(audio_chunks))
    print(f"OK: {out_path} ({sum(len(c) for c in audio_chunks)} bytes)")

if __name__ == "__main__":
    text_file = sys.argv[1] if len(sys.argv) > 1 else r"D:\Social_Bot\voice_input.txt"
    out_file  = sys.argv[2] if len(sys.argv) > 2 else r"D:\Social_Bot\output_audio.mp3"
    text = Path(text_file).read_text(encoding="utf-8")
    synthesize(text, out_file)
