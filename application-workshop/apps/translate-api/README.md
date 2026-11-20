# Translate API Workload (`apps/translate-api/`)

A multi-service **Translation Portal** workload consisting of two container services (`frontend/` and `api/`) discovered and built automatically by `scripts/build_and_push.py`:

## Structure

- **`frontend/` (`frontend:<tag>`)**: React 19 + Material UI (MUI v7) + TypeScript single-page application built with Vite and served by a non-root Nginx reverse proxy (`UID 1000`) on port `8080`, proxying `/translate`, `/api`, and `/healthz` to `http://127.0.0.1:5000`.
- **`api/` (`api:<tag>`)**: Python Flask + Gunicorn REST API (`main.py`, `UID 1000`) on port `5000` supporting Google Cloud / GDC Translation API keys and a built-in air-gapped translation engine.
- **`manifests/`**: Declarative Kustomize base (`Deployment` with `frontend` and `api` containers, `Service`, `ConfigMap`, `Secret`, and Kustomize `replacements` for `IMAGE_FRONTEND` and `IMAGE_API`) plus environment overlays (`overlays/gdc/`, `overlays/gcp/`).

## Build & Deploy

```bash
# Step 1: Auto-discover frontend/Dockerfile and api/Dockerfile, build & push both images
python3 scripts/build_and_push.py -r workloads/translate-project -a translate-api

# Step 2: Overwrite manifests/ in workloads/translate-project and push MR
python3 scripts/push_manifests.py -r workloads/translate-project -a translate-api
```
