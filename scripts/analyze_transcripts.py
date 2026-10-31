#!/usr/bin/env python3
"""
analyze_transcripts.py — find what the agent keeps re-doing across sessions.

Reads coding-agent session transcripts (Claude Code JSONL by default) and
reports the commands, file reads, searches and questions that recur across
sessions. Those recurring items are the candidates for ./bin/agent-cli
subcommands.

Stdlib only. No new dependencies.

Usage:
  python3 analyze_transcripts.py                      # auto-detect for cwd
  python3 analyze_transcripts.py --repo /path/to/repo
  python3 analyze_transcripts.py --transcripts DIR    # any *.jsonl / *.json / *.md / *.txt
  python3 analyze_transcripts.py --json               # machine-readable
  python3 analyze_transcripts.py --min-sessions 2 --top 25
"""
import argparse
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict

# ----------------------------------------------------------------------------
# Locating transcripts
# ----------------------------------------------------------------------------

def claude_code_project_dir(repo: str) -> str:
    """Claude Code stores transcripts at ~/.claude/projects/<cwd with / -> ->/*.jsonl"""
    encoded = os.path.abspath(repo).replace(os.sep, "-")
    if not encoded.startswith("-"):
        encoded = "-" + encoded
    return os.path.join(os.path.expanduser("~"), ".claude", "projects", encoded)


def find_transcripts(repo: str, explicit_dir: str | None) -> list[str]:
    candidates = []
    if explicit_dir:
        for ext in ("jsonl", "json", "md", "txt", "log"):
            candidates += glob.glob(os.path.join(explicit_dir, "**", f"*.{ext}"), recursive=True)
        return sorted(set(candidates))

    cc = claude_code_project_dir(repo)
    candidates += glob.glob(os.path.join(cc, "*.jsonl"))

    # Common alternative locations other agents / teams use. Harmless if absent.
    for p in (
        os.path.join(repo, ".claude", "sessions"),
        os.path.join(repo, ".agent", "sessions"),
        os.path.join(repo, "sessions"),
        os.path.join(os.path.expanduser("~"), ".copilot", "session-state"),
        os.path.join(os.path.expanduser("~"), ".copilot", "sessions"),
    ):
        if os.path.isdir(p):
            for ext in ("jsonl", "json", "md", "txt", "log"):
                candidates += glob.glob(os.path.join(p, "**", f"*.{ext}"), recursive=True)
    return sorted(set(candidates))


# ----------------------------------------------------------------------------
# Normalisation — collapse near-duplicates so counts are meaningful
# ----------------------------------------------------------------------------

_HASHLIKE = re.compile(r"\b[0-9a-f]{7,40}\b")
_NUMS = re.compile(r"\b\d{2,}\b")
_WS = re.compile(r"\s+")


def norm_cmd(cmd: str) -> str:
    cmd = cmd.strip().split("\n")[0]          # first line of multi-line commands
    cmd = _HASHLIKE.sub("<sha>", cmd)
    cmd = _NUMS.sub("<n>", cmd)
    cmd = _WS.sub(" ", cmd)
    return cmd[:160]


def norm_path(p: str, repo: str) -> str:
    p = os.path.abspath(p) if os.path.isabs(p) else p
    try:
        rel = os.path.relpath(p, os.path.abspath(repo))
        if not rel.startswith(".."):
            return rel
    except ValueError:
        pass
    return p


# ----------------------------------------------------------------------------
# Extraction
# ----------------------------------------------------------------------------

READ_TOOLS = {"Read", "read_file", "view_file", "view", "cat", "open_file"}
SEARCH_TOOLS = {"Grep", "Glob", "grep", "glob", "search", "search_files", "find_files", "ripgrep", "code_search"}
SHELL_TOOLS = {"Bash", "bash", "shell", "run_command", "execute_command", "run_in_terminal", "powershell"}


def iter_json_events(path: str):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        if path.endswith(".jsonl"):
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
        else:
            try:
                data = json.load(fh)
            except json.JSONDecodeError:
                return
            if isinstance(data, list):
                yield from data
            elif isinstance(data, dict):
                for key in ("messages", "events", "turns", "history"):
                    if isinstance(data.get(key), list):
                        yield from data[key]
                        return
                yield data


