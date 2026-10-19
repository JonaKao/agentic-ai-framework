#!/usr/bin/env python3
"""Agentic AI Framework CLI: the single way agents record project state.

Usage (from the workspace root):
  python3 framework/aaf.py new <name> [--description TEXT] [--from PATH]
  python3 framework/aaf.py check <name>
  python3 framework/aaf.py status <name> --phase PHASE [--task TEXT] [--iteration N] [--note TEXT]
  python3 framework/aaf.py decide <name> TITLE RATIONALE
  python3 framework/aaf.py review <name> --verdict pass|fail --summary TEXT [--file PATH]
  python3 framework/aaf.py snapshot <name> LABEL
  python3 framework/aaf.py restore <name> LABEL
  python3 framework/aaf.py draft save <name> ID --issue TEXT --summary TEXT [--iterations N] [--notes PATH]
  python3 framework/aaf.py draft apply|discard <name> ID
  python3 framework/aaf.py draft list <name>
  python3 framework/aaf.py git init <name> [--repo NAME] [--public] [--no-remote]
  python3 framework/aaf.py git init-framework [--repo NAME] [--public] [--no-remote]
  python3 framework/aaf.py git commit <name> [--title TEXT] [--allow-failing]
  python3 framework/aaf.py git commit-framework [--title TEXT]
  python3 framework/aaf.py git push|pull <name>
  python3 framework/aaf.py git info <name> [--fetch]
  python3 framework/aaf.py git files <name>
  python3 framework/aaf.py stats <name>
  python3 framework/aaf.py readme <name>
  python3 framework/aaf.py plan <name> --step TEXT [--step TEXT ...] | --add TEXT
  python3 framework/aaf.py step <name> N
  python3 framework/aaf.py estimate <name>
  python3 framework/aaf.py list

Standard library only; runs on the Python 3.9 that ships with macOS.
"""

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECTS = os.path.join(ROOT, "projects")
TEMPLATE = os.path.join(ROOT, "template")
PHASES = ["idle", "planning", "implementing", "checking", "reviewing", "fixing", "waiting", "done", "stuck"]
SKIP = {"state", "__pycache__", ".git", ".venv", "venv", "node_modules", ".DS_Store"}
KEEP_ON_RESTORE = {"state", ".git", ".venv", "venv", "node_modules"}
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def now():
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def die(msg, code=1):
    print("aaf: " + msg, file=sys.stderr)
    sys.exit(code)


def project_dir(name, must_exist=True):
    if not NAME_RE.match(name or ""):
        die("invalid project name %r (letters, digits, - _ . only)" % name)
    path = os.path.join(PROJECTS, name)
    if must_exist and not os.path.isdir(path):
        existing = sorted(p for p in os.listdir(PROJECTS) if os.path.isdir(os.path.join(PROJECTS, p)))
        die("no project %r. Existing: %s" % (name, ", ".join(existing) or "none"))
    return path


def read_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def append_jsonl(path, record):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")


def event(pdir, kind, text, **fields):
    """Append to the project's event log. Extra fields keep the record machine-readable
    for the dashboard's timeline and track record; the text is for people."""
    rec = {"ts": now(), "kind": kind, "text": text}
    rec.update({k: v for k, v in fields.items() if v is not None})
    append_jsonl(os.path.join(pdir, "state", "events.jsonl"), rec)


# ---------------------------------------------------------------- new

