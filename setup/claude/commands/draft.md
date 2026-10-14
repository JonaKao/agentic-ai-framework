---
description: Continue or discard a saved fix attempt
argument-hint: <project> continue|discard <draft-id> [extra guidance]
---

Input: $ARGUMENTS

Words: project `P`, action, draft ID `D`, then optional guidance from the human.
If the action or ID is missing, run `python3 framework/aaf.py draft list P`, show the
open drafts, and ask which one and what to do.

## continue

1. `python3 framework/aaf.py check P` must pass now; this state is the fallback.
2. `python3 framework/aaf.py draft apply P D`. This saves the current state as snapshot
   `before-draft-D`, puts the draft's files in place, and prints the issue and the notes
   from the last attempt. Read them carefully, and the
   human's extra guidance if any: do not repeat an approach that already failed.
3. Run the fix loop from `.claude/commands/fix.md` (steps 3 to 5) for this issue, with
   another `fix_iterations` iterations, using `before-draft-D` as the rollback
   snapshot and `D` as the draft ID if it has to be saved again.
4. If the fix was kept and `projects/P/.git` exists, run `python3 framework/aaf.py check P`,
   then `python3 framework/aaf.py git commit P --title "Fix: <issue>"`.
5. Report the outcome. If it failed again, say how many iterations the draft has used
   in total and ask once more whether to continue or discard.

## discard

1. `python3 framework/aaf.py draft discard P D`
2. Keep the issue under known issues in `state/progress.md`, noting that a fix was tried
   and discarded, with the one-line reason from the draft.
3. If no drafts remain open, set `status P --phase done --note "Drafts resolved"`.
