---
name: gitops-interaction-guide
description: >-
  Standard interaction, terminal session, and execution mode management for all GitOps workshop skills.
  Enforces explain-before-execute transparency, handles tmux environment detection, pane creation/selection, autonomous vs guided mode selection, and command dispatch standards.
---

# Workshop Interaction & Terminal Session Guide

This skill defines the **transparent, beginner-friendly interaction standard** across all GitOps workshop skills.

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

Whenever a workshop skill begins, the agent **MUST output the following formatted orientation** in its message:

```markdown
👋 **Welcome to the [Workshop Skill Name]!**

Before we run any provisioning, let's configure our environment:
1. **Terminal Setup**: I will check if you are running in a `tmux` session so you can see live command execution, spinners, and logs side-by-side in an adjacent pane.
2. **Execution Mode**: You can choose whether you want me to execute commands automatically or stage them for you to review and press Enter.
3. **Service Checks**: We'll verify that your cluster dashboards (ArgoCD & GitLab) are accessible.

I will now check if you're inside a `tmux` session...
```

---

## 2. Working Directory & Terminal Session Setup

### Step 2.0: Resolve Workshop Working Directory (`WORKSHOP_DIR`)
Because `gitops-workshop` lives inside a multi-workshop repository, the user may launch `agy` either from inside `gitops-workshop/` or from the repository root (`gdc-ag/`):
1. Determine `WORKSHOP_DIR`:
   - If `./scripts/bootstrap` exists in the current directory, `WORKSHOP_DIR="$(pwd)"`.
   - Otherwise, if `./gitops-workshop/scripts/bootstrap` exists, `WORKSHOP_DIR="$(pwd)/gitops-workshop"`.
2. **All `.env` reads/writes, example templates (`.env.gcp.example`, `.env.gdc.example`), and script executions MUST resolve relative to `$WORKSHOP_DIR`** (never the multi-workshop repository root).
3. When creating tmux panes/windows (`split-window`, `new-window`), pass `-c "$WORKSHOP_DIR"`. If reusing an existing execution pane whose `#{pane_current_path}` is not `$WORKSHOP_DIR`, dispatch `cd "$WORKSHOP_DIR"` to that pane first.

### Step 2.1: Detect Tmux Environment
Inform the user before checking:
> *"Checking if we are running inside an active `tmux` terminal session..."*

To accurately determine if the **current execution environment/terminal** is running inside tmux (and not merely that a tmux server daemon exists elsewhere on the machine), check the `$TMUX` environment variable (or detect via `tmux display-message`):

```bash
# Check if the current terminal is inside an active tmux session
if [ -n "$TMUX" ]; then
  tmux display-message -p '#{session_name}'
else
  tmux display-message -p '#{session_name}' 2>/dev/null || echo "NOT_IN_TMUX"
fi
```

> [!NOTE]
> Checking `tmux display-message` alone can report a session name if an unrelated background tmux daemon is running, even if the user's active shell or agent process is outside tmux. Checking `[ -n "$TMUX" ]` guarantees the current terminal is an attached tmux pane.

#### Scenario A: Inside Tmux
When tmux is detected, **ALWAYS output a friendly, transparent message to the user BEFORE performing any session renaming or pane creation**:

> 💬 **Example Narration**:
> *"I detected we're in a tmux session. Great! This workshop is best executed this way.*
> *I see there's only a single pane, so I'm going to split this window so you can watch commands run live side-by-side with progress spinners and logs.*
> *I'm also going to rename the session to `gitops-workshop` so you can easily identify and reconnect to it."*

Follow these steps with clear, prior communication:

1. **Inform & Rename Session**:
   - Inform the user: *"Renaming the tmux session to `gitops-workshop` so you can easily manage and identify it..."*
   - Run:
     ```bash
     tmux rename-session "gitops-workshop"
     ```
2. **Inspect Panes**:
   - Inspect available panes in the current window:
     ```bash
     tmux list-panes -F "#{pane_index} #{pane_id} #{pane_active} #{pane_width}x#{pane_height}"
     ```
