# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Stateful Archive Ingestion & Storage Service (upload-api).

Persists uploaded archive bundles (.zip, .tar, .gz, .tgz, .tar.gz) onto a
Kubernetes StatefulSet PersistentVolumeClaim (/uploads) and optionally
replicates objects to S3-compatible GDC Object Storage.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import io
import logging
import os
import shutil
import socket
import zipfile

import boto3
from botocore.exceptions import ClientError
from flask import Flask, jsonify, make_response, render_template_string, request, send_from_directory
from werkzeug.utils import secure_filename

app = Flask(__name__)

UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", "/uploads")
BUCKET_NAME = os.environ.get("BUCKET_NAME", "")
STORAGE_ENDPOINT = os.environ.get("STORAGE_ENDPOINT", "")
ACCESS_KEY_ID = os.environ.get("ACCESS_KEY_ID", "")
SECRET_ACCESS_KEY = os.environ.get("SECRET_ACCESS_KEY", "")

app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = (".zip", ".tar", ".gz", ".tgz", ".tar.gz")
app.config["ALLOWED_EXTENSIONS"] = ALLOWED_EXTENSIONS

logging.basicConfig(level=logging.INFO)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename: str) -> bool:
    if not filename:
        return False
    return filename.lower().endswith(app.config["ALLOWED_EXTENSIONS"])


def calculate_digests(filepath: str) -> dict:
    hash_md5 = hashlib.md5()
    hash_sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hash_md5.update(chunk)
            hash_sha256.update(chunk)
    return {
        "md5_hex": hash_md5.hexdigest(),
        "md5_b64": base64.b64encode(hash_md5.digest()).decode("utf-8"),
        "sha256_hex": hash_sha256.hexdigest(),
    }


def get_storage_metrics() -> dict:
    usage = shutil.disk_usage(UPLOAD_FOLDER)
    return {
        "mount_path": UPLOAD_FOLDER,
        "pod_hostname": socket.gethostname(),
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "total_gb": round(usage.total / (1024**3), 2),
        "used_mb": round(usage.used / (1024**2), 2),
        "free_gb": round(usage.free / (1024**3), 2),
        "s3_bucket": BUCKET_NAME or "Not configured (local PVC mode)",
        "s3_endpoint": STORAGE_ENDPOINT or "Not configured",
        "s3_replication_enabled": bool(BUCKET_NAME and STORAGE_ENDPOINT and ACCESS_KEY_ID and SECRET_ACCESS_KEY),
    }


def list_persisted_files() -> list:
    items = []
    if not os.path.exists(UPLOAD_FOLDER):
        return items
    for fname in sorted(os.listdir(UPLOAD_FOLDER)):
        fpath = os.path.join(UPLOAD_FOLDER, fname)
        if not os.path.isfile(fpath) or fname.startswith("."):
            continue
        stat = os.stat(fpath)
        digests = calculate_digests(fpath)
        items.append(
            {
                "filename": fname,
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "md5": digests["md5_hex"],
                "sha256": digests["sha256_hex"][:16] + "...",
            }
        )
    return items


def upload_to_cloud_storage(file_path: str, filename: str) -> tuple[bool, str]:
    """Replicate the archive to S3-compatible GDC Object Storage when configured."""
    if not (BUCKET_NAME and STORAGE_ENDPOINT and ACCESS_KEY_ID and SECRET_ACCESS_KEY):
        return False, "Skipped (using StatefulSet PersistentVolumeClaim storage; S3 credentials not set)"

    verify_cert = "trusted_certs.crt" if os.path.exists("trusted_certs.crt") else True
    try:
        s3_client = boto3.client(
            "s3",
            aws_access_key_id=ACCESS_KEY_ID,
            aws_secret_access_key=SECRET_ACCESS_KEY,
            endpoint_url=STORAGE_ENDPOINT,
            region_name="zone1",
            verify=verify_cert,
            config=boto3.session.Config(s3={"addressing_style": "path"}),
        )
        with open(file_path, "rb") as f:
            s3_client.put_object(
                Body=f,
                Bucket=BUCKET_NAME,
                Key=filename,
                ChecksumAlgorithm="SHA1",
            )
        app.logger.info(f"Successfully replicated {filename} to bucket {BUCKET_NAME}.")
        return True, f"Replicated to s3://{BUCKET_NAME}/{filename}"
    except (ClientError, Exception) as exc:
        app.logger.warning(f"S3 replication failed for {filename}: {exc}")
        return False, f"PVC saved; S3 replication skipped ({exc})"


INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Archive Storage Vault (upload-api)</title>
  <style>
    :root {
      --primary: #1976d2;
      --primary-dark: #115293;
      --bg: #f4f6f9;
      --card: #ffffff;
      --text: #1e293b;
      --muted: #64748b;
      --border: #e2e8f0;
      --success: #16a34a;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text); }
    header { background: #fff; border-bottom: 1px solid var(--border); padding: 16px 32px; display: flex; justify-content: space-between; align-items: center; }
    header h1 { font-size: 1.25rem; font-weight: 700; color: var(--text); }
    .badge { font-size: 0.78rem; padding: 4px 10px; border-radius: 999px; border: 1px solid var(--primary); color: var(--primary); font-weight: 600; }
    main { max-width: 960px; margin: 32px auto; padding: 0 20px; display: flex; flex-direction: column; gap: 24px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 16px; }
    .card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 20px; box-shadow: 0 1px 2px rgba(0,0,0,0.04); }
    .metric-label { font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); margin-bottom: 6px; }
    .metric-value { font-size: 1.15rem; font-weight: 700; word-break: break-all; }
    .actions { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin-top: 12px; }
    button, .btn { background: var(--primary); color: #fff; border: none; padding: 10px 18px; border-radius: 6px; font-weight: 600; cursor: pointer; font-size: 0.9rem; }
    button:hover { background: var(--primary-dark); }
    button.secondary { background: #0f172a; }
    input[type="file"] { border: 1px dashed var(--border); padding: 8px 12px; border-radius: 6px; background: #f8fafc; }
    table { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 0.9rem; }
    th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--border); }
    th { color: var(--muted); font-weight: 600; font-size: 0.8rem; text-transform: uppercase; }
    code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.82rem; background: #f1f5f9; padding: 2px 6px; border-radius: 4px; }
    #status-banner { display: none; padding: 12px 16px; border-radius: 6px; font-size: 0.9rem; font-weight: 500; }
  </style>
</head>
<body>
  <header>
    <h1>Stateful Archive Storage Vault (upload-api)</h1>
    <span class="badge">StatefulSet + PersistentVolumeClaim</span>
  </header>
  <main>
    <div class="grid">
      <div class="card">
        <div class="metric-label">StatefulSet Pod</div>
        <div class="metric-value" id="pod-name">{{ metrics.pod_hostname }}</div>
      </div>
      <div class="card">
        <div class="metric-label">PVC Mount Path</div>
        <div class="metric-value"><code>{{ metrics.mount_path }}</code></div>
      </div>
      <div class="card">
        <div class="metric-label">Volume Free / Total</div>
        <div class="metric-value">{{ metrics.free_gb }} GiB / {{ metrics.total_gb }} GiB</div>
      </div>
      <div class="card">
        <div class="metric-label">Object Storage Target</div>
        <div class="metric-value" style="font-size:0.9rem">{{ metrics.s3_bucket }}</div>
      </div>
    </div>

    <div class="card">
      <h2 style="font-size:1.05rem; margin-bottom:6px;">Ingest Archive Bundle</h2>
      <p style="font-size:0.88rem; color:var(--muted);">Upload a <code>.zip</code>, <code>.tar</code>, <code>.gz</code>, or <code>.tgz</code> archive to persist on the attached Kubernetes PersistentVolumeClaim.</p>
      <div id="status-banner" style="margin-top:12px;"></div>
      <div class="actions">
        <input type="file" id="archive-input" accept=".zip,.tar,.gz,.tgz,.tar.gz" />
        <button onclick="uploadSelected()">Upload Archive</button>
        <button class="secondary" onclick="generateSample()">Generate & Persist Sample Archive (.zip)</button>
      </div>
    </div>

    <div class="card">
      <h2 style="font-size:1.05rem; margin-bottom:6px;">Persisted Archives on Volume (<code>{{ metrics.mount_path }}</code>)</h2>
      <table>
        <thead>
          <tr>
            <th>Filename</th>
            <th>Size (Bytes)</th>
            <th>MD5 Digest</th>
            <th>SHA-256 Prefix</th>
            <th>Timestamp (UTC)</th>
            <th>Download</th>
          </tr>
        </thead>
        <tbody id="files-body">
          {% for f in files %}
          <tr>
            <td><strong>{{ f.filename }}</strong></td>
            <td>{{ f.size_bytes }}</td>
            <td><code>{{ f.md5 }}</code></td>
            <td><code>{{ f.sha256 }}</code></td>
            <td>{{ f.modified_at }}</td>
            <td><a href="/files/{{ f.filename }}">Download</a></td>
          </tr>
          {% else %}
          <tr><td colspan="6" style="color:var(--muted); text-align:center; padding:20px;">No archives persisted yet. Click "Generate & Persist Sample Archive" above to test volume persistence.</td></tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </main>

  <script>
    function showBanner(msg, ok) {
      const el = document.getElementById('status-banner');
      el.style.display = 'block';
      el.style.background = ok ? '#dcfce7' : '#fee2e2';
      el.style.color = ok ? '#166534' : '#991b1b';
      el.textContent = msg;
    }
    async function uploadSelected() {
      const input = document.getElementById('archive-input');
      if (!input.files.length) {
        showBanner('Please select an archive file (.zip, .tar, .gz, .tgz) first.', false);
        return;
      }
      const formData = new FormData();
      formData.append('file', input.files[0]);
      const res = await fetch('/upload', { method: 'POST', body: formData });
      const data = await res.json();
      if (res.ok) {
        showBanner(data.message + ' (MD5: ' + data.md5 + ')', true);
        setTimeout(() => window.location.reload(), 600);
      } else {
        showBanner(data.error || 'Upload failed', false);
      }
    }
    async function generateSample() {
      const res = await fetch('/upload', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ generate_sample: true })
      });
      const data = await res.json();
      if (res.ok) {
        showBanner(data.message + ' (MD5: ' + data.md5 + ')', true);
        setTimeout(() => window.location.reload(), 600);
      } else {
        showBanner(data.error || 'Failed to generate sample archive', false);
      }
    }
  </script>
