# Upload API Workload (`apps/upload-api/`)

A stateful **Archive Ingestion & Storage Vault** workload deployed as a Kubernetes **`StatefulSet`** with a **`10Gi` PersistentVolumeClaim (`volumeClaimTemplates`)**, RBAC `RoleBinding`, and optional **GDC Object Storage (S3)** bucket replication.

## Infrastructure Highlights

Unlike stateless web deployments, `upload-api` demonstrates how to ship workloads with persistent infrastructure requirements via GitOps:

- **StatefulSet & Dynamic PVC Provisioning**: Requests a dedicated `10Gi` `ReadWriteOnce` persistent volume (`storageClassName: standard-rwo`) mounted at `/uploads` via `volumeClaimTemplates`.
- **Dual-Tier Storage (Block PVC + S3 Object Storage)**: Persists uploaded `.zip`, `.tar`, `.gz`, and `.tgz` archives directly to the attached block volume with MD5/SHA-256 checksum verification, and replicates objects to S3-compatible GDC Object Storage when bucket credentials are configured.
- **RBAC Policy**: Includes a declarative `RoleBinding` (`readwrite-all-buckets`) parameterized via Kustomize `replacements`.

## Build & Deploy

```bash
# Step 1: Build image and push to Harbor / Artifact Registry
python3 scripts/build_and_push.py -a upload-api

# Step 2: Integrate manifests into your GitLab project repo and push
python3 scripts/push_manifests.py -a upload-api
```
