import os
import json
import time
import tempfile
import subprocess
from typing import Tuple

from functions_framework import cloud_event
from google.cloud import storage
import google.auth
from google.auth.transport.requests import Request
import requests

# ---------- Configuration via env ----------
PROJECT_ID = os.getenv("PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
RUN_REGION_FOR_SPEECH = os.getenv("REGION", "global")  # v2 Speech recognizers; 'global' is fine
PREPPED_BUCKET = os.getenv("PREPPED_BUCKET", "phi-inbound-audio-raw")
PREPPED_PREFIX = os.getenv("PREPPED_PREFIX", "prepped/")
OUTPUT_BUCKET = os.getenv("OUTPUT_BUCKET", "phi-output-encounters")
OUTPUT_PREFIX = os.getenv("OUTPUT_PREFIX", "transcripts/")
SPEECH_MODEL = os.getenv("SPEECH_MODEL", "medical_conversation")

# Validate env early (avoid opaque errors later)
if not PROJECT_ID:
    raise RuntimeError("PROJECT_ID/GOOGLE_CLOUD_PROJECT is not set")

# ---------- GCS client ----------
storage_client = storage.Client()

# ---------- Helpers ----------
AUDIO_EXTS = (".wav", ".flac", ".m4a", ".mp3", ".aac", ".ogg", ".opus", ".aiff", ".aif")

def is_audio_event(obj_name: str, content_type: str) -> bool:
    if content_type and content_type.lower().startswith("audio/"):
        return True
    if obj_name:
        return obj_name.lower().endswith(AUDIO_EXTS)
    return False

def to_mono_wav(src_path: str, dst_path: str) -> Tuple[int, str]:
    """
    Convert input file to mono 16 kHz PCM16 WAV.
    Returns (returncode, stderr_text) so we can degrade gracefully on errors.
    """
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-y", "-i", src_path, "-ac", "1", "-ar", "16000",
        "-c:a", "pcm_s16le", dst_path,
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc.returncode, proc.stderr.decode("utf-8", "ignore")

def get_token() -> str:
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(Request())
    return creds.token

def derive_labels_from_path(name: str) -> Tuple[str, str]:
    """
    Optional convenience: extract provider_id / visit_id from GCS object name if present
    e.g. provider/<prov>/visit/<visit>/zoom/file.m4a
    """
    parts = (name or "").split("/")
    provider_id = "unknown"
    visit_id = "unknown"
    try:
        i = parts.index("provider")
        provider_id = parts[i + 1]
    except Exception:
        pass
    try:
        j = parts.index("visit")
        visit_id = parts[j + 1]
    except Exception:
        pass
    return provider_id, visit_id

def safe_download(blob: storage.Blob, local_path: str, attempts: int = 3) -> bool:
    """
    Download with short retries to avoid read-after-finalize 404.
    """
    for attempt in range(attempts):
        try:
            blob.download_to_filename(local_path)
            return True
        except Exception as e:
            if attempt == attempts - 1:
                print(f"Download failed after {attempts} attempts: {e}")
                return False
            time.sleep(0.5 * (attempt + 1))
    return False

def speech_batch_recognize(gcs_input_uri: str) -> requests.Response:
    """
    Kick off Speech v2 batchRecognize with medical model and output to GCS.
    """
    url = (
        f"https://speech.googleapis.com/v2/projects/{PROJECT_ID}"
        f"/locations/{RUN_REGION_FOR_SPEECH}/recognizers/_:batchRecognize"
    )
    payload = {
        "config": {
            "autoDecodingConfig": {},
            "languageCodes": ["en-US"],
            "model": SPEECH_MODEL,
        },
        "files": [{"uri": gcs_input_uri}],
        "recognitionOutputConfig": {
            "gcsOutputConfig": {"uri": f"gs://{OUTPUT_BUCKET}/{OUTPUT_PREFIX}"}
        },
    }
    headers = {"Authorization": f"Bearer {get_token()}", "Content-Type": "application/json"}
    resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=120)
    return resp

# ---------- CloudEvent entrypoint ----------
@cloud_event
def handle(event):
    data = event.data or {}
    bucket = data.get("bucket")
    name = data.get("name")
    content_type = data.get("contentType") or ""

    # Skip missing names
    if not name:
        print("Skip event with empty object name")
        return ("", 204)

    # Skip our own outputs (avoid loops) and non-audio objects (e.g., .txt diagnostic files)
    if name.startswith(PREPPED_PREFIX):
        print(f"Skip prepped object: {name}")
        return ("", 204)
    if not is_audio_event(name, content_type):
        print(f"Skip non-audio object: gs://{bucket}/{name} (contentType={content_type})")
        return ("", 204)

    print(f"Processing gs://{bucket}/{name} (contentType={content_type})")

    # Prepare temp files, derive labels
    provider_id, visit_id = derive_labels_from_path(name)
    base = os.path.splitext(os.path.basename(name))[0]

    with tempfile.TemporaryDirectory() as tmpdir:
        local_in = os.path.join(tmpdir, "in.any")
        local_out = os.path.join(tmpdir, f"{base}.wav")

        # Download with small retry
        src_blob = storage_client.bucket(bucket).blob(name)
        if not safe_download(src_blob, local_in):
            print(f"Skip: could not download gs://{bucket}/{name}")
            return ("", 204)

        # Convert to WAV
        rc, err = to_mono_wav(local_in, local_out)
        if rc != 0:
            print(f"ffmpeg failed ({rc}) on {name}\n{err[:800]}")
            return ("", 204)

        # Upload prepped
        prepped_key = f"{PREPPED_PREFIX}provider/{provider_id}/visit/{visit_id}/{base}.wav"
        prepped_blob = storage_client.bucket(PREPPED_BUCKET).blob(prepped_key)
        prepped_blob.upload_from_filename(local_out, content_type="audio/wav")
        # Add simple metadata
        prepped_blob.metadata = {
            "provider_id": provider_id,
            "visit_id": visit_id,
            "src": f"gs://{bucket}/{name}",
        }
        try:
            prepped_blob.patch()
        except Exception:
            pass

        prepped_uri = f"gs://{PREPPED_BUCKET}/{prepped_key}"
        print(f"Uploaded prepped: {prepped_uri}")

    # Speech v2 batch
    resp = speech_batch_recognize(prepped_uri)
    print(f"Speech batchRecognize -> status {resp.status_code}")
    if resp.status_code >= 300:
        print(resp.text[:1000])

    return ("", 204)