def extract_from_json_transcript(path: str, repo: str, out: dict):
    """Pull tool calls and user questions out of a Claude-Code-style transcript."""
    for ev in iter_json_events(path):
        msg = ev.get("message", ev) if isinstance(ev, dict) else None
        if not isinstance(msg, dict):
            continue
        role = msg.get("role") or ev.get("type")
        content = msg.get("content")

        # User questions (plain text, not injected system reminders)
        if role == "user" and isinstance(content, str) and not content.lstrip().startswith("<"):
            q = content.strip()
            if 8 < len(q) < 300 and ("?" in q or q.lower().startswith(("how", "what", "where", "which", "why", "does", "is ", "can "))):
                out["questions"].append(norm_cmd(q))

        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = block.get("name", "")
            inp = block.get("input", {}) or {}
            if name in READ_TOOLS or name.endswith("read_file"):
                p = inp.get("file_path") or inp.get("path") or inp.get("filePath")
                if p:
                    out["reads"].append(norm_path(p, repo))
            elif name in SEARCH_TOOLS:
                pat = inp.get("pattern") or inp.get("query") or inp.get("regex")
                if pat:
                    out["searches"].append(f"{name}: {norm_cmd(str(pat))}")
            elif name in SHELL_TOOLS or name.endswith("bash") or "command" in inp:
                c = inp.get("command") or inp.get("cmd")
                if c:
                    out["commands"].append(norm_cmd(str(c)))


_MD_CMD = re.compile(r"^\s*(?:\$ |> |`)([a-zA-Z][^\n`]{3,150})`?", re.M)
_MD_READ = re.compile(r"(?:Read|Reading|cat|opened?)\s+[`\"']?([\w./\\-]+\.[a-zA-Z0-9]{1,6})", re.I)


def extract_from_text_transcript(path: str, repo: str, out: dict):
    """Best-effort for markdown / plain-text transcripts from other agents."""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    for m in _MD_CMD.finditer(text):
        out["commands"].append(norm_cmd(m.group(1)))
    for m in _MD_READ.finditer(text):
        out["reads"].append(norm_path(m.group(1), repo))
    for line in text.splitlines():
        s = line.strip()
        if s.endswith("?") and 8 < len(s) < 300:
            out["questions"].append(norm_cmd(s))


# ----------------------------------------------------------------------------
# Aggregation
# ----------------------------------------------------------------------------

def aggregate(per_session: dict[str, dict], min_sessions: int, top: int):
    """Count in how many *sessions* each item appears (cross-session repetition
    is the signal; repetition within one session is often legitimate)."""
    report = {}
    for kind in ("commands", "reads", "searches", "questions"):
        session_count = Counter()
        total_count = Counter()
        for sess, data in per_session.items():
            items = data[kind]
            total_count.update(items)
            session_count.update(set(items))
        rows = [
            {"item": item, "sessions": s, "total": total_count[item]}
            for item, s in session_count.items()
            if s >= min_sessions
        ]
        rows.sort(key=lambda r: (-r["sessions"], -r["total"], r["item"]))
        report[kind] = rows[:top]
    return report


