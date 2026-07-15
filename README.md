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

## 📂 Repository Contents

Currently, the repository features:

- **[GDC Sandbox Workshop](./gdc-sandbox-workshop/):** A full-featured workshop environment. It includes:
  - Automation scripts for project creation and IAM configuration.
  - Setup for container registries (Harbor).
  - Sample workloads including a Web Server, Translation API, and Elasticsearch stack.
  - Detailed lab guides and exercises.

*Note: This repository is expected to grow with more reference architectures, utilities, and sample code over time.*

## 🚀 Getting Started

To dive into GDC-AG, we recommend starting with the **[Sandbox Workshop](./gdc-sandbox-workshop/README.md)**. This workshop provides a guided experience in a sandbox environment, covering everything from initial setup to deploying complex multi-tier applications.

### Prerequisites

Specific prerequisites depend on the individual tool or workshop, but generally include:
- Access to a GDC-AG environment (or Sandbox).
- Basic familiarity with `kubectl` and containerization.
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
