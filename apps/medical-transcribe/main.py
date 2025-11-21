PHRASESET_NAME = os.getenv("PHRASESET_NAME")  # e.g., "projects/.../phraseSets/psychosomatic_terms"

import os, json, tempfile, subprocess
from functions_framework import cloud_event
from cloudevents.http.event import CloudEvent
from google.cloud import storage
import google.auth
from google.auth.transport.requests import Request
import requests

# Config via env vars
OUTPUT_BUCKET = os.getenv("OUTPUT_BUCKET", "phi-output-encounters")
OUTPUT_PREFIX = os.getenv("OUTPUT_PREFIX", "transcripts/")
PREPPED_BUCKET = os.getenv("PREPPED_BUCKET", "phi-inbound-audio-raw")  # can be same as input
PREPPED_PREFIX = os.getenv("PREPPED_PREFIX", "prepped/")

PROJECT_ID = os.getenv("PROJECT_ID")
PROJECT_NUM = os.getenv("PROJECT_NUM")
REGION = os.getenv("REGION", "global")
MODEL = os.getenv("SPEECH_MODEL", "medical_conversation")

# Build Speech v2 endpoint
SPEECH_URL = f"https://speech.googleapis.com/v2/projects/{PROJECT_ID}/locations/{REGION}/recognizers/_:batchRecognize"

storage_client = storage.Client()

def _token():
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(Request())
    return creds.token

@cloud_event
def handler(event: CloudEvent):
    # Expect Cloud Storage "finalized" event
    data = event.data or {}
    bucket = data.get("bucket")
    name = data.get("name")

    # Guard: only process objects from the intended bucket
    if bucket != "phi-inbound-audio-raw":
        print(f"Skip: unexpected bucket {bucket}")
        return ("", 204)

    # Guard: avoid loops (don’t process our own prepped outputs)
    if name.startswith(PREPPED_PREFIX):
        print(f"Skip: prepped object {name}")
        return ("", 204)

    # Optional: only react to certain suffixes
    # if not (name.endswith(".m4a") or name.endswith(".wav") or name.endswith(".mp3")):
    #     print(f"Skip: not an audio file: {name}")
    #     return ("", 204)

    # Download to /tmp
    src_blob = storage_client.bucket(bucket).blob(name)
    base = os.path.splitext(os.path.basename(name))[0]
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = os.path.join(tmpdir, "in.any")
        dst_path = os.path.join(tmpdir, f"{base}.flac")
        src_blob.download_to_filename(src_path)

        # Convert to FLAC mono 16 kHz, trim obvious head/tail silence
        # Tune thresholds if needed (-50dB here)
        ffmpeg_cmd = [
            "ffmpeg", "-y", "-i", src_path,
            "-af", "silenceremove=start_periods=1:start_duration=0.5:start_threshold=-50dB:"
                   "stop_periods=1:stop_duration=1:stop_threshold=-50dB",
            "-ac", "1", "-ar", "16000", "-c:a", "flac", "-compression_level", "5",
            dst_path
        ]
        subprocess.run(ffmpeg_cmd, check=True)

        # Upload prepped file
        prepped_key = f"{PREPPED_PREFIX}{base}.flac"
        prepped_blob = storage_client.bucket(PREPPED_BUCKET).blob(prepped_key)
        prepped_blob.upload_from_filename(dst_path, content_type="audio/flac")
        prepped_uri = f"gs://{PREPPED_BUCKET}/{prepped_key}"
        print(f"Uploaded prepped: {prepped_uri}")
    
# Build base config once
config = {
    "autoDecodingConfig": {},
    "languageCodes": ["en-US"],
    "model": MODEL,  # e.g., "medical_conversation" or "medical_dictation"
}

# Only attach adaptation if the model supports it (medical_* doesn't)
if PHRASESET_NAME and not MODEL.startswith("medical_"):
    # PHRASESET_NAME should be the full resource name:
    # projects/PROJECT_ID/locations/LOCATION/phraseSets/PHRASESET_ID
    config["adaptation"] = {
        "phraseSets": [{"phraseSet": PHRASESET_NAME}]
    }

# Kick off Speech v2 batchRecognize
payload = {
    "config": config,                          # ✅ just the variable (a dict)
    "files": [{"uri": prepped_uri}],
    "recognitionOutputConfig": {
        # (Optional) ask for extra formats in the output bucket
        "outputFormatConfig": {
            "srt": {},   # SubRip
            "vtt": {}    # WebVTT
        },
        # Write under your transcripts prefix (include trailing '/')
        "gcsOutputConfig": {"uri": f"gs://{OUTPUT_BUCKET}/{OUTPUT_PREFIX}"}
    }
}

headers = {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}
r = requests.post(SPEECH_URL, headers=headers, data=json.dumps(payload), timeout=120)
print(f"Speech batchRecognize status {r.status_code}: {r.text}")
return ("", 204)

if __name__ == "__main__":
    # Local dev: run a simple HTTP server (Functions Framework)
    from functions_framework import create_app
    app = create_app("handler")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
