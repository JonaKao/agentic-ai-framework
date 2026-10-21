#!/usr/bin/env python3
"""Claude Code Stop hook: keep a /task running until it has properly ended.

While the session's project is in an active phase (planning, implementing, checking,
reviewing, fixing), the agent may not simply stop talking. It must either continue the
loop or end it on the record with `aaf.py status <project> --phase done|stuck|waiting`
(waiting also covers asking the human a question). This turns the /task procedure from
advice into a rule.

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
        with open(path) as f:
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


def main():
    data = json.load(sys.stdin)
    session = data.get("session_id", "")
    found = active_project(session)
    counter_path = session_file(session, "-gate")
    if not found:
        if os.path.exists(counter_path):
            os.remove(counter_path)
        return
    name, st = found
    counter = read_json(counter_path, {}) or {}
    key = "%s|%s|%s" % (name, st.get("task", ""), st.get("updated", ""))
    nudges = counter.get("nudges", 0) + 1 if counter.get("key") == key else 1
    if nudges > MAX_NUDGES:
        return
    os.makedirs(SESSIONS, exist_ok=True)
    with open(counter_path, "w") as f:
        json.dump({"key": key, "nudges": nudges}, f)

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
    print(json.dumps({"decision": "block", "reason": reason}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