def cmd_new(args):
    pdir = project_dir(args.name, must_exist=False)
    if os.path.exists(pdir) and os.listdir(pdir) and not args.src:
        die("project %r already exists" % args.name)
    if args.src:
        src = os.path.abspath(os.path.expanduser(args.src))
        if not os.path.isdir(src):
            die("source folder not found: %s" % src)
        shutil.copytree(src, pdir, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv", "venv", "node_modules"))
    os.makedirs(pdir, exist_ok=True)

    subs = {"{{NAME}}": args.name, "{{DESCRIPTION}}": args.description or ""}
    for dirpath, _, files in os.walk(TEMPLATE):
        rel = os.path.relpath(dirpath, TEMPLATE)
        target_dir = os.path.join(pdir, rel) if rel != "." else pdir
        os.makedirs(target_dir, exist_ok=True)
        for fn in files:
            target = os.path.join(target_dir, fn)
            if os.path.exists(target):
                # Inherited code keeps its own files; framework copy goes beside it.
                if fn == "CLAUDE.md":
                    target = os.path.join(target_dir, "CLAUDE.framework.md")
                else:
                    continue
            with open(os.path.join(dirpath, fn)) as f:
                text = f.read()
            for k, v in subs.items():
                text = text.replace(k, v)
            with open(target, "w") as f:
                f.write(text)

    for sub in ("plots", os.path.join("state", "reviews")):
        os.makedirs(os.path.join(pdir, sub), exist_ok=True)

    pj = os.path.join(pdir, "project.json")
    if not os.path.exists(pj):
        write_json(pj, {
            "name": args.name,
            "description": args.description or "",
            "max_iterations": 8,
            "fix_iterations": 3,
            "checks": [],
        })
    write_json(os.path.join(pdir, "state", "status.json"), {
        "phase": "idle", "task": "", "iteration": 0, "note": "Project created", "updated": now(),
    })
    event(pdir, "status", "Project created" + (" from %s" % args.src if args.src else ""))
    print("Created projects/%s" % args.name)


# ---------------------------------------------------------------- check

def tail(text, limit=4000):
    text = text or ""
    return text if len(text) <= limit else "...\n" + text[-limit:]


def cmd_check(args):
    pdir = project_dir(args.name)
    cfg = read_json(os.path.join(pdir, "project.json"), {})
    checks = cfg.get("checks", [])
    results = []
    if not checks:
        print("No checks defined in project.json. Add at least one.")
    for chk in checks:
        name = chk.get("name") or chk.get("cmd")
        timeout = chk.get("timeout", 600)
        t0 = time.time()
        try:
            proc = subprocess.run(chk["cmd"], shell=True, cwd=pdir, capture_output=True,
                                  text=True, timeout=timeout)
            passed = proc.returncode == 0
            output = (proc.stdout or "") + (proc.stderr or "")
            code = proc.returncode
        except subprocess.TimeoutExpired as e:
            passed, code = False, None
            output = "TIMEOUT after %ss\n%s" % (timeout, (e.stdout or "") if isinstance(e.stdout, str) else "")
        dur = round(time.time() - t0, 2)
        results.append({"name": name, "cmd": chk["cmd"], "passed": passed, "exit_code": code,
                        "duration_s": dur, "output": tail(output)})
        print("%s  %s  (%.1fs)" % ("PASS" if passed else "FAIL", name, dur))
        if not passed:
            print("    " + tail(output, 1500).replace("\n", "\n    "))

    all_passed = bool(results) and all(r["passed"] for r in results)
    record = {"ran_at": now(), "passed": all_passed, "checks": results}
    write_json(os.path.join(pdir, "state", "checks.json"), record)
    n_ok = sum(r["passed"] for r in results)
    append_jsonl(os.path.join(pdir, "state", "check_history.jsonl"),
                 {"ran_at": record["ran_at"], "passed": all_passed, "n_pass": n_ok, "n_total": len(results)})
    event(pdir, "check", "Checks %s: %d of %d passed" % ("passed" if all_passed else "failed", n_ok, len(results)),
          passed=all_passed, n_pass=n_ok, n_total=len(results),
          failed=[r["name"] for r in results if not r["passed"]] or None)
    print("\n%d of %d checks passed." % (n_ok, len(results)))
    sys.exit(0 if all_passed else 1)


# ---------------------------------------------------------------- status

def cmd_status(args):
    pdir = project_dir(args.name)
    path = os.path.join(pdir, "state", "status.json")
    st = read_json(path, {})
    st["phase"] = args.phase
    if args.task is not None:
        st["task"] = args.task
        st["task_started"] = now()
    if args.iteration is not None:
        st["iteration"] = args.iteration
    st["note"] = args.note or ""
    st["updated"] = now()
    write_json(path, st)
    text = args.phase.capitalize()
    if args.iteration:
        text += " (iteration %d)" % args.iteration
    if args.note:
        text += ": " + args.note
    elif args.task:
        text += ": " + args.task
    event(pdir, "status", text, phase=args.phase, iteration=args.iteration, task=args.task)
    _log_estimate(pdir)
    print(text)


# ---------------------------------------------------------------- decide

def cmd_decide(args):
    pdir = project_dir(args.name)
    path = os.path.join(pdir, "state", "decisions.md")
    day = dt.date.today().isoformat()
    with open(path, "a") as f:
        f.write("\n## %s: %s\n\n%s\n" % (day, args.title.strip(), args.rationale.strip()))
    event(pdir, "decision", args.title.strip(), title=args.title.strip())
    print("Recorded decision: " + args.title)


# ---------------------------------------------------------------- review

def cmd_review(args):
    pdir = project_dir(args.name)
    report = ""
    if args.file:
        try:
            with open(args.file) as f:
                report = f.read()
        except OSError as e:
            die("cannot read report: %s" % e)
    rec = {"at": now(), "verdict": args.verdict, "summary": args.summary, "report": report}
    write_json(os.path.join(pdir, "state", "review.json"), rec)
    append_jsonl(os.path.join(pdir, "state", "review_history.jsonl"),
                 {"at": rec["at"], "verdict": args.verdict, "summary": args.summary})
    event(pdir, "review", "Review %s: %s" % (args.verdict.upper(), args.summary), verdict=args.verdict)
    print("Recorded review: " + args.verdict.upper())



# ---------------------------------------------------------------- snapshots and drafts
#
# A snapshot is a copy of the project's working files (everything except state/).
# Drafts are snapshots of an unfinished fix attempt, kept until the human decides.

NESTED_SKIP = {"__pycache__", ".git", ".venv", "venv", "node_modules", ".DS_Store"}


def _copy_tree(src, dst):
    """Copy project files from src to dst. Skips the project's own top-level state/ and
    caches. Nested folders named state/ (for example test fixtures) are project files
    and are copied like everything else."""
    os.makedirs(dst, exist_ok=True)
    for entry in os.listdir(src):
        if entry in SKIP:
            continue
        s, d = os.path.join(src, entry), os.path.join(dst, entry)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*NESTED_SKIP))
        else:
            shutil.copy2(s, d)


def _file_set(root):
    """Relative paths of the files _copy_tree would copy from root."""
    out = set()
    for entry in os.listdir(root):
        if entry in SKIP:
            continue
        path = os.path.join(root, entry)
        if os.path.isdir(path):
            for dirpath, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if d not in NESTED_SKIP]
                for fn in files:
                    if fn not in NESTED_SKIP:
                        out.add(os.path.relpath(os.path.join(dirpath, fn), root))
        else:
            out.add(entry)
    return out


def _clear_working_files(pdir):
    """Remove the project's working files. Keeps state/ (snapshots, history), the Git
    repository and local environments, which are not part of a snapshot."""
    for entry in os.listdir(pdir):
        if entry in KEEP_ON_RESTORE:
            continue
        path = os.path.join(pdir, entry)
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.remove(path)


def _label(text):
    if not NAME_RE.match(text or ""):
        die("invalid label %r (letters, digits, - _ . only)" % text)
    return text


def _snapshot(pdir, label):
    dst = os.path.join(pdir, "state", "snapshots", _label(label))
    if os.path.exists(dst):
        shutil.rmtree(dst)
    _copy_tree(pdir, dst)
    return dst


def _restore_from(pdir, src):
    """Replace the working files with those in src. Keeps a backup of the current files
    in state/snapshots/before-last-restore and verifies the result, so a rollback can
    itself be undone."""
    if not os.path.isdir(src):
        die("nothing to restore at %s" % os.path.relpath(src, pdir))
    backup = os.path.join(pdir, "state", "snapshots", "before-last-restore")
    if os.path.abspath(src) != os.path.abspath(backup):
        if os.path.exists(backup):
            shutil.rmtree(backup)
        _copy_tree(pdir, backup)
    _clear_working_files(pdir)
    _copy_tree(src, pdir)
    expected, actual = _file_set(src), _file_set(pdir)
    if expected != actual:
        missing = sorted(expected - actual)[:10]
        extra = sorted(actual - expected)[:10]
        die("restore did not reproduce the snapshot exactly (missing: %s; extra: %s). "
            "The files from before the restore are in state/snapshots/before-last-restore."
            % (missing, extra))


def cmd_snapshot(args):
    pdir = project_dir(args.name)
    _snapshot(pdir, args.label)
    event(pdir, "status", "Snapshot saved: %s" % args.label)
    print("Snapshot saved: state/snapshots/%s" % args.label)


def cmd_restore(args):
    pdir = project_dir(args.name)
    _restore_from(pdir, os.path.join(pdir, "state", "snapshots", _label(args.label)))
    event(pdir, "status", "Rolled back to snapshot %s" % args.label, action="restore", label=args.label)
    print("Restored project files from snapshot %s" % args.label)


