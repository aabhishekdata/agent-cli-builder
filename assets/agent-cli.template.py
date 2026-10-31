#!/usr/bin/env python3
"""
agent-cli — repo orientation for coding agents. Written for agents, not humans.

Terse by default. Every subcommand accepts --json. Stdlib only.
Regenerate / extend: see the "agent-cli" section in AGENTS.md (or CLAUDE.md).

    ./bin/agent-cli            # overview of what's here
    ./bin/agent-cli <cmd> --help
    ./bin/agent-cli doctor     # self-check: is this CLI still telling the truth?

PLACEHOLDERS — the agent generating this file should replace every TODO
with facts discovered from the repo and the repeated-items report. Do not
ship a subcommand whose answer is hard-coded if it can be computed from the
repo at run time; computed answers do not drift.
"""
import argparse
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI_VERSION = "0.1.0"           # bump when subcommands change
GENERATED_FROM = "TODO: date + commit sha this CLI was generated against"


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------

def sh(cmd: str, cwd: str = ROOT, timeout: int = 60) -> str:
    """Run a shell command, return stdout (stripped). Never raises on non-zero."""
    try:
        r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or r.stderr).strip()
    except subprocess.TimeoutExpired:
        return f"<timeout after {timeout}s>"


def emit(data, as_json: bool, text_fn=None):
    """Single output path: JSON for machines, terse text otherwise."""
    if as_json:
        print(json.dumps(data, indent=None, separators=(",", ":"), default=str))
    elif text_fn:
        print(text_fn(data))
    elif isinstance(data, dict):
        for k, v in data.items():
            print(f"{k}: {v}")
    else:
        print(data)


def read_if_exists(rel: str, max_lines: int = 0) -> str | None:
    p = os.path.join(ROOT, rel)
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines()
    return "\n".join(lines[:max_lines] if max_lines else lines)


# ----------------------------------------------------------------------------
# subcommands — add one function per repeated question. Keep each < 40 lines.
# ----------------------------------------------------------------------------

def cmd_info(args):
    """Stack, entry points, scripts, how to run/test/build. Replaces re-reading manifests."""
    data = {
        "root": ROOT,
        "stack": [],            # TODO e.g. ["python 3.11", "fastapi", "postgres"]
        "entry_points": [],     # TODO e.g. ["src/app/main.py"]
        "run": "TODO",          # TODO the one command that starts it
        "test": "TODO",         # TODO the one command that tests it
        "build": "TODO",
        "lint": "TODO",
    }
    # Example of a computed (non-drifting) fact: scripts from package.json if present.
    pkg = read_if_exists("package.json")
    if pkg:
        try:
            data["npm_scripts"] = json.loads(pkg).get("scripts", {})
        except json.JSONDecodeError:
            pass
    emit(data, args.json)


def cmd_map(args):
    """Top-level layout with one-line purpose per directory. Replaces ls/tree walks."""
    # TODO: fill `purpose` from what you learned; keep the listing itself computed.
    purpose = {
        # "src": "application code",
        # "tests": "pytest suite; fixtures in tests/fixtures",
    }
    entries = []
    for name in sorted(os.listdir(ROOT)):
        if name.startswith(".") or name in ("node_modules", "__pycache__", "venv", ".venv", "dist", "build"):
            continue
        p = os.path.join(ROOT, name)
        entries.append({"path": name + ("/" if os.path.isdir(p) else ""),
                        "purpose": purpose.get(name, "")})
    emit(entries, args.json, lambda d: "\n".join(f"{e['path']:<28} {e['purpose']}" for e in d))


def cmd_status(args):
    """Git orientation in one call: branch, dirty files, last commits."""
    data = {
        "branch": sh("git rev-parse --abbrev-ref HEAD"),
        "dirty": sh("git status --porcelain").splitlines(),
        "recent": sh("git log --oneline -8").splitlines(),
    }
    emit(data, args.json)


def cmd_where(args):
    """Find where a symbol/term lives. Knows which dirs matter and which to skip."""
    term = args.term
    exclude = "--glob '!node_modules' --glob '!dist' --glob '!*.lock'"   # TODO tune
    if sh("command -v rg"):
        out = sh(f"rg -n --no-heading {exclude} {json.dumps(term)} .", timeout=30)
    else:
        out = sh(f"grep -rn --exclude-dir=node_modules --exclude-dir=.git {json.dumps(term)} .", timeout=30)
    hits = [l for l in out.splitlines() if l][: args.limit]
    emit({"term": term, "hits": hits}, args.json, lambda d: "\n".join(d["hits"]) or "(no hits)")


