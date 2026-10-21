# Framework reference

Details behind the rules in the workspace `CLAUDE.md`. Read the part you need.

## Workspace layout

| Path | What it is |
|---|---|
| `projects/<name>/CLAUDE.md` | How to work on that project: run, test, conventions, no-go zones |
| `projects/<name>/DONE.md` | Definition of done; a task is finished only when every item holds |
| `projects/<name>/project.json` | Checks (commands that must exit 0), `max_iterations`, `fix_iterations` |
| `projects/<name>/README.md` | What the project is, kept current; two sections are generated |
| `projects/<name>/features.json` | Optional end-to-end feature list with pass flags (multi-session projects) |
| `projects/<name>/specs/` | Specs written with `/spec` |
| `projects/<name>/state/` | Progress note, decisions, status, checks, reviews, plan, activity |
| `projects/<name>/plots/` | Plots; shown on the dashboard |
| `framework/aaf.py` | The CLI below |
| `framework/hooks/` | `activity.py` (live feed, token usage) and `gate.py` (keeps `/task` running) |
| `projects/control-room/` | The dashboard; `python3 dashboard/server.py`, then http://localhost:8765 |
| `template/` | Files copied into every new project |
| `setup/claude/` | Source of `.claude/` (commands, agents, settings); edit here, not in `.claude/` |

## aaf.py

```
status <p> --phase PHASE [--task T] [--iteration N] [--note T]
    phases: planning implementing checking reviewing fixing  (active: the Stop hook keeps the task running)
            waiting (needs the human: a draft decision or a question)  done  stuck  idle
check <p>                                   run all checks, record results
decide <p> TITLE RATIONALE                  append to the decision log
review <p> --verdict pass|fail --summary T [--file REPORT]
plan <p> --step T [--step T ...] | --add T  record plan steps;  step <p> N  ticks one off
snapshot <p> LABEL / restore <p> LABEL      save and restore working files
draft save|apply|discard|list <p> [ID] ...  unfinished fix attempts
feature add <p> --title T [--criteria T] [--spec PATH] / list / next / pass ID --evidence T / fail ID
git init <p> | init-framework | commit <p> [--title T] | commit-framework [--title T]
git push|pull|info|files <p>
stats <p> / estimate <p> / readme <p> / new <p> [--from PATH] / list
```

## Review severities

blocker and major fail the review; minor findings (real but small defects) are fixed
automatically by the fix phase; notes (style, ideas) are recorded and never auto-fixed.

## Generated README sections

Between `<!-- aaf:history:start -->`/`end` and `<!-- aaf:checks:start -->`/`end`.
Refreshed on every `aaf.py git commit`. Never edit them by hand.