def _draft_dir(pdir, draft_id):
    return os.path.join(pdir, "state", "drafts", _label(draft_id))


def cmd_draft(args):
    pdir = project_dir(args.name)
    if args.action != "list" and not args.id:
        die("draft %s needs a draft ID" % args.action)
    ddir = _draft_dir(pdir, args.id) if args.id else None

    if args.action == "save":
        if not args.issue or not args.summary:
            die("draft save needs --issue and --summary")
        if os.path.exists(ddir):
            shutil.rmtree(ddir)
        _copy_tree(pdir, os.path.join(ddir, "files"))
        notes = ""
        if args.notes:
            try:
                with open(args.notes) as f:
                    notes = f.read()
            except OSError as e:
                die("cannot read notes: %s" % e)
        prev = read_json(os.path.join(pdir, "state", "drafts_history.json"), {}).get(args.id, {})
        meta = {"id": args.id, "issue": args.issue, "summary": args.summary, "notes": notes,
                "iterations": (args.iterations or 0) + prev.get("iterations", 0),
                "rounds": prev.get("rounds", 0) + 1, "created": now(), "status": "open"}
        write_json(os.path.join(ddir, "meta.json"), meta)
        event(pdir, "draft", "Draft saved: %s (%s)" % (args.issue, args.summary), action="save", draft=args.id)
        print("Draft %s saved after %d iteration(s) in total" % (args.id, meta["iterations"]))

    elif args.action == "apply":
        meta = read_json(os.path.join(ddir, "meta.json"), None)
        if not meta:
            die("no draft %r" % args.id)
        _snapshot(pdir, "before-draft-" + args.id)
        _restore_from(pdir, os.path.join(ddir, "files"))
        hist_path = os.path.join(pdir, "state", "drafts_history.json")
        hist = read_json(hist_path, {})
        hist[args.id] = {"iterations": meta["iterations"], "rounds": meta["rounds"], "issue": meta["issue"]}
        write_json(hist_path, hist)
        shutil.rmtree(ddir)
        event(pdir, "draft", "Continuing draft: %s" % meta["issue"], action="apply", draft=args.id)
        print("Draft %s applied. Previous state saved as snapshot before-draft-%s.\n" % (args.id, args.id))
        print("Issue: %s\nLast attempt: %s\n%s" % (meta["issue"], meta["summary"], meta.get("notes", "")))

    elif args.action == "discard":
        meta = read_json(os.path.join(ddir, "meta.json"), None)
        if not meta:
            die("no draft %r" % args.id)
        shutil.rmtree(ddir)
        hist_path = os.path.join(pdir, "state", "drafts_history.json")
        hist = read_json(hist_path, {})
        if hist.pop(args.id, None) is not None:
            write_json(hist_path, hist)
        append_jsonl(os.path.join(pdir, "state", "discarded_drafts.jsonl"),
                     {"at": now(), "id": args.id, "issue": meta["issue"], "summary": meta["summary"],
                      "iterations": meta["iterations"]})
        event(pdir, "draft", "Draft discarded, kept as known issue: %s" % meta["issue"], action="discard", draft=args.id)
        print("Draft %s discarded. Record it as a known issue in state/progress.md." % args.id)

    elif args.action == "list":
        root = os.path.join(pdir, "state", "drafts")
        found = False
        for d in sorted(os.listdir(root)) if os.path.isdir(root) else []:
            meta = read_json(os.path.join(root, d, "meta.json"), None)
            if meta:
                found = True
                print("%-20s %d iteration(s)  %s\n    %s" % (d, meta["iterations"], meta["issue"], meta["summary"]))
        if not found:
            print("No open drafts.")


# ---------------------------------------------------------------- git
#
# Every project can be its own Git repository with a private GitHub remote.
# Commits are only made through `aaf.py git commit`, which refuses while checks fail
# and writes the message from the recorded task, decisions, checks and review.

GITIGNORE = """# Agentic AI Framework: local-only working state.
# Progress, decisions and reviews are committed; the live dashboard status is not.
state/snapshots/
state/drafts/
state/drafts_history.json
state/drafts-notes.md
state/status.json
state/checks.json
state/check_history.jsonl
state/events.jsonl
state/git.json
state/activity.jsonl
state/plan.json
state/estimates.jsonl
*.tmp
.venv/
venv/
__pycache__/
*.pyc
.DS_Store
"""

FRAMEWORK_GITIGNORE_EXTRA = """
# Each project is its own repository
projects/*/
# Installed copy of setup/claude/ (plus Claude Code's local settings)
.claude/
# Hook scratch data
.aaf/
"""

TRAILER_RE = re.compile(r"^([A-Za-z][A-Za-z-]*): (.+)$")


def run(cmd, cwd, check=True):
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    except FileNotFoundError:
        die("%s is not installed" % cmd[0])
    if check and proc.returncode != 0:
        die("%s failed:\n%s" % (" ".join(cmd[:3]), (proc.stderr or proc.stdout).strip()))
    return proc


def is_repo(path):
    return os.path.isdir(os.path.join(path, ".git"))


def ensure_gitignore(path, extra=""):
    gi = os.path.join(path, ".gitignore")
    wanted = GITIGNORE + extra
    if not os.path.exists(gi):
        with open(gi, "w") as f:
            f.write(wanted)
        return
    existing = open(gi).read()
    have = set(existing.splitlines())
    missing = [l for l in wanted.splitlines() if l and not l.startswith("#") and l not in have]
    if missing:
        with open(gi, "a") as f:
            f.write(("" if existing.endswith("\n") else "\n") + "\n# Added by the Agentic AI Framework\n"
                    + "\n".join(missing) + "\n")


