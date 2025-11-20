import os
from google.api_core.exceptions import NotFound
from google.cloud.speech_v2 import SpeechClient
from google.cloud.speech_v2.types import cloud_speech

PROJECT_ID = os.environ["GOOGLE_CLOUD_PROJECT"]
LOCATION   = os.getenv("SPEECH_LOCATION", "us-central1")  # must match your recognizer region
PHRASE_SET_ID = "ortho_airway_terms"
PHRASE_SET_NAME = f"projects/{PROJECT_ID}/locations/{LOCATION}/phraseSets/{PHRASE_SET_ID}"

# Optional: if you use a regional location, set the regional endpoint
client = SpeechClient(client_options={"api_endpoint": f"{LOCATION}-speech.googleapis.com"})

def ensure_phrase_set():
    # 1) Reuse if it already exists
    try:
        client.get_phrase_set(name=PHRASE_SET_NAME)
        return PHRASE_SET_NAME
    except NotFound:
        pass

    # 2) Otherwise create it once (LRO; wait until done)
    phrases = [
        {"value": "orthognathic surgery", "boost": 18},
        {"value": "mandibular advancement", "boost": 15},
        {"value": "Dr. Movahed", "boost": 20},
        {"value": "Pat McBride", "boost": 20},
        {"value": "psychiatric clearance", "boost": 12},
    ]

    op = client.create_phrase_set(
        parent=f"projects/{PROJECT_ID}/locations/{LOCATION}",
        phrase_set=cloud_speech.PhraseSet(
            display_name="Ortho/Psych bias terms",
            phrases=[cloud_speech.PhraseSet.Phrase(**p) for p in phrases],
            # Optional: set a default boost here; per-phrase boosts can override
            boost=15.0,
        ),
        phrase_set_id=PHRASE_SET_ID,
    )

    phrase_set = op.result()  # wait for creation to finish
    return phrase_set.name

if __name__ == "__main__":
    name = ensure_phrase_set()
    print("PhraseSet ready:", name)
