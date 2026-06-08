"""
Login TikTok sandbox per I-llumin-A.
Redirect via GitHub Pages (sandbox vieta localhost). Paste manuale del codice.
Uso: py -3 tiktok_auth.py
"""
import os, secrets, webbrowser, urllib.parse, hashlib, base64
import requests, truststore, certifi
truststore.inject_into_ssl()
from dotenv import load_dotenv
load_dotenv()

CLIENT_KEY    = os.environ["TIKTOK_CLIENT_KEY"]
CLIENT_SECRET = os.environ["TIKTOK_CLIENT_SECRET"]
REDIRECT_URI  = "https://illumina10101-10.github.io/i-llumin-a/callback.html"
SCOPE         = "video.publish"
STATE         = secrets.token_hex(8)

# PKCE
CODE_VERIFIER  = secrets.token_urlsafe(64)
CODE_CHALLENGE = base64.urlsafe_b64encode(
    hashlib.sha256(CODE_VERIFIER.encode()).digest()
).rstrip(b"=").decode()


def exchange_code(code):
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
        verify=certifi.where(), timeout=30,
    )
    return r.json()


def save_to_env(key, value):
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    lines = open(env_path, encoding="utf-8").read().splitlines()
    out, found = [], False
    for line in lines:
        if line.startswith(f"{key}="):
            out.append(f"{key}={value}"); found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{key}={value}")
    open(env_path, "w", encoding="utf-8").write("\n".join(out) + "\n")
    print(f"  .env aggiornato: {key}=***{value[-6:]}")


if __name__ == "__main__":
    print("=" * 55)
    print("  I-llumin-A — Login TikTok Sandbox")
    print("=" * 55)

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

    print("\n[1] Apro browser per login TikTok...")
    print("    (accedi col tuo account, autorizza l'app)")
    webbrowser.open(auth_url)

    print("\n[2] Dopo l'autorizzazione vieni rediretto a una pagina")
    print("    che mostra un CODICE. Copialo e incollalo qui sotto.\n")
    code = input("Incolla il codice: ").strip()

    if not code:
        print("[ERR] Nessun codice inserito.")
        raise SystemExit(1)

    # Pulisci solo se incollato URL intero (tieni il codice completo, anche con *)
    if "code=" in code:
        code = code.split("code=")[1].split("&")[0]
    code = urllib.parse.unquote(code)

    print("\n[3] Scambio codice con token...")
    data = exchange_code(code)

    if "access_token" not in data:
        print(f"[ERR] TikTok API: {data}")
        raise SystemExit(1)

    save_to_env("TIKTOK_ACCESS_TOKEN", data["access_token"])
    if data.get("refresh_token"):
        save_to_env("TIKTOK_REFRESH_TOKEN", data["refresh_token"])

    print("\n[OK] Token salvato! Bot puo pubblicare in inbox TikTok.")
    print("=" * 55)
