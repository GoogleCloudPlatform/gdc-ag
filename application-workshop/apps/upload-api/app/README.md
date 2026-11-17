# Upload API Application (`apps/upload-api/app/`)

This directory contains the Python Flask + Boto3 source code and non-root `Dockerfile` for the stateful **Upload API** workload.

## Endpoints

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/` | `GET` | Serves the Archive Storage Vault Web UI (PVC usage, upload form, 1-click sample archive generator, and stored file inventory) |
| `/upload` | `POST` | Accepts multipart archive uploads (`.zip`, `.tar`, `.gz`, `.tgz`, `.tar.gz`), writes to `/uploads` PVC, computes MD5/SHA-256 digests, and optionally replicates to S3 Object Storage |
| `/files` | `GET` | Lists all archives persisted on the `/uploads` PersistentVolumeClaim along with volume capacity metrics |
| `/healthz` | `GET` | Kubernetes liveness and readiness probe verifying `/uploads` mount health |
