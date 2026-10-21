#!/usr/bin/env python3
"""Claude Code hook: log what the agent is doing, in plain words, for the control room.

Registered in .claude/settings.json (installed from setup/claude/settings.json) for
PreToolUse, PostToolUse, PostToolUseFailure, PermissionRequest, Notification,
UserPromptSubmit, SubagentStart, SubagentStop and Stop, always in the background.

Record fields: ts, kind, text, optional detail, subagent, tool_use_id and quiet.
- PreToolUse writes the step ("Reading train.py") with its tool_use_id.
- PermissionRequest writes kind "waiting" with the same tool_use_id.
- PostToolUse / PostToolUseFailure write kind "done" / "error" for that tool_use_id.
  "done" records carry quiet: true: they are not steps of their own, but they show
  that the step ran, which also means any permission it needed was granted.
- UserPromptSubmit writes kind "you": the human answered in Claude Code. It reads the hook's JSON on stdin, works out which project the step
belongs to, and appends one line to projects/<name>/state/activity.jsonl.

It must never get in the agent's way: every error is swallowed and it always exits 0.
Standard library only.
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
MAX_BYTES = 1_000_000          # trim the log when it grows past this
KEEP_LINES = 1500
AAF_WORDS = {
    "check": "Running the tests", "status": "Updating its status", "decide": "Recording a decision",
    "review": "Recording the review", "snapshot": "Saving a snapshot", "restore": "Rolling back",
    "draft": "Handling a draft", "git": "Working with Git", "new": "Creating a project",
}


def now():
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def short(text, n=110):
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


def rel(path, project):
    """A path as the human would recognise it: relative to the project when possible."""
    if not path:
        return ""
    p = os.path.abspath(os.path.join(ROOT, path)) if not os.path.isabs(path) else path
    base = os.path.join(PROJECTS, project) if project else ROOT
    try:
        r = os.path.relpath(p, base)
        return r if not r.startswith("..") else os.path.basename(p)
    except ValueError:
        return os.path.basename(p)


def projects():
    try:
        return [p for p in os.listdir(PROJECTS) if os.path.isdir(os.path.join(PROJECTS, p))]
    except OSError:
        return []


def project_from_text(text):
    names = projects()
    m = re.search(r"aaf\.py\s+(?:git|draft)\s+\S+\s+([A-Za-z0-9][A-Za-z0-9_.-]*)", text or "")
    if not m:
        m = re.search(r"aaf\.py\s+(?:check|status|decide|review|snapshot|restore|new)\s+([A-Za-z0-9][A-Za-z0-9_.-]*)", text or "")
    if m and m.group(1) in names:
        return m.group(1)
    m = re.search(r"projects/([A-Za-z0-9][A-Za-z0-9_.-]*)", text or "")
    if m and m.group(1) in names:
        return m.group(1)
    return None


def sticky(session, project=None):
    """Remember the last project per session, so steps without a path still land somewhere."""
    if not session:
        return project
    path = os.path.join(SESSIONS, re.sub(r"[^A-Za-z0-9_-]", "", session) + ".json")
    try:
        if project:
            os.makedirs(SESSIONS, exist_ok=True)
            with open(path, "w") as f:
                json.dump({"project": project}, f)
            return project
        with open(path) as f:
            return json.load(f).get("project")
    except (OSError, ValueError):
        return project


def most_active():
    best, best_t = None, ""
    for p in projects():
        try:
            with open(os.path.join(PROJECTS, p, "state", "status.json")) as f:
                st = json.load(f)
        except (OSError, ValueError):
            continue
        if st.get("phase") in ACTIVE and st.get("updated", "") > best_t:
            best, best_t = p, st.get("updated", "")
    return best


def describe(data, project):
    """(kind, plain-language text, detail) for one hook call."""
    ev = data.get("hook_event_name", "")
    if ev == "UserPromptSubmit":
        return "you", "You sent a message in Claude Code", ""
    if ev == "PermissionRequest":
        _, step, _ = describe(dict(data, hook_event_name="PreToolUse"), project)
        return "waiting", "Waiting for your permission in Claude Code", step
    if ev in ("PostToolUse", "PostToolUseFailure"):
        _, step, _ = describe(dict(data, hook_event_name="PreToolUse"), project)
        if ev == "PostToolUseFailure":
            return "error", "A step did not work: " + step[:1].lower() + step[1:], short(data.get("error", ""))
        return "done", "Finished: " + step[:1].lower() + step[1:], ""
    if ev == "Notification":
        msg = data.get("message", "")
        ntype = data.get("notification_type", "") or data.get("matcher", "")
        if "permission" in (ntype + msg).lower():
            return "waiting", "Waiting for your permission in Claude Code", short(msg)
        if "idle" in ntype.lower() or "waiting for your input" in msg.lower():
            return "waiting", "Waiting for your reply in Claude Code", short(msg)
        return "note", short(msg) or "Notification", ""
    if ev == "SubagentStart":
        return "agent", "Started the %s" % (data.get("agent_type") or "helper agent"), ""
    if ev == "SubagentStop":
        return "agent", "The %s finished" % (data.get("agent_type") or "helper agent"), ""
    if ev == "Stop":
        return "turn", "Finished its turn", ""

    tool, ti = data.get("tool_name", ""), data.get("tool_input") or {}
    if tool == "Read":
        return "read", "Reading %s" % rel(ti.get("file_path"), project), ""
    if tool in ("Edit", "MultiEdit"):
        return "edit", "Editing %s" % rel(ti.get("file_path"), project), ""
    if tool == "Write":
        return "edit", "Writing %s" % rel(ti.get("file_path"), project), ""
    if tool in ("Grep", "Glob"):
        return "search", "Searching for %s" % short(ti.get("pattern", ""), 60), ""
    if tool == "Bash":
        cmd = ti.get("command", "")
        m = re.search(r"aaf\.py\s+(\w+)(?:\s+(\w[\w-]*))?", cmd)
        if m:
            words = AAF_WORDS.get(m.group(1), "Using the framework tool")
            if m.group(1) in ("git", "draft") and m.group(2):
                words += " (%s)" % m.group(2)
            return "framework", words, short(cmd)
        if re.search(r"\b(pytest|unittest|npm test|make test)\b", cmd):
            return "test", "Running tests", short(cmd)
        return "command", ti.get("description") or "Running a command", short(cmd)
    if tool in ("Task", "Agent"):
        who = ti.get("subagent_type") or "helper agent"
        return "agent", "Asking the %s: %s" % (who, short(ti.get("description", ""), 60)), ""
    if tool in ("WebFetch", "WebSearch"):
        return "web", "Looking something up online", short(ti.get("url") or ti.get("query") or "")
    if tool in ("TodoWrite", "TaskCreate", "TaskUpdate"):
        return "plan", "Updating its plan", ""
    return "other", "Using %s" % (tool or "a tool"), ""


def record_usage(data, project):
    """On Stop: total the session's token usage from its transcript and append it to
    state/usage.jsonl (cumulative per session). Best effort; the transcript may lag."""
    path = data.get("transcript_path")
    if not path or not os.path.isfile(path):
        return
    seen, tot = set(), {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    with open(path) as f:
        for line in f:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            msg = rec.get("message") if isinstance(rec, dict) else None
            if not isinstance(msg, dict) or not isinstance(msg.get("usage"), dict):
                continue
            key = msg.get("id") or rec.get("requestId") or rec.get("uuid")
            if key in seen:
                continue
            seen.add(key)
            u = msg["usage"]
            tot["input"] += int(u.get("input_tokens") or 0)
            tot["output"] += int(u.get("output_tokens") or 0)
            tot["cache_read"] += int(u.get("cache_read_input_tokens") or 0)
            tot["cache_write"] += int(u.get("cache_creation_input_tokens") or 0)
    if not any(tot.values()):
        return
    out = os.path.join(PROJECTS, project, "state", "usage.jsonl")
    rec = {"ts": now(), "session": data.get("session_id", ""), **tot}
    with open(out, "a") as f:
        f.write(json.dumps(rec) + "\n")


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return
    session = data.get("session_id", "")
    blob = json.dumps(data.get("tool_input") or {})
    project = project_from_text(blob)
    project = sticky(session, project) if project else (sticky(session) or most_active())
    if not project:
        return
    kind, text, detail = describe(data, project)
    rec = {"ts": now(), "kind": kind, "text": text}
    if detail and detail != text:
        rec["detail"] = detail
    if data.get("tool_use_id"):
        rec["tool_use_id"] = data["tool_use_id"]
    if kind == "done":
        rec["quiet"] = True
    if data.get("agent_type") or data.get("agent_id"):
        rec["subagent"] = data.get("agent_type") or "subagent"
    if data.get("hook_event_name") == "Stop":
        try:
            record_usage(data, project)
        except Exception:
            pass
    path = os.path.join(PROJECTS, project, "state", "activity.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(rec) + "\n")
    if os.path.getsize(path) > MAX_BYTES:
        with open(path) as f:
            lines = f.readlines()[-KEEP_LINES:]
        with open(path, "w") as f:
            f.writelines(lines)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # never disturb the agent
        pass
    sys.exit(0)
