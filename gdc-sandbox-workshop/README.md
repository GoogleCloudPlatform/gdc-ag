# GDC Sandbox Workshop

## About this repo

This repository provides a complete workshop environment for learning Google Distributed Cloud (GDC) Sandbox through hands-on labs. It includes setup automation, helper utilities, sample workloads, and guided exercises.

> [!WARNING]
> **Non-Production Environment:** This workshop and the associated GDC Sandbox environment are intended for **educational and testing purposes only**. They are NOT designed for production workloads.
>
> **Data Sensitivity:** Do NOT upload, process, or store any real sensitive, proprietary, or regulated data within this environment. Always use synthetic or publicly available data for your labs.

### Setup Scripts

Numbered scripts (`000-`, `001-`, `002-`, etc.) automate the initial GDC environment configuration:

- **`000-install-gdcloud.sh`** - Installs the `gdcloud` CLI tool and configures authentication certificates
- **`001-create-projects.py`** - Creates GDC projects based on `projects_config.yaml`
- **`002-apply-role-bindings.py`** - Applies IAM role bindings to projects and organizations
- **`003-createharborproject.sh`** - Sets up Harbor container registry projects
- **`004-addharborsecret.sh`** - Configures Harbor registry secrets for Kubernetes

### Helper Scripts

Convenience scripts to streamline common operations:

- **`sandbox.sh`** - Manages sandbox VM connections (SSH tunnels, file transfers, sshuttle VPN)
- **`login.sh`** - Authenticates to GDC clusters and Harbor registry
- **`build.sh`** - Builds Docker images and pushes them to Harbor
- **`pull.sh`** - Pulls public images and pushes them to your Harbor registry
- **`functions.sh`** - Bash functions for kubectl shortcuts (`ku`, `ko`, `kp`) and deployment helpers

### Lab Guide

The lab guide is available [here](./LabGuide.pdf).


## Set up Local Laptop

1. Clone the repo locally. 

2. Edit the `.env` file. 
```bash

cd ~/gdc-sandbox-workshop
cp .env.example .env

# edit .env for specifics
vi .env

source .env
```

3. Create tunnel to sandbox bootstrapper. 
```bash
./sandbox.sh tunnel
```

## Set up sandbox bootstrapper

1. Connect to the sandbox bootstrapper. 

2. Clone the repository on the sandbox bootstrapper and navigate to the workshop directory. 

```bash
git clone https://github.com/GoogleCloudPlatform/gdc-ag.git
cd gdc-ag/gdc-sandbox-workshop
```

3. On your local laptop, copy the `.env` file to the sandbox. 

```bash
./sandbox.sh env
```

4. On the sandbox bootstrapper, load environment variables. 
```bash
source .env
```

5. In the browser, login to sandbox console and download `gdcloud_cli.tar.gz` from the console.

6. Run `./000-install-gdcloud.sh` to install the `gdcloud` CLI tool and configure authentication certificates. 

7. Login to `gdcloud` cli. 

```bash
login
```

8. Edit `projects_config.yaml` to add your projects and user permissions. 

9. Run `./001-create-projects.py` to create the projects. 

10. Run `./002-apply-role-bindings.py` to apply IAM role bindings to projects and organizations. 

11. In console, attach project to `user-vm-1` cluster. 

12. Run `./003-createharborproject.sh` to create Harbor project.

13. In console, in Harbor project, create robot account and add to `.env`.  Re-run `source .env` and `login`. See [Lab guide](./LabGuide.pdf) for more details, screenshots and walk through. 

14. Run `./004-addharborsecret.sh` to add Harbor secret to `user-vm-1` cluster. 

15. You are now ready to start the labs.



## Labs

These hands-on labs will guide you through deploying and managing workloads on GDC. You'll start with a simple HTML web server to learn the basics of building, deploying, and updating containerized applications. Then you'll progress to more complex services including a translation API with external dependencies and an Elasticsearch stack with Kibana for data analytics.

* [Lab 1 - Deploy HTML Server](./LAB-1.md)
* [Lab 2 - Deploy API Server](./LAB-2.md)
* [Lab 3 - Deploy Elasticsearch](./LAB-3.md)