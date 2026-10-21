---
description: Take over an existing codebase and make it ready for /task
argument-hint: <name> <path-to-existing-code>
---

Input: $ARGUMENTS

Goal: turn inherited code (for example, a previous student's practical) into a project
an agent can work on without supervision. Do not change the code's behaviour here.

1. Run `python3 framework/aaf.py new <name> --from "<path>"`. This copies the code
   into `projects/<name>/` and adds the framework files without overwriting anything.
2. `status <name> --phase planning --task "Onboard existing codebase"`.
3. Explore the code with the `mapper` subagent, so the reading stays out of your own
   context: give it the project path and ask for a map. It writes
   `projects/<name>/state/codebase-map.md` (entry points, modules, dependencies, how to
   run and test, data, risky areas). Read the map, check anything that looks uncertain,
   and record what matters for working on the code in `projects/<name>/CLAUDE.md`.
4. Establish a baseline:
   - Get the code to run as it is. Record any setup you needed.
   - Register the existing tests as checks in `project.json`. If there are none, add a
     smoke check that runs the main entry point on the smallest possible input.
   - Run `python3 framework/aaf.py check <name>` and note what already fails. Do not fix
     failures here; list them in `state/progress.md` as known issues.
5. If the code has no README.md, create one from `template/README.md`. If it has one,
   keep its content and add the "How it is checked" and "History" sections with their
   `<!-- aaf:... -->` markers from the template. Run `python3 framework/aaf.py readme <name>`.
6. Write `state/progress.md`: a map of the codebase (main modules, one line each), known
   issues, and the risky areas a future task should be careful with.
7. Record noteworthy findings with `aaf.py decide` (e.g. "Kept Python 3.8 because ...").
8. Set `status <name> --phase waiting --note "Question: put it on GitHub?"`, then ask the human whether to put the onboarded project on GitHub as a new private
   repository. If yes: `python3 framework/aaf.py git init <name>`. If the baseline
   checks failed, tell the human that this first commit holds the inherited code with
   its known failures, as listed in `progress.md`.
9. `status <name> --phase idle --note "Onboarded"` and give the human a short summary:
   what the code does, how it is checked now, and the three weakest spots.