3. **Determine Target Execution Pane (`<target-pane>`)**:
   - **Case 1 (Only 1 pane exists — the current agent pane)**:
     - **Explain BEFORE splitting**: Inform the user: *"I see there's only a single pane, so I'm going to split this window horizontally (`tmux split-window -h -c \"$WORKSHOP_DIR\"`) to create a dedicated command execution pane on the right side. This will allow you to see live script execution, parameter tables, and status output side-by-side."*
     - Run: `tmux split-window -h -c "$WORKSHOP_DIR"`
     - Record the new pane ID (e.g. `%1` or pane index `1`).
   - **Case 2 (Exactly 2 panes exist)**:
     - Inform the user: *"I detected an adjacent pane (ID: `<pane_id>`). I will use this pane for live command execution."*
     - Automatically select the other pane (the non-active pane) as the target execution pane, and ensure its working directory is `$WORKSHOP_DIR` (if not, run `tmux send-keys -t <target-pane> "cd \"$WORKSHOP_DIR\"" C-m`).
   - **Case 3 (More than 2 panes exist)**:
     - Inform the user of the available panes and prompt them using `ask_question` to choose their preferred execution pane (then ensure it is in `$WORKSHOP_DIR`).

#### Scenario B: NOT in Tmux
If not running in tmux, explain why tmux is beneficial and offer the choice:
> 💡 **Tmux Recommended**: *This workshop is designed to run inside a `tmux` session so you can see live script execution, progress bars, and parameter tables side-by-side in an adjacent pane.*
>
> *To launch a tmux session:*
> ```bash
> tmux
> ```

Use `ask_question` to ask:
- **Option 1**: *I will exit, start tmux, and re-run the skill.*
- **Option 2**: *(Continue anyway) Proceed without tmux in standard terminal mode.*

---

## 3. Execution Mode Selection (`ask_question`)

Once the terminal environment is established, present the execution mode options:

1. **Autonomous Mode (Agent executes in pane)**:
   - The agent appends `-y` (auto-approve prompts) and `-m` (auto-merge GitLab MRs) to automation scripts and dispatches commands directly to `<target-pane>` with `Enter` (`C-m`).
   - The participant watches live execution, progress spinners, parameter tables, and automated MR reconciliations in the adjacent pane.
   - The agent pauses at visual milestones to guide the participant through web UI actions (ArgoCD, GitLab).

2. **Guided Mode (User reviews and presses Enter)**:
   - The agent stages each command into `<target-pane>` *without* `Enter`.
   - **MANDATORY RULE FOR GUIDED MODE**: **NEVER include `-y`, `--auto-approve`, `-m`, or `--mr-approve` in staged commands**.
     - This ensures the participant sees the parameter summary table, gets prompted for confirmation (`Do you want to proceed? [y/N]`), and manually reviews/merges MRs in GitLab.
   - The participant reviews the staged command, presses **Enter** to run, reviews parameters in the terminal, types `y` to confirm, and reviews diffs in the GitLab UI.
   - Ideal for participants who want hands-on control over every terminal command and confirmation step.

---

## 4. Standardized Command Dispatching

- **Autonomous Mode Dispatch (`-y -m`)**:
  - Automatically appends `-y -m` so the script runs without blocking for interactive user input or manual MR merges.
  - Inform user: *"Executing `<command-summary>` in the execution pane..."*
  ```bash
  tmux send-keys -t <target-pane> "<command> -y -m" C-m
  ```
  The agent waits for the command to finish, then captures and verifies the output via:
  ```bash
  tmux capture-pane -t <target-pane> -p -S -50
  ```

