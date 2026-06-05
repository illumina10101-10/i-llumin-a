"""
Traccia i video pubblicati su SQLite.
Ogni domenica ore 10:00: raccoglie analytics, genera report con Claude, invia su Telegram.
"""
import os
import json
import sqlite3
import logging
from datetime import date, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "data" / "tracker.db"


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                published_at TEXT NOT NULL,
                topic TEXT,
                tiktok_url TEXT,
                instagram_url TEXT,
                youtube_url TEXT,
                tiktok_views INTEGER DEFAULT 0,
                instagram_views INTEGER DEFAULT 0,
                youtube_views INTEGER DEFAULT 0,
                script_json TEXT
            )
        """)


def record_video(script: dict, urls: dict) -> int:
    """Registra un video pubblicato nel database."""
    init_db()
    with _conn() as conn:
        cursor = conn.execute(
            """INSERT INTO videos
               (published_at, topic, tiktok_url, instagram_url, youtube_url, script_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                date.today().isoformat(),
                script.get("trending_topic", ""),
                urls.get("tiktok"),
                urls.get("instagram"),
                urls.get("youtube"),
                json.dumps(script, ensure_ascii=False),
            ),
        )
        return cursor.lastrowid


def get_week_videos() -> list[dict]:
    """Restituisce i video pubblicati negli ultimi 7 giorni."""
    init_db()
    since = (date.today() - timedelta(days=7)).isoformat()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM videos WHERE published_at >= ?", (since,)
        ).fetchall()
    return [dict(r) for r in rows]


def _fetch_youtube_views(video_url: str, creds) -> int:
    """Recupera le views di un video YouTube."""
    if not video_url:
        return 0
    try:
        from googleapiclient.discovery import build
        video_id = video_url.split("/shorts/")[-1].split("?")[0]
        yt = build("youtube", "v3", credentials=creds)
        r = yt.videos().list(part="statistics", id=video_id).execute()
        items = r.get("items", [])
        if items:
            return int(items[0]["statistics"].get("viewCount", 0))
    except Exception as e:
        logger.warning("YouTube analytics error: %s", e)
    return 0


def generate_weekly_report() -> str:
    """
    Genera il report settimanale:
    raccoglie analytics, chiama Claude per suggerimenti, restituisce testo.
    """
    videos = get_week_videos()
    if not videos:
        return "Nessun video pubblicato questa settimana."

    total = len(videos)
    total_views = sum(
        (v.get("tiktok_views") or 0)
        + (v.get("instagram_views") or 0)
        + (v.get("youtube_views") or 0)
        for v in videos
    )

    topics = [v["topic"] for v in videos if v.get("topic")]
    best = max(
        videos,
        key=lambda v: (v.get("tiktok_views") or 0) + (v.get("instagram_views") or 0) + (v.get("youtube_views") or 0),
        default=None,
    )

    summary = (
        f"Settimana {date.today().isocalendar()[1]}/{date.today().year}\n"
        f"Video pubblicati: {total}\n"
        f"Views totali stimate: {total_views:,}\n"
        f"Topic: {', '.join(topics[:5])}\n"
    )
    if best:
        best_views = (best.get("tiktok_views") or 0) + (best.get("instagram_views") or 0) + (best.get("youtube_views") or 0)
        summary += f"Miglior video: '{best['topic']}' con ~{best_views:,} views\n"

    # Chiedi suggerimenti a Claude
    claude_suggestions = _get_claude_suggestions(summary, topics)
    report = f"{summary}\n\n🎯 Suggerimenti per la prossima settimana:\n{claude_suggestions}"
    return report


def _get_claude_suggestions(summary: str, topics: list[str]) -> str:
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=400,
            messages=[{
                "role": "user",
                "content": (
                    f"Analizza questi dati di un canale social faceless italiano:\n{summary}\n\n"
                    f"Dai 3 suggerimenti concreti (max 2 righe ciascuno) per migliorare "
                    f"performance e crescita la prossima settimana. Sii specifico e pratico."
                ),
            }],
        )
        return response.content[0].text
    except Exception as e:
        logger.warning("Claude suggestions fallite: %s", e)
        return "• Analizza i video con più views e replica il formato\n• Posta costantemente agli orari ottimali\n• Testa nuovi hook nelle prime 3 secondi"
