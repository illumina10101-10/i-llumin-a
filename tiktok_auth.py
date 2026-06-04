"""
Ottieni il token TikTok per il bot I-llumin-A.
Apre il browser, cattura il callback in locale, salva access_token nel .env.
Eseguire UNA VOLTA sola: py -3 tiktok_auth.py
"""
import os, json, secrets, webbrowser, urllib.parse, http.server, threading
import hashlib, base64
import requests, truststore, certifi
truststore.inject_into_ssl()
from dotenv import load_dotenv
load_dotenv()

CLIENT_KEY    = os.environ["TIKTOK_CLIENT_KEY"]
CLIENT_SECRET = os.environ["TIKTOK_CLIENT_SECRET"]
REDIRECT_URI  = "http://localhost:8080/callback"
SCOPE         = "video.upload"
STATE         = secrets.token_hex(16)

# PKCE — richiesto da TikTok OAuth 2.0
CODE_VERIFIER  = secrets.token_urlsafe(64)
CODE_CHALLENGE = base64.urlsafe_b64encode(
    hashlib.sha256(CODE_VERIFIER.encode()).digest()
).rstrip(b"=").decode()

auth_code = None

class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params and params.get("state", [""])[0] == STATE:
            auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h2>Autorizzazione completata! Puoi chiudere questa finestra.</h2>")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Errore: state mismatch o codice mancante.")
    def log_message(self, *args):
        pass  # silenzia i log del server

def exchange_code(code):
    """Scambia il codice con access_token + refresh_token."""
    r = requests.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": CLIENT_KEY,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
            "code_verifier": CODE_VERIFIER,
        },
        verify=certifi.where(),
        timeout=30,
    )
    return r.json()

def save_to_env(key, value):
    """Aggiorna una variabile nel .env senza sovrascrivere le altre."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    with open(env_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    updated = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            updated = True
        else:
            new_lines.append(line)
    if not updated:
        new_lines.append(f"{key}={value}\n")
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    print(f"  .env aggiornato: {key}=***{value[-6:]}")

if __name__ == "__main__":
    print("=" * 55)
    print("  I-llumin-A — Login TikTok (locale, sicuro)")
    print("=" * 55)

    # Avvia server locale per il callback
    server = http.server.HTTPServer(("localhost", 8080), CallbackHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    print("\n[1] Server locale avviato su http://localhost:8080")

    # Costruisci URL di autorizzazione con PKCE
    auth_url = (
        "https://www.tiktok.com/v2/auth/authorize/"
        f"?client_key={CLIENT_KEY}"
        f"&scope={SCOPE}"
        "&response_type=code"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&state={STATE}"
        f"&code_challenge={CODE_CHALLENGE}"
        "&code_challenge_method=S256"
    )

    print("[2] Apro il browser per il login TikTok...")
    webbrowser.open(auth_url)
    print("[3] Accedi con il tuo account TikTok e autorizza l'app.")
    print("    Attendo il callback...\n")

    # Aspetta il codice (max 3 minuti)
    import time
    for _ in range(180):
        if auth_code:
            break
        time.sleep(1)

    server.shutdown()

    if not auth_code:
        print("[ERR] Timeout — nessun codice ricevuto. Riprova.")
        exit(1)

    print(f"[OK] Codice ricevuto. Scambio con token...")
    data = exchange_code(auth_code)

    if "access_token" not in data:
        print(f"[ERR] Errore TikTok API: {data}")
        exit(1)

    access_token  = data["access_token"]
    refresh_token = data.get("refresh_token", "")

    save_to_env("TIKTOK_ACCESS_TOKEN", access_token)
    if refresh_token:
        save_to_env("TIKTOK_REFRESH_TOKEN", refresh_token)

    print("\n[OK] Token salvato nel .env!")
    print("     La pipeline pubblichera automaticamente nell'inbox TikTok da adesso.")
    print("=" * 55)
