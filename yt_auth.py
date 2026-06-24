"""
Genera il token OAuth YouTube e lo stampa in formato JSON.
Usa certifi per i certificati SSL su Windows.
"""
import json, os, certifi

# Fix SSL su Windows con Python 3.15
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()
os.environ["SSL_CERT_FILE"] = certifi.where()

from google_auth_oauthlib.flow import InstalledAppFlow

flow = InstalledAppFlow.from_client_secrets_file(
    "yt_credentials.json",
    scopes=[
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.readonly",
        "https://www.googleapis.com/auth/yt-analytics.readonly",
        "https://www.googleapis.com/auth/youtube",  # gestione: cancellare video
    ],
)
creds = flow.run_local_server(port=8765, open_browser=True)

token = json.dumps({
    "token": creds.token,
    "refresh_token": creds.refresh_token,
    "client_id": creds.client_id,
    "client_secret": creds.client_secret
})

print("\n=== YOUTUBE TOKEN JSON ===")
print(token)
print("=== FINE ===\n")

with open("yt_token.json", "w") as f:
    f.write(token)

# Salva diretto in .env (sostituisce YOUTUBE_TOKEN_JSON)
env_path = ".env"
lines = open(env_path, encoding="utf-8").read().splitlines()
out, found = [], False
for line in lines:
    if line.startswith("YOUTUBE_TOKEN_JSON="):
        out.append("YOUTUBE_TOKEN_JSON=" + token); found = True
    else:
        out.append(line)
if not found:
    out.append("YOUTUBE_TOKEN_JSON=" + token)
open(env_path, "w", encoding="utf-8").write("\n".join(out) + "\n")
print("Token salvato in .env (scope upload+readonly+analytics)")
