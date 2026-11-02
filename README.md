# Google Distributed Cloud - Air Gapped (GDC-AG) Resources

This repository is a collection of tools, automation scripts, and hands-on workshops designed for **Google Distributed Cloud - Air Gapped (GDC-AG)**. 

GDC-AG brings Google Cloud services to disconnected and highly regulated environments. This repository provides resources to help developers, architects, and partners build, deploy, and manage workloads on GDC-AG effectively.

> [!WARNING]
> **Non-Production Environment:** The resources and environments described in this repository (including the GDC Sandbox) are intended for **educational and testing purposes only**. They are NOT designed for production workloads.
>
> **Data Sensitivity:** Do NOT upload, process, or store any real sensitive, proprietary, or regulated data within these environments. Always use synthetic or publicly available data for your testing and learning.

## 🎯 Target Audience

- **Google Engineers & Customer Engineers:** Resources for customer engagements, demos, and proof-of-concepts.
- **Partners & ISVs:** Guidance on porting, validating, and optimizing applications for GDC-AG.
- **Customer Developers:** Practical examples and guided workshops for learning the platform's capabilities.

## 📂 Workshops Catalog

This repository organizes hands-on workshops as **independent, self-contained tracks** at the top level. You can run any workshop directly without completing the others:

| Workshop | Target Environment | What You Will Build & Learn | Entry Point |
| :--- | :--- | :--- | :--- |
| **[GDC Sandbox Workshop](./gdc-sandbox-workshop/)** | GDC Sandbox | Project & landing zone automation, granular IAM role bindings, Harbor container registry setup, and multi-tier sample workloads (Web Server, Translation API, Elasticsearch). | [README](./gdc-sandbox-workshop/README.md) |
| **[GitOps Workshop](./gitops-workshop/)** | GDC Sandbox & GCP (GKE Autopilot) | End-to-end declarative GitOps platform featuring self-hosted GitLab Omnibus, ArgoCD (App-of-Apps pattern), OIDC/SSH zero-trust authentication, and multi-tenant self-service workload onboarding (with interactive Antigravity CLI guides). | [README](./gitops-workshop/README.md) |

*Note: This repository is expected to grow with additional parallel workshops, reference architectures, utilities, and sample code over time.*

## 🚀 Getting Started

Choose the workshop that matches your learning goal and navigate into its directory—each workshop manages its own prerequisites, `.env` configuration, and step-by-step guide:

- **Exploring GDC-AG core platform & workloads?** Start with the **[GDC Sandbox Workshop](./gdc-sandbox-workshop/README.md)** (`cd gdc-sandbox-workshop`).
- **Building a declarative GitOps control plane (ArgoCD + GitLab)?** Start with the **[GitOps Workshop](./gitops-workshop/README.md)** (`cd gitops-workshop`).

### General Prerequisites

Specific prerequisites are documented in each workshop's `README.md`, but generally include:
- Access to a target environment (such as a GDC-AG / GDC Sandbox environment, or a GCP project where supported).
- Basic familiarity with `kubectl`, `git`, and containerization.
- Python 3.x and a Bash environment.

## 🔒 Security Best Practices

When working with the GDC Sandbox or any GDC-AG environment, keep the following security practices in mind:

- **Secure Access:** Use Identity-Aware Proxy (IAP) tunnels for SSH and management access to your sandbox instances to avoid exposing services to the public internet.
- **Least Privilege:** Apply granular IAM role bindings (as demonstrated in the workshop) to ensure users and services have only the permissions they need.
- **Secret Management:** Never commit secrets, API keys, or service account keys to source control. Use environment variables (e.g., `.env` files) and Kubernetes Secrets.
- **Service Accounts:** Use dedicated Service Accounts and Robot Accounts for automated tasks like CI/CD and registry access.
- **Regular Rotation:** Periodically rotate your credentials, including Harbor robot secrets and GDC service account keys.

## 🤝 Contributing

We welcome contributions! Whether it's a bug fix, a new sample workload, or a reference guide, please see our [Contributing Guide](./docs/contributing.md) and [Code of Conduct](./docs/code-of-conduct.md).

## 📄 License

This project is licensed under the Apache 2.0 License. See the [LICENSE](./LICENSE) file for details.

---
*This is not an official Google product.*
