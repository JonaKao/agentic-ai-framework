---
description: Interview the human and write a spec before a large task
argument-hint: <project> <brief description of what to build>
---

Input: $ARGUMENTS

The first word is the project `P`; the rest is a brief description. Use this before any
task that touches several files, has an unclear approach, or will take more than one
session. Small, clear changes go straight to `/task`.

1. Set `python3 framework/aaf.py status P --phase waiting --note "Writing a spec with you"`.
2. Read `projects/P/CLAUDE.md`, `projects/P/README.md`, `projects/P/state/progress.md`
   and the code the description touches, so your questions are informed.
3. Interview the human with the AskUserQuestion tool, a few questions at a time. Ask about
   what you cannot work out from the code: intended behaviour, edge cases, constraints,
   trade-offs, what is out of scope, and how they would recognise success. Skip the
   obvious; dig into the hard parts they may not have considered.
4. Write `projects/P/specs/<short-name>.md`:
   - **Goal**: what it is for, in two or three sentences
   - **Scope** and **out of scope**
   - **Design**: the files, modules and interfaces involved, and the approach
   - **Features**: each one a user-visible, end-to-end behaviour, with its acceptance
     criteria written so a check can test it
   - **Verification**: the end-to-end check that proves the whole thing works
   - **Open questions**, if any remain
5. Register each feature: `python3 framework/aaf.py feature add P --title "<feature>" --criteria "<acceptance criteria>" --spec specs/<short-name>.md`
6. `python3 framework/aaf.py decide P "Spec: <short-name>" "<the main choices made in the interview>"`
7. `python3 framework/aaf.py status P --phase idle --note "Spec ready: specs/<short-name>.md"`.
8. Tell the human the spec is ready and how to run it: first `/clear` (a fresh session
   implements best from the written spec alone), then `/task P next` once per feature,
   or `/task P implement specs/<short-name>.md` for a small spec.
