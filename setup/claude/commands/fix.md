---
description: Try to fix specific issues safely, rolling back and keeping a draft if a fix fails
argument-hint: <project> [issues to fix; default: known issues in progress.md]
---

Input: $ARGUMENTS

The first word is the project name `P`; the rest describes the issues to fix. With no
issues given, use the minor findings from the latest review
(`projects/P/state/reviews/latest.md`) that are still open in `state/progress.md`.
Never take findings marked `note`: they are style or future ideas, not defects.

The rule: **the project must end this procedure in a state where every check passes.**
A fix is either kept whole or rolled back whole.

Let `F` = `fix_iterations` from `projects/P/project.json` (default 3).

## For each issue (k = 1, 2, ...), one at a time

Related findings that touch the same lines may be handled as one issue.

1. **Save the good state.** `python3 framework/aaf.py check P` must pass now. Then
   `python3 framework/aaf.py snapshot P before-fix-<k>`.
2. **Make the issue checkable.** Add a test that reproduces it and confirm it fails.
3. **Fix loop**, for iteration i = 1 ... F. Every attempt counts, whether it fails a
   check or fails the review:
   - `status P --phase fixing --iteration i --note "Fixing: <issue, short>"`
   - make the smallest change, then `python3 framework/aaf.py check P`; if anything
     fails, start the next iteration
   - when every check passes, launch the `reviewer` subagent on this fix only (project
     path, the issue text, the files changed). PASS with no new blocker or major
     finding: the fix is done, go to step 4. FAIL: treat its findings like failing
     checks, write them down for the notes, and start the next iteration
   - stop early only if the same failure (same check, or same review finding) repeats
     three times in a row
4. **Fix kept**: record it with `aaf.py decide` (title starting with "Fixed: ") and
   remove the issue from the known issues in `progress.md`.
5. **Iterations used up or repeated failure**:
   - write a short note to `projects/P/state/drafts-notes.md`: what you tried, in
     order, with what each attempt broke (check output or review finding); your best
     guess at what is needed next
   - `python3 framework/aaf.py draft save P fix-<k> --issue "<issue>" --summary "<what went wrong, one line>" --iterations <i> --notes projects/P/state/drafts-notes.md`
   - `python3 framework/aaf.py restore P before-fix-<k>`
   - `python3 framework/aaf.py check P` and confirm everything passes again. If not,
     stop and report immediately: the rollback did not restore a green state. The
     files from just before the rollback are in `state/snapshots/before-last-restore`.
   - keep the issue under known issues in `progress.md`, with "draft fix-<k> available"

## Afterwards

If this procedure was started on its own (with `/fix`, not from inside `/task`), any fixes
were kept, and `projects/P/.git` exists: run `python3 framework/aaf.py check P`, then
`python3 framework/aaf.py git commit P --title "Fix: <short summary of the kept fixes>"`.
Inside `/task`, the task's own commit at the end includes them.

If any drafts were saved, set `status P --phase waiting --note "<n> draft(s) need a decision"`.
For each draft, tell the human what you tried, what went wrong, and ask:
"Continue this draft, or discard it and keep the issue on record?"
