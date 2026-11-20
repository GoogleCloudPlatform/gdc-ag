---
name: app-interaction-guide
description: >-
  Standard interaction, terminal session, and execution mode management for all Application Workshop skills.
  Enforces explain-before-execute transparency, handles tmux environment detection, pane creation/selection, autonomous vs guided mode selection, and command dispatch standards.
---

# Application Workshop Interaction & Terminal Session Guide

This skill defines the **transparent, beginner-friendly interaction standard** across all Application Workshop skills (`/app-workshop-guide` and `/app-deploy`).

---

## 🌟 Core Interaction Rule: "Explain First, Execute Second"

> [!CAUTION]
> ### 🛑 The Cardinal Rule: Never Execute Tools Silently
> When this skill starts, the AI agent **MUST generate a visible, comprehensive explanation in the chat BEFORE triggering any tool calls**.
>
> If you call `run_command` (e.g. `tmux display-message` or `kubectl`), you **MUST write the explanatory text in your response message**. Never make a bare tool call without accompanying user-facing text.
>
> The user must always see:
> 1. **Welcome & Context**: What skill is running and what goals we are going to achieve.
> 2. **Roadmap**: The steps we will follow.
> 3. **Immediate Action**: Why a specific command (e.g. tmux detection, port-forward check) is being executed.

---

## 1. Welcome & Initial Orientation Template

Whenever an Application Workshop skill begins, the agent **MUST output the following formatted orientation** in its message:

```markdown
👋 **Welcome to the [Application Workshop Skill Name]!**

Before we build and ship the workload, let's configure our environment:
1. **Terminal Setup**: I will check if you are running in a `tmux` session so you can see live Docker builds, parameter tables, and GitOps pushes side-by-side in an adjacent pane.
2. **Execution Mode**: You can choose whether you want me to execute commands automatically or stage them for you to review and press Enter.
3. **Service Checks**: We'll verify that your GitOps platform dashboards (ArgoCD & GitLab) are running and reachable.

I will now check if you're inside a `tmux` session...
```

---

## 2. Working Directory & Terminal Session Setup

### Step 2.0: Resolve Workshop Working Directory (`WORKSHOP_DIR`)
Because `application-workshop` lives inside the `gdc-ag` multi-workshop repository, the user may launch `agy` either from inside `application-workshop/` or from the repository root (`gdc-ag/`):
1. Determine `WORKSHOP_DIR`:
   - If `./scripts/build_and_push.py` exists in the current directory, `WORKSHOP_DIR="$(pwd)"`.
   - Otherwise, if `./application-workshop/scripts/build_and_push.py` exists, `WORKSHOP_DIR="$(pwd)/application-workshop"`.
2. **All `.env` reads/writes, example templates (`.env.gdc.example`, `.env.gcp.example`), and script executions MUST resolve relative to `$WORKSHOP_DIR`** (never the multi-workshop repository root).
3. When creating tmux panes/windows (`split-window`, `new-window`), pass `-c "$WORKSHOP_DIR"`. If reusing an existing execution pane whose `#{pane_current_path}` is not `$WORKSHOP_DIR`, dispatch `cd "$WORKSHOP_DIR"` to that pane first.

### Step 2.1: Detect Tmux Environment
Inform the user before checking:
> *"Checking if we are running inside an active `tmux` terminal session..."*

```bash
if [ -n "$TMUX" ]; then
  tmux display-message -p '#{session_name}'
else
  tmux display-message -p '#{session_name}' 2>/dev/null || echo "NOT_IN_TMUX"
fi
```

#### Scenario A: Inside Tmux
1. **Inform & Rename Session (if default)**:
   - Inform the user: *"Ensuring our tmux session and execution pane are ready..."*
2. **Inspect Panes**:
   ```bash
   tmux list-panes -F "#{pane_index} #{pane_id} #{pane_active} #{pane_width}x#{pane_height}"
   ```
3. **Determine Target Execution Pane (`<target-pane>`)**:
   - **Case 1 (Only 1 pane exists)**:
     - Inform the user before splitting, then run:
       ```bash
       tmux split-window -h -c "$WORKSHOP_DIR"
       ```
   - **Case 2 (Exactly 2 panes exist)**:
     - Select the non-active pane as `<target-pane>` and ensure its working directory is `$WORKSHOP_DIR`.
   - **Case 3 (More than 2 panes exist)**:
     - Ask the user via `ask_question` which pane to use for live command execution.

#### Scenario B: NOT in Tmux
If not running in tmux, recommend `tmux` or allow the user to continue in standard terminal mode via `ask_question`.

---

## 3. Execution Mode Selection (`ask_question`)

Present the execution mode options:

1. **Autonomous Mode (Agent executes in pane)**:
   - The agent appends `-y` (auto-approve prompts) and `-m` (auto-merge GitLab MRs) to automation scripts and dispatches commands directly to `<target-pane>` with `Enter` (`C-m`).
2. **Guided Mode (User reviews and presses Enter)**:
   - The agent stages each command into `<target-pane>` *without* `Enter`.
   - **MANDATORY RULE FOR GUIDED MODE**: **NEVER include `-y`, `--auto-approve`, `-m`, or `--mr-approve` in staged commands**.

---

## 4. Standardized Command Dispatching

- **Autonomous Mode Dispatch (`-y -m`)**:
  ```bash
  tmux send-keys -t <target-pane> "<command> -y -m" C-m
  ```
- **Guided Mode Dispatch (No `-y`, No `-m`)**:
  ```bash
  tmux send-keys -t <target-pane> -l "<command>"
  ```
  Then prompt the user via `ask_question`:
  - **Option 1**: *(Recommended) Done - The script finished successfully.*
  - **Option 2**: *There are issues. Help me troubleshoot.*

---

## 5. Dedicated Port-Forwarding Window (`port-forwards`)

Manage background port-forwards in the dedicated tmux window named `port-forwards`:

| Service | Local Port | Target Service | Pane Title (`<app>-<purpose>`) | Command Line |
| :--- | :--- | :--- | :--- | :--- |
| **ArgoCD Web UI** | `8080` / `8088` | `svc/argocd-server 8080:80` | `argocd-web` | `kubectl port-forward -n argocd svc/argocd-server 8080:80` |
| **GitLab Web UI** | `8081` | `svc/gitlab-omnibus 8081:80` | `gitlab-web` | `kubectl port-forward -n gitlab svc/gitlab-omnibus 8081:80` |
| **GitLab Git SSH** | `2222` | `svc/gitlab-omnibus 2222:22` | `gitlab-ssh` | `kubectl port-forward -n gitlab svc/gitlab-omnibus 2222:22` |
| **Translation App** | `8082` | `svc/translate-api 8082:80` | `translate-api-web` | `kubectl port-forward -n translate-api svc/translate-api 8082:80` |
| **Upload Vault App** | `8083` | `svc/upload-api 8083:80` | `upload-api-web` | `kubectl port-forward -n upload-api svc/upload-api 8083:80` |
