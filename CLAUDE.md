# Agentic AI Framework — workspace instructions

This folder is a workspace for running coding agents on projects with as little
supervision as possible. Every project lives in `projects/<name>/` and carries its
own context files. Read this file first, then the project's files.

## Layout

| Path | What it is |
|---|---|
| `projects/<name>/CLAUDE.md` | How to work on that project: run, test, conventions, no-go zones |
| `projects/<name>/DONE.md` | The definition of done. A task is finished only when every item holds |
| `projects/<name>/project.json` | The project's checks (commands that must exit 0), `max_iterations` per task and `fix_iterations` per follow-up fix |
| `projects/<name>/state/` | Progress note, decisions log, status, check results, reviews. The dashboard reads this |
| `projects/<name>/plots/` | Plots produced by the project. Shown on the dashboard |
| `framework/aaf.py` | The one CLI for recording state: `new`, `check`, `status`, `decide`, `review`, `snapshot`, `restore`, `draft`, `git` |
| `projects/control-room/` | The dashboard itself, as a project agents can improve. Start it with `python3 dashboard/server.py` (a shim), then open http://localhost:8765 |
| `template/` | Files copied into every new project |

## Rules that apply to every project

1. **State lives in files, not in the conversation.** At the start of work, read the
   project's `CLAUDE.md`, `DONE.md`, `state/progress.md` and `state/decisions.md`.
   At the end, update `state/progress.md`.
2. **Report state through `framework/aaf.py`**, never by editing `state/*.json` by hand.
   The dashboard depends on it:
   - `python3 framework/aaf.py status <project> --phase <phase> [--task "..."] [--iteration N] [--note "..."]`
     with phase one of `planning`, `implementing`, `checking`, `reviewing`, `fixing`, `waiting`
     (a draft needs the human), `done`, `stuck`, `idle`
   - `python3 framework/aaf.py check <project>` runs all checks and records the results
   - `python3 framework/aaf.py decide <project> "Title" "Why, and what was rejected"`
   - `python3 framework/aaf.py review <project> --verdict pass|fail --summary "..." [--file report.md]`
3. **"Correct" means the checks pass.** If a task's success is not covered by a check,
   add one first and make sure it fails before you start implementing.
4. **Never weaken a check to make it pass.** Do not delete, skip, loosen or special-case
   tests or thresholds unless the task explicitly asks for it. If a check is wrong,
   record a decision explaining why and say so in your final report.
5. **Look at your plots.** When a task produces plots, write them to the project's
   `plots/` folder, open them with the Read tool, and note anything irregular.
   When the same irregularity keeps appearing, turn it into a numeric check.
6. **Stay inside the project folder** unless the task says otherwise.
7. **Never leave a project broken.** Before any risky change, take a snapshot
   (`aaf.py snapshot`). A fix that does not work out is saved as a draft and the
   snapshot is restored (`aaf.py draft save`, then `aaf.py restore`), so the project
   always ends in a state where every check passes.
8. **Git goes through the framework.** Each project is its own repository (usually a
   private GitHub repo). Use `aaf.py git pull|commit|push|info`, never `git commit` or
   `git push` directly, and never force-push or rewrite history. `aaf.py git commit`
   refuses while checks fail, writes the message from the recorded task, decisions,
   checks and review, and pushes. Live dashboard files and drafts stay local.
9. **Stop honestly.** If the same failure repeats three times, or the iteration limit
   in `project.json` is reached, set phase `stuck` and report what you tried, the
   evidence, and what you need from the human.

## Commands

- `/new-project <name> [description]`: scaffold a fresh project
- `/onboard <name> <path-to-existing-code>`: take over an existing codebase
- `/task <name> <what to do>`: run a task until the definition of done holds, then
  attempt the reviewer's minor findings safely
- `/fix <name> [issues]`: attempt specific issues, rolling back to a draft on failure
- `/draft <name> continue|discard <id>`: decide what happens to a saved fix attempt
