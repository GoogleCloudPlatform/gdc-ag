# CLI UX & Formatting Guidelines (`application-workshop`)

This document outlines the visual and behavioral design standards for Python CLI scripts in `application-workshop`, matching the conventions of `gitops-workshop`.

## 1. Visual Design & Theme

CLI output uses the `rich` library to render clean, readable output for humans and AI agents.

### Color Palette & Badges
- **Header Panels**: `cyan` / `blue` panels for major script phases.
- **Success Badge**: `[bold green] [SUCCESS] [/bold green]` or `[green]✓[/green]`
- **Warning / Skip Badge**: `[bold yellow] [EXISTS/SKIP] [/bold yellow]` or `[yellow]! [/yellow]`
- **Error Badge**: `[bold red] [ERROR] [/bold red]` or `[red]✗[/red]`
- **Info Badge**: `[bold blue] [INFO] [/bold blue]` or `[blue]i[/blue]`

## 2. Prerequisites Verification
- **Silent by Default**: Prerequisite checks (`check_prerequisites()`) run silently when all dependencies (`docker`, `kubectl`, `git`, and `gcloud` in GCP mode) pass.
- **Diagnostic Output on Error**: If a required CLI tool or Python package is missing, an issue panel and targeted instructions are displayed.
- **Prerequisite Mode (`--check-prereqs`)**: Explicitly displays the full verification checklist when triggered with `--check-prereqs` and exits with code 0.

## 3. Parameter Summary Tables (`print_parameter_summary()`)
- **Direct Table Title**: The table title is rendered directly on the table header using `box.ROUNDED`.
- **Concise Parameter Layout**: Shows platform mode (`GDC` or `GCP`), image URI, target namespace, GitLab repository coordinates, and active status flags (`DRY-RUN`, `Auto-Approve`, `Auto-Merge`).
- **Clean File Sourcing**: Environment files are displayed with concise relative status (e.g., `.env (found)`).

## 4. Completion Banners & Next Instructions (`print_next_steps()`)
- **Success Notification Before Box**: A `[SUCCESS]` status message is printed immediately before the next steps panel.
- **Compact Next Steps Panel**: Displays a concise numbered list of immediate commands and verification steps.

## 5. Environment File Sourcing (`-e` / `--env-file`)
- **Read-Only Environment Config**: Python automation scripts MUST treat `.env` files as strictly READ-ONLY. Scripts must never modify or overwrite `.env`.
- **CWD Default**: The `.env` path defaults to `.env` in `application-workshop/`.
- **Custom Location Flag**: Scripts take an optional `-e` / `--env-file` argument (e.g. `python3 scripts/build_and_push.py -e /path/to/custom.env`).

## 6. Interactive Elements & Confirmation Prompts
- **User Confirmation Prompt**: Scripts prompt the user (`confirm_action()`) for confirmation before executing mutating actions.
- **Auto-Approve Flag (`-y` / `--auto-approve`)**: Bypasses interactive confirmation prompts (`confirm_action()`) for hands-off execution.
- **MR Auto-Merge Flag (`-m` / `--mr-approve`)**: Automatically approves and merges created GitLab Merge Requests via the GitLab REST API (`merge_gitlab_mr()`) without pausing for manual browser interaction.
- **Autonomous Mode (`-y -m`)**: Combines `-y` and `-m` for non-interactive execution.
- **Guided Mode**: Staged commands in guided mode do NOT use `-y` or `-m`, allowing the participant to review each step interactively.
- **Dry-run Mode (`--dry-run`)**: Prints proposed Docker, Kubernetes, and GitLab actions without executing mutating calls.
