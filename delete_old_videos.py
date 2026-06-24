"""
Cancella i video del VECCHIO genere (scienza/storia) prima del pivot calcio.
Tiene i pronostici calcio. Chiede conferma prima di cancellare.
Richiede token con scope youtube (gestione) -> rifai yt_auth.py prima.
Uso: py -3 delete_old_videos.py
"""
import os, json, certifi
try:
    import truststore; truststore.inject_into_ssl()
except ImportError:
    pass
os.environ["SSL_CERT_FILE"] = certifi.where()
from dotenv import load_dotenv; load_dotenv()
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Cutoff: primo video calcio pubblicato il 2026-06-23. Tutto PRIMA = vecchio genere.
CUTOFF = "2026-06-23T18:00:00Z"

td = json.loads(os.environ["YOUTUBE_TOKEN_JSON"])
c = Credentials(token=td.get("token"), refresh_token=td.get("refresh_token"),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=td.get("client_id"), client_secret=td.get("client_secret"))
if c.expired:
    c.refresh(Request())
yt = build("youtube", "v3", credentials=c)

# Raccogli tutti i video con data
ch = yt.channels().list(part="contentDetails", mine=True).execute()
up = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

vids = []
page = None
while True:
    pl = yt.playlistItems().list(part="contentDetails,snippet", playlistId=up,
                                 maxResults=50, pageToken=page).execute()
    for it in pl["items"]:
        vids.append({
            "id": it["contentDetails"]["videoId"],
            "pub": it["contentDetails"]["videoPublishedAt"],
            "title": it["snippet"]["title"],
        })
    page = pl.get("nextPageToken")
    if not page:
        break

old = [v for v in vids if v["pub"] < CUTOFF]
keep = [v for v in vids if v["pub"] >= CUTOFF]

print(f"Totale video: {len(vids)}")
print(f"DA CANCELLARE (prima del {CUTOFF}): {len(old)}")
print(f"DA TENERE (calcio): {len(keep)}")
print()
for v in old[:5]:
    print("  CANCELLA:", v["pub"][:10], v["title"][:50])
if len(old) > 5:
    print(f"  ... e altri {len(old)-5}")
print()

resp = input(f"Cancellare {len(old)} video vecchi? Scrivi SI per confermare: ").strip()
if resp != "SI":
    print("Annullato.")
    raise SystemExit(0)

ok, err = 0, 0
for v in old:
    try:
        yt.videos().delete(id=v["id"]).execute()
        ok += 1
        print(f"  [{ok}/{len(old)}] cancellato: {v['title'][:40]}")
    except Exception as e:
        err += 1
        print(f"  [ERR] {v['id']}: {str(e)[:80]}")

print(f"\nFatto. Cancellati {ok}, errori {err}.")