def remote_url(path):
    proc = run(["git", "remote", "get-url", "origin"], path, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def web_url(remote):
    m = re.match(r"(?:https://github\.com/|git@github\.com:)(.+?)(?:\.git)?$", remote or "")
    return "https://github.com/" + m.group(1) if m else ""


def _init_repo(path, repo_name, public, no_remote, first_message, extra_ignore=""):
    if is_repo(path):
        print("Already a Git repository.")
    else:
        run(["git", "init", "-q"], path)
        run(["git", "checkout", "-q", "-b", "main"], path, check=False)
    ensure_gitignore(path, extra_ignore)
    run(["git", "add", "-A"], path)
    if run(["git", "status", "--porcelain"], path).stdout.strip():
        run(["git", "commit", "-q", "-m", first_message], path)
    if no_remote:
        return ""
    if remote_url(path):
        print("Remote already set: " + remote_url(path))
        return remote_url(path)
    vis = "--public" if public else "--private"
    run(["gh", "repo", "create", repo_name, vis, "--source", path, "--remote", "origin", "--push"], path)
    return remote_url(path)


def git_init(args):
    pdir = project_dir(args.name)
    repo = args.repo or args.name
    url = _init_repo(pdir, repo, args.public, args.no_remote,
                     "Start project %s\n\nCreated with the Agentic AI Framework." % args.name)
    write_json(os.path.join(pdir, "state", "git.json"), {
        "remote": url, "web": web_url(url), "decisions_committed": len(_decisions(pdir)),
        "auto_push": bool(url),
    })
    event(pdir, "git", "Git repository created" + (": " + web_url(url) if url else " (local only)"))
    print("Git ready" + (": " + web_url(url) if url else " (no remote)"))


def git_init_framework(args):
    url = _init_repo(ROOT, args.repo or "agentic-ai-framework", args.public, args.no_remote,
                     "Start the Agentic AI Framework", FRAMEWORK_GITIGNORE_EXTRA)
    print("Framework repository ready" + (": " + web_url(url) if url else " (no remote)"))


def git_commit_framework(args):
    """Commit and push changes to the framework itself (commands, aaf.py, hooks, templates).
    Projects are separate repositories and are not affected."""
    if not is_repo(ROOT):
        die("the framework is not a Git repository yet (run: aaf.py git init-framework)")
    ensure_gitignore(ROOT, FRAMEWORK_GITIGNORE_EXTRA)
    run(["git", "add", "-A"], ROOT)
    changed = run(["git", "diff", "--cached", "--name-status"], ROOT).stdout.strip().splitlines()
    if not changed:
        print("Nothing to commit in the framework.")
        return
    title = (args.title or "Update the framework").strip().splitlines()[0][:72]
    words = {"A": "added", "M": "changed", "D": "removed", "R": "renamed"}
    lines = []
    for l in changed:
        parts = l.split("\t")
        lines.append("- %s %s" % (words.get(parts[0][:1], parts[0]), parts[-1]))
    msg = title + "\n\nFiles:\n" + "\n".join(lines) + "\n"
    proc = subprocess.run(["git", "commit", "-q", "-F", "-"], cwd=ROOT, input=msg, text=True, capture_output=True)
    if proc.returncode != 0:
        die("git commit failed:\n" + (proc.stderr or proc.stdout))
    short = run(["git", "rev-parse", "--short", "HEAD"], ROOT).stdout.strip()
    print("Committed %s: %s (%d files)" % (short, title, len(changed)))
    if remote_url(ROOT):
        proc = run(["git", "push", "-q", "-u", "origin", "HEAD"], ROOT, check=False)
        if proc.returncode != 0:
            die("push failed:\n" + proc.stderr.strip())
        print("Pushed to " + (web_url(remote_url(ROOT)) or remote_url(ROOT)))


def _decisions(pdir):
    try:
        md = open(os.path.join(pdir, "state", "decisions.md")).read()
    except OSError:
        return []
    out = []
    for block in re.split(r"^## ", md, flags=re.M)[1:]:
        head, _, body = block.partition("\n")
        m = re.match(r"\d{4}-\d{2}-\d{2}:\s*(.*)", head.strip())
        out.append({"title": (m.group(1) if m else head).strip(), "body": body.strip()})
    return out


def _commit_message(pdir, title):
    st = read_json(os.path.join(pdir, "state", "status.json"), {})
    ck = read_json(os.path.join(pdir, "state", "checks.json"), {})
    rv = read_json(os.path.join(pdir, "state", "review.json"), {})
    gj = read_json(os.path.join(pdir, "state", "git.json"), {})
    subject = (title or st.get("task") or "Update").strip().splitlines()[0]
    if len(subject) > 72:
        subject = subject[:69].rstrip() + "..."
    body = []
    if st.get("note"):
        body.append(st["note"])
    new = _decisions(pdir)[gj.get("decisions_committed", 0):]
    if new:
        lines = ["Decisions:"]
        for d in new:
            lines.append("- " + d["title"])
            first = d["body"].split("\n\n")[0].replace("\n", " ").strip()
            if first:
                lines.append("  " + (first[:200] + ("..." if len(first) > 200 else "")))
        body.append("\n".join(lines))
    checks = ck.get("checks", [])
    n_ok = sum(1 for c in checks if c.get("passed"))
    if checks:
        body.append("Checks: %d of %d passed (%s)" % (n_ok, len(checks), ", ".join(c["name"] for c in checks)))
    started = st.get("task_started", "")
    fresh_review = rv and (not started or rv.get("at", "") >= started)
    if fresh_review:
        body.append("Independent review: %s. %s" % (rv["verdict"].upper(), rv.get("summary", "")))
    trailers = ["Agent-Project: " + os.path.basename(pdir)]
    if checks:
        trailers.append("Checks: %d/%d" % (n_ok, len(checks)))
    if fresh_review:
        trailers.append("Review: " + rv["verdict"])
    if st.get("iteration"):
        trailers.append("Agent-Attempts: %d" % st["iteration"])
    body.append("\n".join(trailers))
    return subject + "\n\n" + "\n\n".join(body) + "\n", len(_decisions(pdir))


def git_commit(args):
    pdir = project_dir(args.name)
    if not is_repo(pdir):
        die("project %s is not a Git repository yet (run: aaf.py git init %s)" % (args.name, args.name))
    ck = read_json(os.path.join(pdir, "state", "checks.json"), {})
    if not args.allow_failing and not ck.get("passed"):
        die("refusing to commit: the latest check run did not pass. Run `aaf.py check %s` first." % args.name)
    ensure_gitignore(pdir)
    update_readme(pdir)
    run(["git", "add", "-A"], pdir)
    if not run(["git", "status", "--porcelain"], pdir).stdout.strip():
        print("Nothing to commit.")
        return
    msg, n_dec = _commit_message(pdir, args.title)
    gj_path = os.path.join(pdir, "state", "git.json")
    gj = read_json(gj_path, {})
    gj["decisions_committed"] = n_dec
    write_json(gj_path, gj)
    run(["git", "add", "-A"], pdir)
    proc = subprocess.run(["git", "commit", "-q", "-F", "-"], cwd=pdir, input=msg, text=True, capture_output=True)
    if proc.returncode != 0:
        die("git commit failed:\n" + (proc.stderr or proc.stdout))
    short = run(["git", "rev-parse", "--short", "HEAD"], pdir).stdout.strip()
    event(pdir, "git", "Committed %s: %s" % (short, msg.splitlines()[0]), action="commit", commit=short)
    print("Committed %s: %s" % (short, msg.splitlines()[0]))
    if gj.get("auto_push", True) and remote_url(pdir):
        git_push(args)


def git_push(args):
    pdir = project_dir(args.name)
    if not remote_url(pdir):
        die("no remote. Create one with: aaf.py git init %s" % args.name)
    proc = run(["git", "push", "-q", "-u", "origin", "HEAD"], pdir, check=False)
    if proc.returncode != 0:
        event(pdir, "git", "Push failed")
        die("push failed (the remote may have newer commits; try `aaf.py git pull %s`):\n%s"
            % (args.name, proc.stderr.strip()))
    event(pdir, "git", "Pushed to GitHub")
    print("Pushed to " + (web_url(remote_url(pdir)) or remote_url(pdir)))


def git_pull(args):
    pdir = project_dir(args.name)
    if not remote_url(pdir):
        print("No remote; nothing to pull.")
        return
    dirty = run(["git", "status", "--porcelain", "--untracked-files=no"], pdir).stdout.strip()
    if dirty:
        die("uncommitted changes in tracked files; commit or restore them before pulling:\n" + dirty)
    proc = run(["git", "pull", "-q", "--ff-only"], pdir, check=False)
    if proc.returncode != 0:
        event(pdir, "git", "Pull failed: histories have diverged")
        die("pull failed; local and remote histories have diverged. A human should decide how to merge.\n"
            + proc.stderr.strip())
    event(pdir, "git", "Pulled from GitHub")
    print("Up to date with the remote.")


def git_info(args):
    pdir = project_dir(args.name)
    print(json.dumps(git_info_dict(pdir, fetch=args.fetch), indent=2))


def git_info_dict(pdir, fetch=False, limit=40):
    """Read-only summary of a project's repository, for agents and the dashboard."""
    if not is_repo(pdir):
        return {"repo": False}
    url = remote_url(pdir)
    if fetch and url:
        run(["git", "fetch", "-q"], pdir, check=False)
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], pdir, check=False).stdout.strip()
    ahead = behind = None
    ab = run(["git", "rev-list", "--left-right", "--count", "@{u}...HEAD"], pdir, check=False)
    if ab.returncode == 0:
        behind, ahead = (int(x) for x in ab.stdout.split())
    changed = [l[3:] for l in run(["git", "status", "--porcelain"], pdir).stdout.splitlines()]
    # Which commits GitHub already has (as of the last fetch or push): everything reachable
    # from the upstream branch. Correct for merges and long histories alike.
    on_remote = None
    if ab.returncode == 0:
        up = run(["git", "rev-list", "-n", "2000", "@{u}"], pdir, check=False)
        on_remote = set(up.stdout.split()) if up.returncode == 0 else None
    sep, end = "\x1f", "\x1e"
    log = run(["git", "log", "-n", str(limit), "--pretty=format:%H" + sep + "%h" + sep + "%aI" + sep + "%an"
               + sep + "%s" + sep + "%b" + end], pdir, check=False)
    commits = []
    for rec in log.stdout.split(end):
        parts = rec.strip("\n").split(sep)
        if len(parts) < 6:
            continue
        body = parts[5].strip()
        trailers = {}
        paras = body.split("\n\n")
        if paras and all(TRAILER_RE.match(l) for l in paras[-1].splitlines() if l):
            for l in paras[-1].splitlines():
                m = TRAILER_RE.match(l)
                if m:
                    trailers[m.group(1)] = m.group(2)
            body = "\n\n".join(paras[:-1]).strip()
        commits.append({"hash": parts[0], "short": parts[1], "date": parts[2], "author": parts[3],
                        "subject": parts[4], "body": body, "trailers": trailers,
                        "pushed": (parts[0] in on_remote) if on_remote is not None else None})
    return {"repo": True, "branch": branch, "remote": url, "web": web_url(url),
            "ahead": ahead, "behind": behind, "changed": changed[:50], "n_changed": len(changed),
            "commits": commits}


