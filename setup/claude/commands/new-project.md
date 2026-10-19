---
description: Scaffold a new project from the template
argument-hint: <name> [description]
---

Input: $ARGUMENTS

1. Run `python3 framework/aaf.py new <name> --description "<description, if given>"`.
2. Ask the human, one question at a time, until you can fill in `README.md` (what it
   does) and:
   - `projects/<name>/CLAUDE.md`: purpose, how to run, conventions, what not to touch
   - `projects/<name>/DONE.md`: the project-specific criteria (metrics, thresholds,
     what plots must show)
3. Set up at least one real check in `projects/<name>/project.json` and run
   `python3 framework/aaf.py check <name>` to confirm it executes.
4. Record the main setup choices with `python3 framework/aaf.py decide`.
5. Ask the human whether to put the project on GitHub (recommended; private by default).
   If yes: `python3 framework/aaf.py git init <name>` (add `--public` only if they ask).
6. Set `status <name> --phase idle --note "Project set up"` and tell the human the
   project is ready for `/task`.
