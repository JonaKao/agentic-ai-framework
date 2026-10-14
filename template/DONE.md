# Definition of done: {{NAME}}

A task is finished only when every item below holds. The reviewer checks each one.

## Always

- [ ] Every check in `project.json` passes (`python3 framework/aaf.py check {{NAME}}`)
- [ ] No check, test or threshold was weakened, skipped or removed to get there
- [ ] The task's own success is covered by a check, not only by manual inspection
- [ ] The reviewer subagent returned PASS
- [ ] `state/progress.md` says what changed and what is next
- [ ] Plots produced by the task were opened and inspected; irregularities are noted

## Project-specific

<!-- Add measurable criteria, e.g.:
- [ ] Validation accuracy >= 0.90 on the fixed split (seed 0)
- [ ] Training loss decreases monotonically over the last 50% of steps (smoothed)
- [ ] Peak memory under 8 GB on the MacBook
-->

## When stuck, report

- What you tried, in order, and why each attempt failed
- The failing check output (shortened)
- The one decision or piece of information you need from the human