def cmd_test(args):
    """Run the test suite the way this repo expects. Replaces guessing flags."""
    cmd = "TODO e.g. python -m pytest -q"  # TODO
    if args.only:
        cmd += f" {args.only}"
    out = sh(cmd, timeout=600)
    tail = out.splitlines()[-25:]
    emit({"cmd": cmd, "tail": tail}, args.json, lambda d: "\n".join(d["tail"]))


def cmd_orient(args):
    """20-line digest of README / ARCHITECTURE / AGENTS. Replaces 6 file reads."""
    # TODO: write the digest by hand once, then keep it short. Prefer pointing
    # at `agent-cli info` / `map` for anything that can be computed.
    digest = """\
TODO: what this repo is, in 2 lines.
TODO: the 3 places work usually happens.
TODO: the 2 traps (env vars, generated files, slow tests...).
Commands: agent-cli info | map | status | where <term> | test [path] | doctor
"""
    emit({"digest": digest}, args.json, lambda d: d["digest"])


def cmd_faq(args):
    """Answers to questions asked repeatedly. Each answer should name its source file."""
    faq = {
        # "how do I run migrations": {"answer": "TODO", "source": "docs/db.md"},
    }
    if args.question:
        q = args.question.lower()
        hits = {k: v for k, v in faq.items() if q in k.lower()}
        emit(hits or {"answer": "not in faq; try `agent-cli where`"}, args.json)
    else:
        emit(faq, args.json)


def cmd_doctor(args):
    """Self-check against the repo so the CLI cannot drift silently.

    A command that has drifted from the repo is worse than six file reads,
    because it still looks authoritative. Every hard-coded fact above should
    have a probe here. Exit 1 on any failure so agents notice.
    """
    checks = []

    def check(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    # TODO: one probe per hard-coded fact. Examples:
    # check("entry point exists", os.path.exists(os.path.join(ROOT, "src/app/main.py")))
    # check("test cmd resolves", sh("python -m pytest --version"))
    check("no TODO placeholders left", "TODO" not in open(__file__, encoding="utf-8").read().split("def cmd_doctor")[0].replace('"""', "")
          or args.allow_todo, "run with --allow-todo while scaffolding")
    check("generated-from sha recorded", "TODO" not in GENERATED_FROM, GENERATED_FROM)
    head = sh("git rev-parse --short HEAD 2>/dev/null")
    check("git reachable", bool(head) and not head.startswith("fatal"), head or "no commits yet")

    failed = [c for c in checks if not c["ok"]]
    emit({"version": CLI_VERSION, "generated_from": GENERATED_FROM, "checks": checks, "failed": len(failed)},
         args.json, lambda d: "\n".join(f"{'OK ' if c['ok'] else 'FAIL'} {c['check']}  {c['detail']}" for c in d["checks"]))
    sys.exit(1 if failed else 0)


# ----------------------------------------------------------------------------
# wiring
# ----------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(prog="agent-cli", description=__doc__.split("\n\n")[0])
    ap.add_argument("--version", action="version", version=f"agent-cli {CLI_VERSION} (from {GENERATED_FROM})")
    sub = ap.add_subparsers(dest="cmd")

    def add(name, fn, help_, extra=None):
        p = sub.add_parser(name, help=help_, description=fn.__doc__)
        p.add_argument("--json", action="store_true", help="machine-readable output")
        if extra:
            extra(p)
        p.set_defaults(fn=fn)
        return p

    add("info", cmd_info, "stack, entry points, run/test/build commands")
    add("map", cmd_map, "top-level layout with purpose per directory")
    add("status", cmd_status, "branch, dirty files, recent commits")
    add("where", cmd_where, "locate a term/symbol", lambda p: (p.add_argument("term"), p.add_argument("--limit", type=int, default=40)))
    add("test", cmd_test, "run tests the repo's way", lambda p: p.add_argument("--only", help="path or -k expression"))
    add("orient", cmd_orient, "20-line digest for a cold start")
    add("faq", cmd_faq, "answers to repeatedly asked questions", lambda p: p.add_argument("question", nargs="?"))
    add("doctor", cmd_doctor, "validate this CLI against the repo", lambda p: p.add_argument("--allow-todo", action="store_true"))

    args = ap.parse_args(argv)
    if not args.cmd:
        # Default: the cheapest possible orientation.
        print("agent-cli: info | map | status | where <term> | test | orient | faq | doctor   (--json on all)")
        return 0
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