</body>
</html>
"""


@app.route("/", methods=["GET"])
def index():
    """Render the Archive Storage Vault UI."""
    return render_template_string(
        INDEX_HTML,
        metrics=get_storage_metrics(),
        files=list_persisted_files(),
    )


@app.route("/healthz", methods=["GET"])
def healthz():
    """Kubernetes liveness and readiness probe."""
    writable = os.path.isdir(UPLOAD_FOLDER) and os.access(UPLOAD_FOLDER, os.W_OK)
    status_code = 200 if writable else 503
    return (
        jsonify(
            {
                "status": "healthy" if writable else "unhealthy",
                "service": "upload-api",
                "storage_mount": UPLOAD_FOLDER,
                "writable": writable,
                "pod": socket.gethostname(),
            }
        ),
        status_code,
    )


@app.route("/files", methods=["GET"])
def get_files():
    """Return JSON inventory of persisted archives and PVC storage metrics."""
    return jsonify(
        {
            "service": "upload-api",
            "storage": get_storage_metrics(),
            "files": list_persisted_files(),
        }
    )


@app.route("/files/<path:filename>", methods=["GET"])
def download_file(filename: str):
    """Download a persisted archive from the volume."""
    safe_name = secure_filename(filename)
    return send_from_directory(app.config["UPLOAD_FOLDER"], safe_name, as_attachment=True)


@app.route("/upload", methods=["POST"])
def upload_file():
    """Ingest and persist an archive onto the StatefulSet PVC and optional S3 bucket."""
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        if payload.get("generate_sample"):
            ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
            filename = f"telemetry-bundle-{ts}.zip"
            dest_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(
                    "manifest.json",
                    f'{{"bundle": "{filename}", "pod": "{socket.gethostname()}", "timestamp": "{ts}"}}\n',
                )
            with open(dest_path, "wb") as f:
                f.write(buf.getvalue())
            digests = calculate_digests(dest_path)
            s3_ok, s3_msg = upload_to_cloud_storage(dest_path, filename)
            return make_response(
                jsonify(
                    {
                        "message": f"Sample archive '{filename}' persisted to {dest_path}.",
                        "status": "success",
                        "saved_to": dest_path,
                        "md5": digests["md5_hex"],
                        "sha256": digests["sha256_hex"],
                        "s3_replication": {"replicated": s3_ok, "detail": s3_msg},
                    }
                ),
                201,
            )

    if "file" not in request.files:
        return make_response(jsonify({"error": "No 'file' key in request data."}), 400)

    file = request.files["file"]
    if not file.filename:
        return make_response(jsonify({"error": "No selected file provided."}), 400)

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        dest_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        try:
            file.save(dest_path)
            digests = calculate_digests(dest_path)
            s3_ok, s3_msg = upload_to_cloud_storage(dest_path, filename)
            return make_response(
                jsonify(
                    {
                        "message": f"File '{filename}' received and persisted successfully.",
                        "status": "success",
                        "saved_to": dest_path,
                        "md5": digests["md5_hex"],
                        "sha256": digests["sha256_hex"],
                        "s3_replication": {"replicated": s3_ok, "detail": s3_msg},
                    }
                ),
                201,
            )
        except Exception as exc:
            return make_response(jsonify({"error": f"Failed to persist file: {exc}"}), 500)

    error_msg = (
        f"File type not allowed. Accepted archive formats: {', '.join(app.config['ALLOWED_EXTENSIONS'])} "
        f"(max 100MB)."
    )
    return make_response(jsonify({"error": error_msg}), 400)


@app.errorhandler(413)
def request_entity_too_large(error):
    return make_response(
        jsonify({"error": "File upload failed: Payload exceeds 100MB limit."}),
        413,
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=False, host="0.0.0.0", port=port)