def cmd_git(args):
    fn = {"init": git_init, "init-framework": git_init_framework, "commit": git_commit,
          "commit-framework": git_commit_framework,
          "push": git_push, "pull": git_pull, "info": git_info,
          "files": lambda a: print(json.dumps(git_files_dict(project_dir(a.name)), indent=2))}[args.action]
    if args.action not in ("init-framework", "commit-framework") and not args.name:
        die("git %s needs a project name" % args.action)
    fn(args)


# ---------------------------------------------------------------- stats
#
# Derived views for the dashboard: per-task timelines and the agent's track record.
# Everything is computed from the event log, so older logs (text only) still work.

STATUS_RE = re.compile(r"^(Idle|Planning|Implementing|Checking|Reviewing|Fixing|Waiting|Done|Stuck)"
                       r"(?: \(iteration (\d+)\))?")
END_PHASES = {"done", "stuck", "waiting"}


def _parse_ts(ts):
    try:
        return dt.datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None


def _status_fields(e):
    phase, it = e.get("phase"), e.get("iteration")
    if phase is None:
        m = STATUS_RE.match(e.get("text", ""))
        if not m:
            return None, None
        phase, it = m.group(1).lower(), (int(m.group(2)) if m.group(2) else None)
    return phase, it


def _read_events(pdir):
    out = []
    try:
        with open(os.path.join(pdir, "state", "events.jsonl")) as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    return out


