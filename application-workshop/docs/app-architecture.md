# Application & Manifest Architecture (`translate-api` & `upload-api`)

This document details the architecture of the two reference workloads included under [`apps/`](../apps/) and how their manifests integrate into a single GitLab project repository managed by ArgoCD.

---

## 1. Multi-Workload & Multi-Image Repository Structure

Inside `application-workshop/apps/`, each workload contains its service directory (or directories) with a `Dockerfile` alongside a `manifests/` folder:

```text
apps/
├── translate-api/                  # Multi-Image Stateless Workload (2 Dockerfiles)
│   ├── frontend/                   # Service 1: React 19 SPA + Nginx (Dockerfile -> frontend:<tag>)
│   ├── api/                        # Service 2: Python Flask API (Dockerfile -> api:<tag>)
│   └── manifests/                  # Deployment (2 containers), Service, ConfigMap & Secret overlays
└── upload-api/                     # Single-Image Stateful Storage Workload (1 Dockerfile)
    ├── app/                        # Flask + Boto3 Archive Vault (Dockerfile -> upload-api:<tag>)
    └── manifests/                  # StatefulSet, 10Gi PVC, Service & RoleBinding overlays
```

`scripts/build_and_push.py` searches `apps/<app-name>/` recursively for `Dockerfile`s:
- Service subfolders (`frontend/Dockerfile`, `api/Dockerfile`) implicitly build `<service>:<tag>` (`frontend:<tag>`, `api:<tag>`) and populate `IMAGE_FRONTEND` and `IMAGE_API` in `base/app.properties`.
- A single `app/Dockerfile` builds `<app-name>:<tag>` (`upload-api:<tag>`) and populates `IMAGE` (and `IMAGE_UPLOAD_API`) in `base/app.properties`.

When `scripts/push_manifests.py` ships a workload into its dedicated GitLab project repository (`<group>/<project>.git` created in `gitops-workshop`), the GitLab repository holds **only** the declarative manifests:

```text
<group>/<project>.git
├── README.md
└── manifests/
    ├── kustomization.yaml          # Watched by <project>-apps in ArgoCD
    ├── project.yaml                # AppProject created by gitops-workshop
    ├── <app-name>-app.yaml         # ArgoCD Application -> manifests/<app-name>/overlays/{gdc,gcp}
    └── <app-name>/
        ├── base/                   # Deployment/StatefulSet, Service, Kustomize generators
        └── overlays/{gdc,gcp}/     # Environment-specific Kustomize overlays
```

---

## 2. Workload 1: `translate-api` (Multi-Container Stateless Deployment)

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                    Pod: translate-api (UID 1000)                        │
│                                                                         │
│  ┌───────────────────────────────────┐    ┌──────────────────────────┐  │
│  │ Container 1: frontend (:8080)     │    │ Container 2: api (:5000) │  │
│  │ • Static React 19 SPA (/app/static│───►│ • Flask + Gunicorn API   │  │
│  │ • Nginx Proxy (/translate, /api)  │    │ • Cloud / Air-Gap Engine │  │
│  └───────────────────────────────────┘    └──────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

- **Kubernetes Kind**: `Deployment` (2 replicas, 2 containers per pod: `frontend` and `api`) + `ClusterIP` `Service` (`80 -> 8080`).
- **Configuration & Secrets**: Kustomize `configMapGenerator` (`app.properties`) and `secretGenerator` (`app-secrets.properties`) with `replacements` injecting `data.IMAGE_FRONTEND` into `containers[0].image` and `data.IMAGE_API` into `containers[1].image`.

---

## 3. Workload 2: `upload-api` (StatefulSet + PersistentVolumeClaim + Object Storage)

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                     StatefulSet Pod: upload-api-0 (UID 1000)            │
│                                                                         │
│  Client HTTP :8080 ──► Gunicorn + Flask Archive Service (main.py)       │
│                         ├─► /uploads   10Gi PVC (standard-rwo)          │
│                         └─► Boto3 S3   Optional GDC Object Storage Sync │
└─────────────────────────────────────────────────────────────────────────┘
```

- **Kubernetes Kind**: `StatefulSet` (`serviceName: upload-api`, 1 replica) + `ClusterIP` `Service` (`80 -> 8080`) + `RoleBinding` (`readwrite-all-buckets`).
- **Dynamic Block Storage (`volumeClaimTemplates`)**:
  - Automatically provisions `PersistentVolumeClaim` `data-upload-api-0` (`10Gi`, `ReadWriteOnce`, `storageClassName: standard-rwo`) mounted at `/uploads`.
  - Files uploaded via `POST /upload` or generated via the Web UI (`GET /`) persist across pod restarts with MD5 and SHA-256 verification.
- **Kustomize `replacements`**:
  - Substitutes `IMAGE`, `BUCKET_NAME`, and `STORAGE_ENDPOINT` from `upload-api-config` into `StatefulSet/upload-api` and `PLATFORM_ADMIN` into `RoleBinding/readwrite-all-buckets`.