- **Guided Mode Dispatch (No `-y`, No `-m`)**:
  - **Do NOT include `-y` or `-m`**. The user will interact with the confirmation prompt in the terminal and merge MRs in GitLab.
  - Inform user: *"Staged `<command-summary>` in your execution pane. Review the command, press Enter to run, and confirm when prompted!"*
  ```bash
  # Note: No -y or -m flags staged
  tmux send-keys -t <target-pane> -l "<command>"
  ```
  - **Prompt user for status via `ask_question`**:
    After staging the command, the agent MUST prompt the user with:
    - **Option 1**: *(Recommended) Done - The script finished successfully.*
    - **Option 2**: *There are issues. Help me troubleshoot.*
  - **Handling User Response**:
    - **If "Done"**: The agent captures pane output (`tmux capture-pane -t <target-pane> -p -S -50`) to verify the completion state, explains the milestone, and proceeds to the next step.
    - **If "There are issues. Help me"**: The agent captures pane logs (`tmux capture-pane -t <target-pane> -p -S -100`), diagnoses the error or warning in the terminal output, and provides step-by-step troubleshooting assistance.

---

## 5. Dedicated Port-Forwarding Window & Labeled Panes (`port-forwards`)

To ensure background port-forwarding processes (`kubectl port-forward`) remain organized, persistent, and observable without blocking the agent or execution panes, the agent **MUST manage all port-forwards in a single dedicated tmux window named `port-forwards`**.

### 5.1 Window & Pane Naming Standard
- **Dedicated Window Name**: `port-forwards`
- **Pane Title Format**: `<app>-<purpose>`
  - `purpose` values:
    - **`web`**: Web UI dashboards or HTTP REST APIs.
    - **`ssh`**: Git SSH transport.

| Service | Local Port | Target Service | Pane Title (`<app>-<purpose>`) | Command Line |
| :--- | :--- | :--- | :--- | :--- |
| **ArgoCD Web UI** | `8080` | `svc/argocd-server 8080:80` | `argocd-web` | `kubectl port-forward -n argocd svc/argocd-server 8080:80` |
| **GitLab Web UI** | `8081` | `svc/gitlab-omnibus 8081:80` | `gitlab-web` | `kubectl port-forward -n gitlab svc/gitlab-omnibus 8081:80` |
| **GitLab Git SSH** | `2222` | `svc/gitlab-omnibus 2222:22` | `gitlab-ssh` | `kubectl port-forward -n gitlab svc/gitlab-omnibus 2222:22` |
| **Workload App** | `8082` | `svc/<app-name> 8082:80` | `<app-name>-web` | `kubectl port-forward -n <app-name> svc/<app-name> 8082:80` |

### 5.2 Tmux Window & Pane Lifecycle Management
1. **Ensure `port-forwards` Window Exists**:
   ```bash
   if ! tmux list-windows -F "#{window_name}" 2>/dev/null | grep -q "^port-forwards$"; then
     tmux new-window -n "port-forwards" -d -c "$WORKSHOP_DIR"
   fi
   ```

2. **Launch or Attach Labeled Pane**:
   For each required port-forward, create a dedicated pane within the `port-forwards` window, set the pane title `<app>-<purpose>`, and run the command:
   ```bash
   # Create pane and capture its pane ID
   PANE_ID=$(tmux split-window -t "port-forwards" -c "$WORKSHOP_DIR" -P -F "#{pane_id}")
   tmux select-pane -t "$PANE_ID" -T "<app>-<purpose>"
   tmux send-keys -t "$PANE_ID" "kubectl port-forward -n <namespace> <service> <local-port>:<remote-port>" C-m
   tmux select-layout -t "port-forwards" tiled
   ```

3. **Recreation After Pod Restarts**:
   When pod restarts occur (e.g. Phase 6 SSH auth reconciliation), kill old processes and restart the port-forwards within the `port-forwards` window panes:
   ```bash
   pkill -f "kubectl port-forward -n argocd" || true
   pkill -f "kubectl port-forward -n gitlab" || true
   ```

4. **Non-Tmux Fallback**:
   If the user opted out of tmux, launch the background port-forward commands using standard shell backgrounding (`kubectl port-forward ... >/dev/null 2>&1 &`).