def task_stats(pdir):
    """One record per task: its phases over time, attempts, check runs, reviews, drafts."""
    tasks, cur = [], None

    def close_phase(at):
        if cur and cur["phases"] and cur["phases"][-1]["end"] is None:
            cur["phases"][-1]["end"] = at

    for e in _read_events(pdir):
        kind, ts = e.get("kind"), e.get("ts")
        if kind == "status" and e.get("action") != "restore":
            phase, it = _status_fields(e)
            if phase is None:
                continue
            title = e.get("task")
            if not title and "phase" not in e and phase == "planning" and e.get("text", "").startswith("Planning: "):
                title = e["text"].split(": ", 1)[1]
            if title:
                close_phase(ts)
                if cur and cur["end"] is None:
                    cur["end"] = ts
                cur = {"task": title, "start": ts, "end": None, "outcome": "running", "phases": [],
                       "attempts": 0, "check_runs": 0, "check_failures": 0, "reviews": [],
                       "drafts": 0, "decisions": 0, "commits": [], "times_stuck": 0}
                tasks.append(cur)
            if cur is None:
                continue
            close_phase(ts)
            if phase in END_PHASES:
                cur["outcome"], cur["end"] = phase, ts
                if phase == "stuck":
                    cur["times_stuck"] += 1
                continue
            if phase == "idle":
                continue
            if cur["outcome"] != "running":      # work resumed after an end (e.g. /draft continue)
                cur["outcome"], cur["end"] = "running", None
            cur["phases"].append({"phase": phase, "iteration": it, "start": ts, "end": None})
            if phase in ("implementing", "fixing") and it:
                cur["attempts"] = max(cur["attempts"], it)
        elif cur is not None:
            if kind == "check":
                cur["check_runs"] += 1
                passed = e.get("passed")
                if passed is None:
                    passed = e.get("text", "").startswith("Checks passed")
                if not passed:
                    cur["check_failures"] += 1
            elif kind == "review":
                cur["reviews"].append(e.get("verdict") or ("pass" if "PASS" in e.get("text", "") else "fail"))
            elif kind == "draft" and (e.get("action") == "save" or e.get("text", "").startswith("Draft saved")):
                cur["drafts"] += 1
            elif kind == "decision":
                cur["decisions"] += 1
            elif kind == "git" and (e.get("action") == "commit" or e.get("text", "").startswith("Committed")):
                cur["commits"].append(e.get("commit") or e["text"].split()[1].rstrip(":"))

    for t in tasks:
        a, b = _parse_ts(t["start"]), _parse_ts(t["end"])
        t["duration_s"] = int((b - a).total_seconds()) if a and b else None
        for ph in t["phases"]:
            a, b = _parse_ts(ph["start"]), _parse_ts(ph["end"])
            ph["duration_s"] = int((b - a).total_seconds()) if a and b else None
        impl = [p["iteration"] for p in t["phases"] if p["phase"] == "implementing" and p["iteration"]]
        t["first_try"] = bool(impl) and max(impl) == 1 and bool(t["reviews"]) and t["reviews"][0] == "pass"

    finished = [t for t in tasks if t["outcome"] in END_PHASES]
    reviews = [v for t in tasks for v in t["reviews"]]
    attempts = sorted(t["attempts"] for t in finished)
    summary = {
        "tasks": len(tasks),
        "finished": len(finished),
        "done": sum(1 for t in finished if t["outcome"] == "done"),
        "waiting": sum(1 for t in finished if t["outcome"] == "waiting"),
        "stuck": sum(1 for t in finished if t["outcome"] == "stuck"),
        "first_try": sum(1 for t in finished if t["first_try"]),
        "reviews": len(reviews),
        "review_fails": sum(1 for v in reviews if v == "fail"),
        "drafts": sum(t["drafts"] for t in tasks),
        "times_stuck": sum(t["times_stuck"] for t in tasks),
        "median_attempts": attempts[len(attempts) // 2] if attempts else None,
    }
    return {"summary": summary, "tasks": tasks}


def cmd_stats(args):
    out = task_stats(project_dir(args.name))
    out["estimate_accuracy"] = _calibration()
    print(json.dumps(out, indent=2))


def git_files_dict(pdir, limit_commits=500):
    """Per-file history for the change map: size, how often commits changed it, and when."""
    if not is_repo(pdir):
        return {"repo": False, "files": []}
    info = {}
    for f in run(["git", "ls-files"], pdir).stdout.splitlines():
        try:
            size = os.path.getsize(os.path.join(pdir, f))
        except OSError:
            size = 0
        info[f] = {"path": f, "bytes": size, "commits": 0, "lines_changed": 0,
                   "last_changed": None, "last_subject": None}
    log = run(["git", "log", "-n", str(limit_commits), "--numstat", "--format=\x1e%h\x1f%aI\x1f%s"],
              pdir, check=False).stdout
    for rec in log.split("\x1e")[1:]:
        head, _, rest = rec.partition("\n")
        parts = head.split("\x1f")
        if len(parts) < 3:
            continue
        date, subject = parts[1], parts[2]
        for line in rest.splitlines():
            cols = line.split("\t")
            if len(cols) != 3 or cols[2] not in info:
                continue
            d = info[cols[2]]
            d["commits"] += 1
            d["lines_changed"] += sum(int(c) for c in cols[:2] if c.isdigit())
            if d["last_changed"] is None:
                d["last_changed"], d["last_subject"] = date, subject
    return {"repo": True, "files": sorted(info.values(), key=lambda d: d["path"])}


# ---------------------------------------------------------------- plan and estimate
#
# During planning the agent records its plan as steps and ticks them off. The estimate
# combines that with every finished task recorded in the workspace, recomputed from the
# event logs on each call, so each new task improves it. Predictions are logged at
# milestones and later compared with what actually happened; that comparison widens or
# narrows future ranges (calibration).

TARGET_COVERAGE = (0.7, 0.9)    # share of past predictions whose range held the actual outcome
MIN_HISTORY = 3


def _plan_path(pdir):
    return os.path.join(pdir, "state", "plan.json")


def cmd_plan(args):
    pdir = project_dir(args.name)
    st = read_json(os.path.join(pdir, "state", "status.json"), {})
    path = _plan_path(pdir)
    plan = read_json(path, {})
    if args.add:
        if not plan.get("steps"):
            die("no plan yet; record one with --step")
        plan["steps"].extend({"text": t, "done_at": None, "added_later": True} for t in args.add)
        text = "Plan grew to %d steps" % len(plan["steps"])
    else:
        if not args.step:
            die("give the plan as --step TEXT (repeat for each step)")
        plan = {"task": st.get("task", ""), "created": now(),
                "steps": [{"text": t, "done_at": None} for t in args.step]}
        text = "Plan: %d steps" % len(plan["steps"])
    write_json(path, plan)
    event(pdir, "plan", text, n_steps=len(plan["steps"]))
    _log_estimate(pdir)
    print(text)


def cmd_step(args):
    pdir = project_dir(args.name)
    path = _plan_path(pdir)
    plan = read_json(path, {})
    steps = plan.get("steps", [])
    if not 1 <= args.number <= len(steps):
        die("step %d does not exist (the plan has %d steps)" % (args.number, len(steps)))
    steps[args.number - 1]["done_at"] = now()
    write_json(path, plan)
    done = sum(1 for s in steps if s["done_at"])
    event(pdir, "step", "Step %d of %d done: %s" % (args.number, len(steps), steps[args.number - 1]["text"]),
          step=args.number, n_steps=len(steps), n_done=done)
    _log_estimate(pdir)
    print("Step %d of %d done" % (args.number, len(steps)))


def _quantile(values, q):
    v = sorted(values)
    if not v:
        return None
    pos = (len(v) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def _history():
    """Finished tasks from every project, with total time and 'tail' time (review,
    fixing and final checks after the last implementing phase)."""
    out = []
    for name in sorted(os.listdir(PROJECTS)) if os.path.isdir(PROJECTS) else []:
        pdir = os.path.join(PROJECTS, name)
        if not os.path.isdir(os.path.join(pdir, "state")):
            continue
        for t in task_stats(pdir)["tasks"]:
            if t["outcome"] not in ("done", "waiting") or not t["duration_s"]:
                continue
            last_impl = max((i for i, p in enumerate(t["phases"]) if p["phase"] == "implementing"), default=-1)
            tail = sum(p["duration_s"] or 0 for p in t["phases"][last_impl + 1:]) if last_impl >= 0 else 0
            plan_phase = sum(p["duration_s"] or 0 for p in t["phases"] if p["phase"] == "planning")
            out.append({"project": name, "total": t["duration_s"], "tail": tail, "planning": plan_phase})
    return out


def _calibration(pdir_filter=None):
    """How often past logged ranges contained the real remaining time, and a scale
    factor for the width of new ranges."""
    hits = n = 0
    for name in os.listdir(PROJECTS) if os.path.isdir(PROJECTS) else []:
        pdir = os.path.join(PROJECTS, name)
        ends = {}
        for t in task_stats(pdir)["tasks"] if os.path.isdir(os.path.join(pdir, "state")) else []:
            if t["outcome"] in ("done", "waiting") and t["end"]:
                ends[t["start"]] = t["end"]
        try:
            with open(os.path.join(pdir, "state", "estimates.jsonl")) as f:
                rows = [json.loads(l) for l in f if l.strip()]
        except (OSError, ValueError):
            continue
        for r in rows:
            end = ends.get(r.get("task_start"))
            a, b = _parse_ts(r.get("ts")), _parse_ts(end)
            if not (a and b) or r.get("remaining_low_s") is None:
                continue
            actual = (b - a).total_seconds()
            n += 1
            hits += r["remaining_low_s"] <= actual <= r["remaining_high_s"]
    coverage = hits / n if n else None
    scale = 1.0
    if n >= 10:
        if coverage < TARGET_COVERAGE[0]:
            scale = min(2.5, 1.0 + (TARGET_COVERAGE[0] - coverage) * 3)
        elif coverage > TARGET_COVERAGE[1]:
            scale = max(0.6, 1.0 - (coverage - TARGET_COVERAGE[1]) * 2)
    return {"predictions_checked": n, "coverage": coverage, "width_scale": round(scale, 2)}


def estimate(pdir):
    st = read_json(os.path.join(pdir, "state", "status.json"), {})
    phase = st.get("phase", "idle")
    if phase not in ("planning", "implementing", "checking", "reviewing", "fixing"):
        return {"active": False, "phase": phase}
    start = _parse_ts(st.get("task_started"))
    now_t = dt.datetime.now().astimezone()
    elapsed = (now_t - start).total_seconds() if start else 0
    hist = _history()
    own = [h for h in hist if h["project"] == os.path.basename(pdir)]
    pool = own if len(own) >= 5 else hist
    plan = read_json(_plan_path(pdir), {})
    steps = plan.get("steps") if plan.get("task") == st.get("task") else None
    cal = _calibration()
    result = {"active": True, "phase": phase, "elapsed_s": int(elapsed), "history_tasks": len(pool),
              "history_scope": "this project" if pool is own else "all projects", "calibration": cal}

    if len(pool) < MIN_HISTORY:
        result.update({"basis": "too little history", "remaining_low_s": None, "remaining_high_s": None,
                       "progress_low": None, "progress_high": None})
    else:
        tails = [h["tail"] for h in pool]
        tail_lo, tail_hi = _quantile(tails, 0.2), _quantile(tails, 0.8)
        in_tail = phase in ("reviewing", "fixing") or (steps and all(s["done_at"] for s in steps))
        if steps and any(s["done_at"] for s in steps) and not in_tail:
            # Plan-based: time per finished step so far, extrapolated to the rest, plus the usual tail.
            done = [s for s in steps if s["done_at"]]
            plan_start = _parse_ts(plan.get("created")) or start
            per_step = max(30.0, (now_t - plan_start).total_seconds() / len(done))
            left = len(steps) - len(done)
            lo, hi = left * per_step * 0.7 + tail_lo, left * per_step * 1.6 + tail_hi
            basis = "plan steps (%d of %d done) and past review time" % (len(done), len(steps))
        elif in_tail:
            # Review and follow-up fixes: what is usually left of the tail, given time already spent in it.
            tail_spent = 0.0
            for p in reversed(next((t for t in task_stats(pdir)["tasks"][-1:]), {"phases": []})["phases"]):
                if p["phase"] == "implementing":
                    break
                b = _parse_ts(p["end"]) or now_t
                a = _parse_ts(p["start"])
                tail_spent += (b - a).total_seconds() if a else 0
            longer = [t - tail_spent for t in tails if t > tail_spent]
            lo = _quantile(longer, 0.2) if longer else 60
            hi = _quantile(longer, 0.8) if longer else max(300, tail_spent * 0.5)
            basis = "past review and fixing time"
        else:
            # Duration-based: among past tasks that ran longer than this one so far, how much was left.
            longer = [h["total"] - elapsed for h in pool if h["total"] > elapsed]
            if len(longer) >= 2:
                lo, hi = _quantile(longer, 0.2), _quantile(longer, 0.8)
                basis = "how long past tasks took"
            else:
                lo, hi = elapsed * 0.1, elapsed * 0.6
                basis = "already longer than almost every past task"
        mid, half = (lo + hi) / 2, (hi - lo) / 2 * cal["width_scale"]
        lo, hi = max(0.0, mid - half), mid + half
        result.update({"basis": basis, "remaining_low_s": int(lo), "remaining_high_s": int(hi),
                       "progress_low": round(elapsed / (elapsed + hi), 2) if elapsed + hi else None,
                       "progress_high": round(elapsed / (elapsed + lo), 2) if elapsed + lo else None})
    if steps:
        result["plan"] = {"steps": len(steps), "done": sum(1 for s in steps if s["done_at"]),
                          "current": next((s["text"] for s in steps if not s["done_at"]), None)}
    return result


def _log_estimate(pdir):
    """Record the estimate at a milestone so it can be checked against reality later."""
    try:
        e = estimate(pdir)
        if not e.get("active") or e.get("remaining_low_s") is None:
            return
        st = read_json(os.path.join(pdir, "state", "status.json"), {})
        append_jsonl(os.path.join(pdir, "state", "estimates.jsonl"), {
            "ts": now(), "task_start": st.get("task_started"), "phase": e["phase"],
            "elapsed_s": e["elapsed_s"], "remaining_low_s": e["remaining_low_s"],
            "remaining_high_s": e["remaining_high_s"], "basis": e["basis"]})
    except Exception:
        pass


def cmd_estimate(args):
    print(json.dumps(estimate(project_dir(args.name)), indent=2))


# ---------------------------------------------------------------- readme
#
# A project's README.md is written by the agent, but two sections are generated here
# so they can never go stale. They live between markers; anything outside the markers
# is left untouched:
#   <!-- aaf:history:start --> ... <!-- aaf:history:end -->   finished tasks, newest first
#   <!-- aaf:checks:start --> ... <!-- aaf:checks:end -->     the project's checks

README_SECTIONS = ("history", "checks")


def _readme_history(pdir, limit=25):
    tasks = [t for t in task_stats(pdir)["tasks"] if t["outcome"] in ("done", "waiting")]
    if not tasks:
        return "_No finished tasks yet._"
    lines = []
    for t in reversed(tasks[-limit:]):
        day = (t["end"] or t["start"] or "")[:10]
        notes = []
        if t["first_try"]:
            notes.append("first try")
        elif t["attempts"] > 1:
            notes.append("%d attempts" % t["attempts"])
        if t["reviews"]:
            notes.append("review " + ("passed" if t["reviews"][-1] == "pass" else "failed"))
        if t["outcome"] == "waiting":
            notes.append("a follow-up fix is waiting for a decision")
        lines.append("- %s: %s%s" % (day, t["task"], " (%s)" % ", ".join(notes) if notes else ""))
    return "\n".join(lines)


def _readme_checks(pdir):
    cfg = read_json(os.path.join(pdir, "project.json"), {})
    checks = cfg.get("checks", [])
    if not checks:
        return "_No checks defined yet._"
    out = ["Every change must pass these before it is committed:", ""]
    for c in checks:
        out.append("- **%s**: `%s`" % (c.get("name") or c["cmd"], c["cmd"]))
    return "\n".join(out)


def update_readme(pdir):
    """Regenerate the marked sections of README.md. Returns True if the file changed."""
    path = os.path.join(pdir, "README.md")
    if not os.path.exists(path):
        return False
    text = open(path).read()
    new = text
    for name, fn in (("history", _readme_history), ("checks", _readme_checks)):
        start, end = "<!-- aaf:%s:start -->" % name, "<!-- aaf:%s:end -->" % name
        i, j = new.find(start), new.find(end)
        if i == -1 or j == -1 or j < i:
            continue
        new = new[:i + len(start)] + "\n" + fn(pdir) + "\n" + new[j:]
    if new != text:
        with open(path, "w") as f:
            f.write(new)
        return True
    return False


def cmd_readme(args):
    pdir = project_dir(args.name)
    if not os.path.exists(os.path.join(pdir, "README.md")):
        die("projects/%s has no README.md yet" % args.name)
    print("README.md updated" if update_readme(pdir) else "README.md already up to date")


# ---------------------------------------------------------------- list

def cmd_list(_args):
    for p in sorted(os.listdir(PROJECTS)):
        pdir = os.path.join(PROJECTS, p)
        if not os.path.isdir(pdir):
            continue
        st = read_json(os.path.join(pdir, "state", "status.json"), {})
        print("%-24s %-12s %s" % (p, st.get("phase", "?"), st.get("task", "")))


def main():
    ap = argparse.ArgumentParser(prog="aaf", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("new"); s.add_argument("name"); s.add_argument("--description", default="")
    s.add_argument("--from", dest="src"); s.set_defaults(fn=cmd_new)

    s = sub.add_parser("check"); s.add_argument("name"); s.set_defaults(fn=cmd_check)

    s = sub.add_parser("status"); s.add_argument("name")
    s.add_argument("--phase", required=True, choices=PHASES)
    s.add_argument("--task"); s.add_argument("--iteration", type=int); s.add_argument("--note")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("decide"); s.add_argument("name"); s.add_argument("title"); s.add_argument("rationale")
    s.set_defaults(fn=cmd_decide)

    s = sub.add_parser("review"); s.add_argument("name")
    s.add_argument("--verdict", required=True, choices=["pass", "fail"])
    s.add_argument("--summary", required=True); s.add_argument("--file"); s.set_defaults(fn=cmd_review)

    s = sub.add_parser("snapshot"); s.add_argument("name"); s.add_argument("label"); s.set_defaults(fn=cmd_snapshot)
    s = sub.add_parser("restore"); s.add_argument("name"); s.add_argument("label"); s.set_defaults(fn=cmd_restore)

    s = sub.add_parser("draft"); s.add_argument("action", choices=["save", "apply", "discard", "list"])
    s.add_argument("name"); s.add_argument("id", nargs="?")
    s.add_argument("--issue"); s.add_argument("--summary"); s.add_argument("--iterations", type=int)
    s.add_argument("--notes"); s.set_defaults(fn=cmd_draft)

    s = sub.add_parser("git"); s.add_argument("action", choices=["init", "init-framework", "commit", "commit-framework", "push", "pull", "info", "files"])
    s.add_argument("name", nargs="?"); s.add_argument("--repo"); s.add_argument("--public", action="store_true")
    s.add_argument("--no-remote", action="store_true"); s.add_argument("--title")
    s.add_argument("--allow-failing", action="store_true"); s.add_argument("--fetch", action="store_true")
    s.set_defaults(fn=cmd_git)

    s = sub.add_parser("stats"); s.add_argument("name"); s.set_defaults(fn=cmd_stats)
    s = sub.add_parser("readme"); s.add_argument("name"); s.set_defaults(fn=cmd_readme)
    s = sub.add_parser("plan"); s.add_argument("name"); s.add_argument("--step", action="append")
    s.add_argument("--add", action="append"); s.set_defaults(fn=cmd_plan)
    s = sub.add_parser("step"); s.add_argument("name"); s.add_argument("number", type=int); s.set_defaults(fn=cmd_step)
    s = sub.add_parser("estimate"); s.add_argument("name"); s.set_defaults(fn=cmd_estimate)

    s = sub.add_parser("list"); s.set_defaults(fn=cmd_list)

    args = ap.parse_args()
    os.makedirs(PROJECTS, exist_ok=True)
    args.fn(args)


if __name__ == "__main__":
    main()
