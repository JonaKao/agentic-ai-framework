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
  python3 framework/aaf.py git push|pull <name>
  python3 framework/aaf.py git info <name> [--fetch]
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


def event(pdir, kind, text):
    append_jsonl(os.path.join(pdir, "state", "events.jsonl"), {"ts": now(), "kind": kind, "text": text})


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
    event(pdir, "check", "Checks %s: %d of %d passed" % ("passed" if all_passed else "failed", n_ok, len(results)))
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
    event(pdir, "status", text)
    print(text)


# ---------------------------------------------------------------- decide

def cmd_decide(args):
    pdir = project_dir(args.name)
    path = os.path.join(pdir, "state", "decisions.md")
    day = dt.date.today().isoformat()
    with open(path, "a") as f:
        f.write("\n## %s: %s\n\n%s\n" % (day, args.title.strip(), args.rationale.strip()))
    event(pdir, "decision", args.title.strip())
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
    event(pdir, "review", "Review %s: %s" % (args.verdict.upper(), args.summary))
    print("Recorded review: " + args.verdict.upper())



# ---------------------------------------------------------------- snapshots and drafts
#
# A snapshot is a copy of the project's working files (everything except state/).
# Drafts are snapshots of an unfinished fix attempt, kept until the human decides.

def _copy_tree(src, dst):
    """Copy project files from src to dst, skipping state/ and caches."""
    os.makedirs(dst, exist_ok=True)
    for entry in os.listdir(src):
        if entry in SKIP:
            continue
        s, d = os.path.join(src, entry), os.path.join(dst, entry)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*SKIP))
        else:
            shutil.copy2(s, d)


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
    if not os.path.isdir(src):
        die("nothing to restore at %s" % os.path.relpath(src, pdir))
    _clear_working_files(pdir)
    _copy_tree(src, pdir)


def cmd_snapshot(args):
    pdir = project_dir(args.name)
    _snapshot(pdir, args.label)
    event(pdir, "status", "Snapshot saved: %s" % args.label)
    print("Snapshot saved: state/snapshots/%s" % args.label)


def cmd_restore(args):
    pdir = project_dir(args.name)
    _restore_from(pdir, os.path.join(pdir, "state", "snapshots", _label(args.label)))
    event(pdir, "status", "Rolled back to snapshot %s" % args.label)
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
        event(pdir, "draft", "Draft saved: %s (%s)" % (args.issue, args.summary))
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
        event(pdir, "draft", "Continuing draft: %s" % meta["issue"])
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
        event(pdir, "draft", "Draft discarded, kept as known issue: %s" % meta["issue"])
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
    event(pdir, "git", "Committed %s: %s" % (short, msg.splitlines()[0]))
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
                        "subject": parts[4], "body": body, "trailers": trailers})
    return {"repo": True, "branch": branch, "remote": url, "web": web_url(url),
            "ahead": ahead, "behind": behind, "changed": changed[:50], "n_changed": len(changed),
            "commits": commits}


def cmd_git(args):
    fn = {"init": git_init, "init-framework": git_init_framework, "commit": git_commit,
          "push": git_push, "pull": git_pull, "info": git_info}[args.action]
    if args.action != "init-framework" and not args.name:
        die("git %s needs a project name" % args.action)
    fn(args)

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

    s = sub.add_parser("git"); s.add_argument("action", choices=["init", "init-framework", "commit", "push", "pull", "info"])
    s.add_argument("name", nargs="?"); s.add_argument("--repo"); s.add_argument("--public", action="store_true")
    s.add_argument("--no-remote", action="store_true"); s.add_argument("--title")
    s.add_argument("--allow-failing", action="store_true"); s.add_argument("--fetch", action="store_true")
    s.set_defaults(fn=cmd_git)

    s = sub.add_parser("list"); s.set_defaults(fn=cmd_list)

    args = ap.parse_args()
    os.makedirs(PROJECTS, exist_ok=True)
    args.fn(args)


if __name__ == "__main__":
    main()
