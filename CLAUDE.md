# Agentic AI Framework

A workspace for running coding agents on projects with little supervision. Every project
lives in `projects/<name>/` with its own `CLAUDE.md`, `DONE.md` and `state/`. Read the
project's files before working on it. Command and file details: `framework/REFERENCE.md`.

## Rules

1. **State lives in files.** Start by reading the project's `CLAUDE.md`, `DONE.md`,
   `state/progress.md` and `state/decisions.md`; end by updating `state/progress.md`.
2. **Record state only through `python3 framework/aaf.py`** (status, check, decide,
   review, plan, feature, git). Never edit `state/*.json` or `features.json` by hand.
3. **Correct means the checks pass.** If a task's success is not covered by a check,
   add one first and confirm it fails.
4. **Never weaken a check** (delete, skip, loosen, special-case) unless the task says so.
   If a check is wrong, record a decision and say so.
5. **Look at your plots** and screenshots with the Read tool before claiming success.
6. **Stay inside the project folder** unless the task says otherwise.
7. **Never leave a project broken.** Snapshot before risky changes; a fix that fails
   becomes a draft and the snapshot is restored.
8. **Git only through `aaf.py git`.** No direct `git commit` or `git push`, no force-push.
9. **Keep the README current** when a task changes what the project does, how to run
   it or how it is built.
10. **Ask through the record.** While a task is active, a Stop hook keeps you working.
    To ask the human something, set `--phase waiting --note "Question: ..."` first.
11. **Stop honestly.** Same failure three times, or the iteration limit: set `stuck`
    and report what you tried and what you need.

## Commands

- `/spec <name> <idea>`: interview the human and write a spec with features (large work)
- `/task <name> <what to do>` or `/task <name> next`: run until the definition of done holds
- `/fix <name> [issues]` and `/draft <name> continue|discard <id>`: follow-up fixes
- `/new-project <name>` and `/onboard <name> <path>`: start or take over a project