def suggest_subcommands(report: dict) -> list[dict]:
    """Rough grouping of repeated items into CLI subcommand ideas."""
    ideas = []
    cmds = [r["item"] for r in report["commands"]]
    reads = [r["item"] for r in report["reads"]]

    def has(pred):
        return [c for c in cmds if pred(c)]

    if has(lambda c: c.startswith(("ls", "tree", "find ", "fd ")) or "wc -l" in c):
        ideas.append({"name": "map", "why": "repeated directory listings / tree walks", "replaces": has(lambda c: c.startswith(("ls", "tree", "find ", "fd ")))[:5]})
    if has(lambda c: c.startswith("git ")):
        ideas.append({"name": "status", "why": "repeated git status/log/diff orientation", "replaces": has(lambda c: c.startswith("git "))[:5]})
    if has(lambda c: any(k in c for k in ("pytest", "npm test", "go test", "cargo test", "mvn ", "gradle", "jest", "vitest"))):
        ideas.append({"name": "test", "why": "repeated test invocations with the same flags", "replaces": has(lambda c: any(k in c for k in ("pytest", "npm test", "go test", "cargo test", "mvn ", "gradle", "jest", "vitest")))[:5]})
    if has(lambda c: any(k in c for k in ("npm run build", "make", "tsc", "cargo build", "go build", "docker build"))):
        ideas.append({"name": "build", "why": "repeated build commands", "replaces": has(lambda c: any(k in c for k in ("npm run build", "make", "tsc", "cargo build", "go build", "docker build")))[:5]})
    if has(lambda c: any(k in c for k in ("grep", "rg ", "ag "))) or report["searches"]:
        ideas.append({"name": "where", "why": "repeated symbol/text searches — expose a `where <term>` that knows the repo's hot paths", "replaces": [r["item"] for r in report["searches"]][:5]})
    config_reads = [p for p in reads if os.path.basename(p).lower() in (
        "package.json", "pyproject.toml", "setup.py", "requirements.txt", "cargo.toml", "go.mod", "pom.xml",
        "build.gradle", "makefile", "dockerfile", "docker-compose.yml", ".env.example", "tsconfig.json")]
    if config_reads:
        ideas.append({"name": "info", "why": "re-reading manifests/config to learn stack, scripts, deps, entry points", "replaces": config_reads[:8]})
    doc_reads = [p for p in reads if os.path.basename(p).lower() in ("readme.md", "claude.md", "agents.md", "contributing.md", "architecture.md")]
    if doc_reads:
        ideas.append({"name": "orient", "why": "re-reading orientation docs every session — a 20-line digest beats 6 file reads", "replaces": doc_reads[:8]})
    if report["questions"]:
        ideas.append({"name": "faq", "why": "questions the user kept asking — answer them from one place", "replaces": [r["item"] for r in report["questions"]][:6]})
    return ideas


# ----------------------------------------------------------------------------
# Output
# ----------------------------------------------------------------------------

def print_text(report, ideas, n_sessions, n_files):
    print(f"# Repeated-items report  ({n_files} transcript files, {n_sessions} sessions)\n")
    for kind, title in (("commands", "Commands"), ("reads", "File reads"), ("searches", "Searches"), ("questions", "Questions")):
        rows = report[kind]
        print(f"## {title} repeated across sessions ({len(rows)})")
        if not rows:
            print("  (none above threshold)")
        for r in rows:
            print(f"  [{r['sessions']:>2} sess / {r['total']:>3} total]  {r['item']}")
        print()
    print("## Suggested agent-cli subcommands")
    if not ideas:
        print("  (no obvious clusters — build from the lists above and your own probing)")
    for i in ideas:
        print(f"  agent-cli {i['name']:<8} — {i['why']}")
        for x in i["replaces"]:
            print(f"      ↳ {x}")
    print()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=os.getcwd(), help="repo root (default: cwd)")
    ap.add_argument("--transcripts", help="directory of transcripts (overrides auto-detect)")
    ap.add_argument("--min-sessions", type=int, default=2, help="repeated in at least N sessions (default 2)")
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    files = find_transcripts(args.repo, args.transcripts)
    if not files:
        msg = {"error": "no transcripts found",
               "looked_in": [claude_code_project_dir(args.repo)] + ([args.transcripts] if args.transcripts else []),
               "hint": "pass --transcripts DIR, or run the manual probe in SKILL.md"}
        print(json.dumps(msg, indent=2) if args.json else f"No transcripts found. Looked in: {msg['looked_in']}\nHint: {msg['hint']}", file=sys.stderr)
        sys.exit(2)

    per_session = {}
    for f in files:
        out = {"commands": [], "reads": [], "searches": [], "questions": []}
        if f.endswith((".jsonl", ".json")):
            extract_from_json_transcript(f, args.repo, out)
        else:
            extract_from_text_transcript(f, args.repo, out)
        if any(out.values()):
            per_session[f] = out

    # With a single session, cross-session repetition is undefined; fall back to within-session.
    min_sessions = args.min_sessions if len(per_session) >= args.min_sessions else 1
    report = aggregate(per_session, min_sessions, args.top)
    if min_sessions == 1:
        # within-session repeats only: require total >= 2
        for k in report:
            report[k] = [r for r in report[k] if r["total"] >= 2]
    ideas = suggest_subcommands(report)

    if args.json:
        print(json.dumps({"files": len(files), "sessions": len(per_session), "min_sessions": min_sessions,
                          "report": report, "suggested_subcommands": ideas}, indent=2))
    else:
        if min_sessions == 1:
            print("(only one usable session found — showing within-session repeats)\n")
        print_text(report, ideas, len(per_session), len(files))


if __name__ == "__main__":
    main()
