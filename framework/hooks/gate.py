#!/usr/bin/env python3
"""Claude Code Stop hook: keep a /task running until it has properly ended.

While the session's project is in an active phase (planning, implementing, checking,
reviewing, fixing), the agent may not simply stop talking. It must either continue the
loop or end it on the record with `aaf.py status <project> --phase done|stuck|waiting`
(waiting also covers asking the human a question). This turns the /task procedure from
advice into a rule.

During a feature run (`/task <p> all`, marked by `aaf.py run start <p>` in this session), it
also blocks the stop when a feature has ended `done` while others remain, and sends the agent
on to the next feature; once all pass, it asks once for `aaf.py run end <p>` and the report.
`waiting` and `stuck` still let the turn end, so the human is asked or told.

Safety valves:
- Never fires on a user interrupt (Claude Code does not run Stop hooks then).
- At most MAX_NUDGES blocks in a row per session; then it lets the turn end.
- Ignores projects whose status has not changed for STALE_HOURS (an abandoned run).
- Any error lets the turn end.
"""

import datetime as dt
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROJECTS = os.path.join(ROOT, "projects")
SESSIONS = os.path.join(ROOT, ".aaf", "sessions")
ACTIVE = {"planning", "implementing", "checking", "reviewing", "fixing"}
MAX_NUDGES = 3
STALE_HOURS = 6


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def session_file(session, suffix=""):
    return os.path.join(SESSIONS, re.sub(r"[^A-Za-z0-9_-]", "", session or "none") + suffix + ".json")


def active_project(session):
    """The project this session works on (remembered by the activity hook), if active."""
    # Only the project this very session has worked on: another session may be running a
    # task in parallel, and a plain chat session must never be held up by it.
    remembered = (read_json(session_file(session), {}) or {}).get("project")
    candidates = [remembered] if remembered else []
    now = dt.datetime.now().astimezone()
    best = None
    for name in candidates:
        st = read_json(os.path.join(PROJECTS, name, "state", "status.json"), {}) or {}
        if st.get("phase") not in ACTIVE:
            continue
        try:
            age = now - dt.datetime.fromisoformat(st.get("updated", ""))
        except ValueError:
            continue
        if age > dt.timedelta(hours=STALE_HOURS):
            continue
        if best is None or st.get("updated", "") > best[1].get("updated", ""):
            best = (name, st)
    return best


def run_continuation(session):
    """A feature run (`aaf.py run start`, claimed by this session) whose current feature ended
    `done` while others remain: the reason to carry on with the next one. Also a reminder to
    close the run once every feature passes. None when there is nothing to carry on with:
    no run, another session's run, or the phase is waiting / stuck / idle (the human decides)."""
    claim = (read_json(session_file(session, "-run"), {}) or {}).get("project")
    if not claim:
        return None
    pdir = os.path.join(PROJECTS, claim)
    if not os.path.exists(os.path.join(pdir, "state", "run.json")):
        return None
    st = read_json(os.path.join(pdir, "state", "status.json"), {}) or {}
    if st.get("phase") != "done":
        return None
    try:
        age = dt.datetime.now().astimezone() - dt.datetime.fromisoformat(st.get("updated", ""))
    except ValueError:
        return None
    if age > dt.timedelta(hours=STALE_HOURS):
        return None
    feats = (read_json(os.path.join(pdir, "features.json"), {}) or {}).get("features", [])
    left = [f for f in feats if not f.get("passes")]
    if not left:
        return claim, st, (
            "Every feature of '%s' passes. End the feature run on the record: "
            "`python3 framework/aaf.py run end %s`, then give the human the final report "
            "for the whole run (what each feature delivered, drafts waiting for a decision)." % (claim, claim))
    nxt = left[0]
    return claim, st, (
        "Feature run for '%s': the last feature is done and %d of %d features are left. "
        "Do not stop between features. Start the next one now with the /task procedure for `next` "
        "(orient, make it checkable, loop, review, finish and commit): %s %s. "
        "To stop the run instead, set the phase to waiting with a question, or end it with "
        "`python3 framework/aaf.py run end %s --reason \"...\"`."
        % (claim, len(left), len(feats), nxt.get("id"), nxt.get("title"), claim))


def block(counter_path, key, reason):
    """Block the stop with this reason, at most MAX_NUDGES times for the same key."""
    counter = read_json(counter_path, {}) or {}
    nudges = counter.get("nudges", 0) + 1 if counter.get("key") == key else 1
    if nudges > MAX_NUDGES:
        return
    os.makedirs(SESSIONS, exist_ok=True)
    with open(counter_path, "w", encoding="utf-8") as f:
        json.dump({"key": key, "nudges": nudges}, f)
    print(json.dumps({"decision": "block", "reason": reason}))


def main():
    data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))  # UTF-8 on Windows too
    session = data.get("session_id", "")
    found = active_project(session)
    counter_path = session_file(session, "-gate")
    if not found:
        cont = run_continuation(session)
        if cont:
            name, st, reason = cont
            block(counter_path, "run|%s|%s|%s" % (name, st.get("task", ""), st.get("updated", "")), reason)
        elif os.path.exists(counter_path):
            os.remove(counter_path)
        return
    name, st = found
    key = "%s|%s|%s" % (name, st.get("task", ""), st.get("updated", ""))

    checks = read_json(os.path.join(PROJECTS, name, "state", "checks.json"), {}) or {}
    results = checks.get("checks", [])
    passing = sum(1 for c in results if c.get("passed"))
    check_line = ("Checks: %d of %d passing." % (passing, len(results))) if results else "No check results yet."
    reason = (
        "The /task for project '%s' is still in phase '%s' (task: %s). %s "
        "Do not stop here. Either continue the loop, or end it on the record: "
        "`python3 framework/aaf.py status %s --phase done|stuck --note \"...\"`, or, to ask the human "
        "something, `python3 framework/aaf.py status %s --phase waiting --note \"Question: ...\"` and then ask."
        % (name, st.get("phase"), st.get("task", "?"), check_line, name, name))
    block(counter_path, key, reason)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
