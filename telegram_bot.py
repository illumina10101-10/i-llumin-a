"""
I-llumin-A Telegram Bot
Riceve comandi e triggera GitHub Actions nel cloud (niente pipeline locale).

Comandi: start, status, help
Avvio:   py -3 telegram_bot.py
"""
import os, time, threading
import requests, truststore, certifi
truststore.inject_into_ssl()
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN    = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID      = str(os.environ["TELEGRAM_CHAT_ID"])
GITHUB_TOKEN = os.environ.get("GITHUB_DISPATCH_TOKEN", "")
GITHUB_REPO  = "illumina10101-10/i-llumin-a"
WORKFLOW_ID  = "publish.yml"

API = f"https://api.telegram.org/bot{BOT_TOKEN}"
last_update_id = 0
dispatch_pending = False


def send(text: str):
    try:
        requests.post(f"{API}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
            verify=certifi.where(), timeout=10)
    except Exception as e:
        print(f"[send error] {e}")


def get_updates():
    global last_update_id
    try:
        r = requests.get(f"{API}/getUpdates",
            params={"offset": last_update_id + 1, "timeout": 30,
                    "allowed_updates": ["message"]},
            verify=certifi.where(), timeout=40)
        return r.json().get("result", [])
    except Exception:
        return []


def trigger_github_actions(reason: str = "telegram") -> bool:
    """Triggera workflow_dispatch su GitHub Actions."""
    if not GITHUB_TOKEN:
        return False
    try:
        r = requests.post(
            f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{WORKFLOW_ID}/dispatches",
            headers={
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={"ref": "main", "inputs": {"reason": reason}},
            verify=certifi.where(), timeout=15,
        )
        return r.status_code == 204
    except Exception as e:
        print(f"[GitHub dispatch error] {e}")
        return False


def check_last_run_status():
    """Controlla lo stato dell'ultimo run GitHub Actions."""
    if not GITHUB_TOKEN:
        return None
    try:
        r = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{WORKFLOW_ID}/runs",
            params={"per_page": 1},
            headers={"Authorization": f"Bearer {GITHUB_TOKEN}",
                     "Accept": "application/vnd.github+json"},
            verify=certifi.where(), timeout=10,
        )
        runs = r.json().get("workflow_runs", [])
        if runs:
            run = runs[0]
            return {"status": run["status"], "conclusion": run.get("conclusion"),
                    "url": run["html_url"], "created": run["created_at"][:16]}
    except Exception:
        pass
    return None


def handle_command(text: str):
    global dispatch_pending
    cmd = text.strip().lower().lstrip("/")

    if cmd in ("start", "avvia", "go", "video", "crea"):
        if not GITHUB_TOKEN:
            send("GITHUB_DISPATCH_TOKEN non configurato nel .env.\nImpossibile triggerare GitHub Actions da Telegram.")
            return

        send("Avvio pipeline in cloud (GitHub Actions)...")
        ok = trigger_github_actions("telegram-start")
        if ok:
            dispatch_pending = True
            send(
                "Pipeline avviata su GitHub Actions!\n\n"
                "Durata stimata: ~5-10 minuti.\n"
                "Riceverai notifica Telegram quando il video e pubblicato."
            )
        else:
            send("Errore nell'avvio. Controlla il GITHUB_DISPATCH_TOKEN.")

    elif cmd in ("status", "stato"):
        run = check_last_run_status()
        if run:
            emoji = {"completed": "COMPLETATO", "in_progress": "IN CORSO", "queued": "IN CODA"}.get(run["status"], run["status"])
            conclusion = f" ({run['conclusion']})" if run.get("conclusion") else ""
            send(
                f"Ultimo run GitHub Actions:\n"
                f"Stato: {emoji}{conclusion}\n"
                f"Avviato: {run['created']}\n"
                f"Link: {run['url']}"
            )
        else:
            send("Nessun run trovato (o GITHUB_DISPATCH_TOKEN mancante).")

    elif cmd in ("help", "aiuto"):
        send(
            "<b>I-llumin-A Bot</b>\n\n"
            "/start — avvia creazione video su GitHub Actions\n"
            "/status — stato dell'ultimo run\n"
            "/help — questo messaggio\n\n"
            "I video vengono pubblicati automaticamente alle 9:00 e 18:30 CET ogni giorno."
        )

    elif cmd in ("ciao", "hi", "hello"):
        send("Ciao! Scrivi /start per creare un video extra, /help per i comandi.")


def main():
    global last_update_id
    token_ok = "OK" if GITHUB_TOKEN else "MANCANTE (imposta GITHUB_DISPATCH_TOKEN nel .env)"
    print(f"[I-llumin-A Bot] Avviato. Chat: {CHAT_ID} | GitHub token: {token_ok}")
    send(
        "Bot avviato!\n\n"
        "/start — crea video extra\n"
        "/status — stato pipeline\n"
        "/help — aiuto"
    )

    while True:
        updates = get_updates()
        for update in updates:
            last_update_id = update["update_id"]
            msg = update.get("message", {})
            chat_id = str(msg.get("chat", {}).get("id", ""))
            text = msg.get("text", "")
            if chat_id != CHAT_ID:
                continue
            if text:
                print(f"[CMD] {text}")
                handle_command(text)
        time.sleep(1)


if __name__ == "__main__":
    main()
