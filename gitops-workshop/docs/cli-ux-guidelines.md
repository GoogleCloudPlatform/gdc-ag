# CLI UX & Formatting Guidelines

This document outlines the visual and behavioral design standards for Python CLI scripts in `gitops-workshop`.

## 1. Visual Design & Theme

CLI output uses the `rich` library to render clean, readable output for humans and AI agents.

### Color Palette & Badges
- **Header Panels**: `cyan` / `blue` panels for major script phases.
- **Success Badge**: `[bold green] [SUCCESS] [/bold green]` or `[green]✓[/green]`
- **Warning / Skip Badge**: `[bold yellow] [EXISTS/SKIP] [/bold yellow]` or `[yellow]! [/yellow]`
- **Error Badge**: `[bold red] [ERROR] [/bold red]` or `[red]✗[/red]`
- **Info Badge**: `[bold blue] [INFO] [/bold blue]` or `[blue]i[/blue]`

## 2. Prerequisites Verification
- **Silent by Default**: Prerequisite checks run silently when all dependencies pass to minimize terminal noise.
- **Diagnostic Output on Error**: If a required CLI tool or Python package is missing, an issue panel and targeted instructions are displayed.
- **Prerequisite Mode (`--check-prereqs`)**: Explicitly displays the full verification checklist when triggered with `--check-prereqs`.

## 3. Parameter Summary Tables (`print_parameter_summary()`)
- **Direct Table Title**: The table title is rendered directly on the table header using `box.ROUNDED`, avoiding redundant top-level box panels.
- **Concise Parameter Layout**: Only relevant configuration parameters are shown. Default flags (`Auto-Approve: Disabled`, `Dry-Run: Disabled`) are omitted; special modes like `[yellow]DRY-RUN[/yellow]` are highlighted only when active.
- **Clean File Sourcing**: Environment files are displayed with concise relative status (e.g., `.env (found)`).

## 4. Completion Banners & Next Instructions (`print_next_steps()`)
- **Success Notification Before Box**: A `[SUCCESS]` status message is printed immediately before the next steps panel.
- **Compact Next Steps Panel**: Displays a concise, single-spaced numbered list of immediate commands and actions without duplicate success headers or excessive vertical padding.

## 5. GCP Billing Account Selection
- **Interactive Selection**: If multiple open GCP billing accounts exist and no account is specified via CLI (`-b` / `--billing-account`) or `.env` (`GCP_BILLING_ACCOUNT`), `bootstrap.py` presents a numbered list of available billing accounts for interactive selection.
- **Single Account Auto-Select**: If only one open billing account is accessible, `bootstrap.py` automatically selects it and logs an informational message.

## 6. Environment File Sourcing (`-e` / `--env-file`)
- **Read-Only Environment Config**: Python automation scripts MUST treat `.env` files as strictly READ-ONLY. Scripts must never modify or overwrite `.env`.
- **CWD Default**: The `.env` path defaults to `.env` relative to the current working execution directory (`Path.cwd() / ".env"`).
- **Custom Location Flag**: Scripts take an optional `-e` / `--env-file` argument (e.g. `python3 scripts/bootstrap.py -e /path/to/custom.env`).

## 7. Interactive Elements & Confirmation Prompts
- **User Confirmation Prompt**: Scripts must prompt the user (`confirm_action()`) for confirmation before executing mutating actions.
- **Auto-Approve Flag (`-y` / `--auto-approve`)**: Bypasses interactive parameter and execution confirmation prompts (`confirm_action()`) for hands-off execution.
- **MR Auto-Merge Flag (`-m` / `--mr-approve`)**: Automatically approves and merges created GitLab Merge Requests via the GitLab REST API (`merge_gitlab_mr()`) without pausing for manual browser interaction.
- **Autonomous Mode (`-y -m`)**: Fully automated execution; combines `-y` (bypasses execution prompts) and `-m` (auto-merges Git MRs).
- **Guided Mode**: Staged commands in guided mode do NOT use `-y` or `-m`, allowing the user to review each step interactively.
- **Progress Spinners**: Use `rich.status.Status` or `Console.status(...)` for long-running operations (e.g., creating GKE cluster, waiting for pod readiness).
- **Dry-run Mode**: All scripts must support `--dry-run` to print proposed commands without executing mutating GCP/Kubernetes API calls.

