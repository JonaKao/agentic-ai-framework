# Agentic AI Framework

A workspace for handing whole tasks to a coding agent: you give one command, the agent
works in a loop until the project's definition of done holds, and you watch it on a
live dashboard.

## The loop

1. You run `/task <project> <what to do>` in Claude Code.
2. The agent reads the project's context files, makes the task checkable, then loops:
   implement, run checks, get an independent review from a fresh-context subagent.
3. It stops when every check passes and the review passes, or when it hits the
   iteration limit or repeats the same failure (Stuck), and reports with evidence.
4. If the reviewer listed minor findings, it tries to fix each one within
   `fix_iterations` (default 3). A fix that works is kept. A fix that doesn't is saved
   as a draft, the project is rolled back to its last passing state, and the dashboard
   asks you: `/draft <project> continue <id>` for another round, or `discard` to keep
   the issue on record only.

## Start

1. Run `bash setup/install.sh` once (or just double-click `Open Dashboard.command`,
   which does it for you). It installs the agent commands into `.claude/`.
2. Install Claude Code (see https://docs.claude.com/en/docs/claude-code), then open a
   terminal in this folder and run `claude`.
3. Start the dashboard: double-click `Open Dashboard.command`, or run
   `python3 dashboard/server.py` and open http://localhost:8765.
4. In Claude Code:
   - `/spec my-model <idea>` first for anything large, or
   - `/new-project my-model` for a new project, or
   - `/onboard practical ~/path/to/existing/code` to take over existing code
   - then `/task my-model add a validation split and report validation loss`

## Extras the agents use

- **Python language server**: `brew install pyright` once. The `pyright-lsp` plugin
  (enabled in `.claude/settings.json`) then reports type errors right after each edit.
- **Context7** (`.mcp.json`): current library documentation for the agents.
- **Sandbox**: shell commands run inside Claude Code's sandbox, with network access
  limited to GitHub, PyPI, Hugging Face, PyTorch and the Playwright downloads. The
  framework tool and its checks run outside it.
- **Hooks**: `framework/hooks/activity.py` feeds the dashboard and records token usage;
  `framework/hooks/gate.py` keeps a `/task` running until it ends on the record.

## Git and GitHub

Each project can be its own private GitHub repository:

```
python3 framework/aaf.py git init <project>      # create the repo and push the first commit
python3 framework/aaf.py git init-framework      # the framework itself, as its own repo
```

From then on `/task` pulls before it starts and, once the work is done and reviewed,
commits with a message built from the task, decisions, checks and review, then pushes.
Rolled-back fixes and failing work are never committed. Needs `gh` (`brew install gh`,
then `gh auth login`).

`projects/example` is a demo with a generated history; delete it whenever you like.

## Files

| Path | Purpose |
|---|---|
| `CLAUDE.md` | Rules every agent session follows in this workspace |
| `.claude/commands/` | `/task`, `/fix`, `/draft`, `/new-project`, `/onboard` (installed from `setup/claude/`; edit them there) |
| `.claude/agents/reviewer.md` | The independent reviewer subagent (installed from `setup/claude/`) |
| `framework/aaf.py` | CLI the agent uses to record status, checks, decisions, reviews |
| `projects/control-room/` | The dashboard, kept as a project so agents can improve it (`dashboard/server.py` starts it) |
| `framework/hooks/activity.py` | Logs each agent step in plain words for the dashboard's live activity feed |
| `template/` | Files every new project starts with |
| `projects/<name>/` | Your projects: `CLAUDE.md`, `DONE.md`, `project.json`, `state/`, `plots/` |

## Requirements

`python3` (macOS asks to install the Command Line Tools the first time you run it).
Nothing else.
