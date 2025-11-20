--- a/apps/medical-transcribe/app.py
+++ b/apps/medical-transcribe/app.py
@@
-import os, json, tempfile, subprocess
+import os, json, tempfile, subprocess, time
@@
-def to_mono_wav(src_path, dst_path):
-    cmd = ['ffmpeg', '-y', '-i', src_path, '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', dst_path]
+def to_mono_wav(src_path, dst_path):
+    # quieter ffmpeg output; fail fast on decode errors
+    cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error',
+           '-y', '-i', src_path, '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', dst_path]
     subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
@@
+ALLOWED_EXT = {'.wav', '.flac', '.m4a', '.mp3', '.aac', '.ogg'}
+def is_audio_event(data: dict) -> bool:
+    ct = (data.get('contentType') or '').lower()
+    if ct.startswith('audio/'):
+        return True
+    name = data.get('name', '')
+    ext = os.path.splitext(name)[1].lower()
+    return ext in ALLOWED_EXT
@@
 def handler(cloud_event):
     data = cloud_event.data or {}
-    bucket = data.get("bucket"); name = data.get("name")
+    bucket = data.get("bucket"); name = data.get("name")
+
+    # Skip our own outputs and any non‑audio files (like .txt test drops)
+    prepped_prefix = os.getenv("PREPPED_PREFIX", "prepped/")
+    if not name or name.startswith(prepped_prefix) or not is_audio_event(data):
+        print(f"Skip object name={name} contentType={data.get('contentType')} size={data.get('size')}")
+        return ("", 204)
@@
-    raw_blob.download_to_filename(local_in)
+    # Small retry loop in case of rare read-after-new 404s
+    for attempt in range(3):
+        try:
+            raw_blob.download_to_filename(local_in)
+            break
+        except Exception as e:
+            if attempt == 2:
+                raise
+            time.sleep(0.5 * (attempt + 1))
