# apps/audio-prep/bootstrap_adaptation.py
import os, json
import requests
import google.auth
from google.auth.transport.requests import Request

PROJECT_ID = os.getenv("PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
LOCATION   = os.getenv("REGION", "global")                       # must match your recognizer location
PHRASE_SET_ID = os.getenv("PHRASE_SET_ID", "ortho_airway_terms") # choose an id you like

ENDPOINT = f"https://speech.googleapis.com/v2/projects/{PROJECT_ID}/locations/{LOCATION}"

def _token():
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(Request())
    return creds.token

def ensure_phrase_set():
    headers = {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}

    # 1) Try to GET existing PhraseSet
    get_url = f"{ENDPOINT}/phraseSets/{PHRASE_SET_ID}"
    r = requests.get(get_url, headers=headers)
    if r.status_code == 200:
        print(r.json()["name"])  # resource name to reuse
        return

    if r.status_code != 404:
        raise RuntimeError(f"GET PhraseSet failed: {r.status_code} {r.text}")

    # 2) Create it once if not found
    body = {
        "displayName": "Ortho/Psych bias terms",
        "phrases": [
            {"value": "orthognathic surgery", "boost": 18},
            {"value": "mandibular advancement", "boost": 15},
            {"value": "tongue space", "boost": 15},
            {"value": "psychiatric clearance", "boost": 12},
            {"value": "Dr. Movahed", "boost": 20},
            {"value": "Pat McBride", "boost": 20},
            # add the names/terms you really care about
        ]
    }
    create_url = f"{ENDPOINT}/phraseSets?phraseSetId={PHRASE_SET_ID}"
    r = requests.post(create_url, headers=headers, data=json.dumps(body))
    if r.status_code not in (200, 201):
        raise RuntimeError(f"CREATE PhraseSet failed: {r.status_code} {r.text}")

    print(r.json()["name"])      # e.g. projects/…/locations/global/phraseSets/ortho_airway_terms

if __name__ == "__main__":
    ensure_phrase_set()
