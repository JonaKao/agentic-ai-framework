---
description: Run a task in a project until its definition of done holds
argument-hint: <project> <what to do>
---

Input: $ARGUMENTS

The first word is the project name; the rest is the task. The project lives in
`projects/<project>/`. If it does not exist, list the folders in `projects/` and stop.

If the task is just `next`, take the next unfinished feature from the project's feature
list: `python3 framework/aaf.py feature next <project>`. Its title and criteria are the
task, and its spec file (if any) is required reading. If the task names a spec file, read
it first and work from it. When a feature's criteria are met and checked end to end, mark
it with `python3 framework/aaf.py feature pass <project> <ID> --evidence "<the check that proves it>"`
before finishing. Never edit or remove features; if one is wrong, say so in your report.

Use `P` for the project name below. Report every phase change with
`python3 framework/aaf.py status P --phase <phase> ...` so the dashboard stays live.

## 1. Orient

- Read `projects/P/CLAUDE.md`, `projects/P/DONE.md`, `projects/P/project.json`,
  `projects/P/state/progress.md` and `projects/P/state/decisions.md`.
- Run `python3 framework/aaf.py status P --phase planning --task "<the task, one line>" --iteration 0`.
- If `projects/P/.git` exists, run `python3 framework/aaf.py git pull P` to start from
  the latest version on GitHub. If it reports diverged histories, stop and ask the human.
- Run `python3 framework/aaf.py check P` once to get a baseline (a smoke test). Note
  which checks already fail before you change anything, and fix existing breakage
  before starting new work. If `projects/P/features.json` exists, run
  `python3 framework/aaf.py feature list P` too.

## 2. Make the task checkable

- Decide what would prove this task is done. If no existing check covers it, add a
  test or a check script, register it in `project.json` under `checks`, and confirm
  it fails now.
- If you make a non-obvious choice (approach, library, threshold), record it with
  `python3 framework/aaf.py decide P "<title>" "<why, and what you rejected>"`.
- Record your plan as 3 to 8 concrete steps, in order, each one something you can
  finish and recognise as finished:
  `python3 framework/aaf.py plan P --step "<step 1>" --step "<step 2>" ...`
  Tick each one off the moment it is done: `python3 framework/aaf.py step P <number>`.
  If the work turns out bigger, add steps with `python3 framework/aaf.py plan P --add "<step>"`
  rather than hiding it. The dashboard's time estimate is built from these steps.

## 3. Loop

Repeat for iteration n = 1, 2, ... up to `max_iterations` from `project.json`:

1. `status P --phase implementing --iteration n --note "<what you are trying>"`,
   then make the smallest change that moves toward passing.
2. `status P --phase checking --iteration n`, then `python3 framework/aaf.py check P`.
   If anything fails, read the output, and start the next iteration.
3. When every check passes: `status P --phase reviewing --iteration n`. Launch the
   `reviewer` subagent. Give it only: the project path, the task text, the list of files
   you changed, and the instruction to review against `DONE.md`. Do not give it your
   reasoning or your opinion of the change.
4. Record its verdict: `python3 framework/aaf.py review P --verdict <pass|fail> --summary "<one line>" --file <path to saved report>`
   (save the reviewer's full report to `projects/P/state/reviews/latest.md` first).
   If the verdict is FAIL, treat its findings like failing checks and start the next
   iteration.
5. If the verdict is PASS and every item in `DONE.md` holds, go to step 4.
   Blocker and major findings always mean FAIL; minor findings allow a PASS.

If the task involves training, metrics or data, generate plots into `projects/P/plots/`
during the loop and open them with the Read tool before declaring success.

## Guardrails

- A Stop hook keeps this task running while the phase is active. To pause and ask the
  human something, first set `status P --phase waiting --note "Question: <question>"`,
  then ask. When they answer, set the phase back and continue.

- Never weaken, skip or delete a check to make it pass (see the workspace CLAUDE.md).
- The same failure three times in a row, or reaching `max_iterations`, means stuck:
  `status P --phase stuck --note "<one line on what blocks you>"`, then go to step 5.

## 4. Attempt the minor findings

If the reviewer passed the change but listed **minor** findings, try to fix them now,
safely. Findings marked **note** are not fixed: record them under "Next" in
`progress.md` and leave them for the human to decide. Read `.claude/commands/fix.md` and follow it for this project, with the
reviewer's minor findings as the input. It snapshots the working state first, gives
each fix a limited number of iterations, and rolls back to the passing state if a fix
does not work out, keeping the attempt as a draft for the human.

Skip this step if the task text says not to fix follow-ups, or if `fix_iterations` in
`project.json` is 0.

## 5. Finish

- Update `projects/P/state/progress.md`: what was done, what is next, open issues.
- Update `projects/P/README.md` wherever the task changed what the project does, how to
  run it, or how it is built. Write for someone who has never seen the project. Leave
  the generated sections between `<!-- aaf:... -->` markers alone; `aaf.py git commit`
  refreshes them. If the README is missing, create it from `template/README.md`.
- Set the final phase: `waiting` if any drafts from step 4 need a decision, otherwise
  `done` (or `stuck`), with a one-line `--note`.
- If `projects/P/.git` exists and the phase is `done` or `waiting`, run
  `python3 framework/aaf.py check P` once more, then `python3 framework/aaf.py git commit P`.
  It writes the commit message from the task, the decisions, the checks and the review,
  and pushes to GitHub. Never commit when stuck; drafts are never committed.
- Report to the human in a few lines: what changed, the evidence (checks, review
  verdict, plots looked at), which minor findings were fixed, and for each draft:
  what you tried, what went wrong, and the question "Continue this draft, or discard
  it and keep the issue on record?" Use the reply as described in `.claude/commands/draft.md`.
