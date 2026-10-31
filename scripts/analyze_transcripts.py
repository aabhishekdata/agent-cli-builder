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

On Windows use `python` or `py` instead of `python3`.
"""
from __future__ import annotations  # keeps `str | None` hints working on Python 3.8/3.9

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict
from urllib.parse import unquote, urlparse

# ----------------------------------------------------------------------------
# Locating transcripts
# ----------------------------------------------------------------------------

def claude_code_project_dir(repo: str) -> str:
    """Claude Code stores transcripts at ~/.claude/projects/<encoded cwd>/*.jsonl,
    where every non-alphanumeric character of the absolute path becomes '-'
    (/home/me/my.repo -> -home-me-my-repo, C:\\Work\\My Repo -> C--Work-My-Repo)."""
    encoded = re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(repo))
    return os.path.join(os.path.expanduser("~"), ".claude", "projects", encoded)


def _legacy_claude_code_project_dir(repo: str) -> str:
    """Older guess (separator-only replacement); still checked so nothing regresses."""
    encoded = os.path.abspath(repo).replace(os.sep, "-")
    if not encoded.startswith("-"):
        encoded = "-" + encoded
    return os.path.join(os.path.expanduser("~"), ".claude", "projects", encoded)


def _vscode_user_dirs() -> list[str]:
    """VS Code (and Insiders) user-data dirs for this OS."""
    home = os.path.expanduser("~")
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA", os.path.join(home, "AppData", "Roaming"))
    elif sys.platform == "darwin":
        base = os.path.join(home, "Library", "Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME", os.path.join(home, ".config"))
    return [os.path.join(base, name, "User") for name in ("Code", "Code - Insiders")]


def _same_path(a: str, b: str) -> bool:
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


def vscode_chat_dirs(repo: str) -> list[str]:
    """GitHub Copilot Chat in VS Code saves sessions per workspace at
    <user dir>/workspaceStorage/<hash>/chatSessions/*.json(l). The hash folder's
    workspace.json holds the folder URI, which is how we match it to this repo.
    The file format is undocumented and changes between releases, so parsing
    is heuristic: treat the counts as a hint, not a measurement."""
    repo_abs = os.path.abspath(repo)
    found = []
    for user_dir in _vscode_user_dirs():
        for ws in glob.glob(os.path.join(user_dir, "workspaceStorage", "*", "workspace.json")):
            try:
                with open(ws, encoding="utf-8") as fh:
                    uri = json.load(fh).get("folder", "")
            except (OSError, ValueError, AttributeError):
                continue
            parsed = urlparse(uri)
            if parsed.scheme != "file":
                continue
            path = unquote(parsed.path)
            if re.match(r"^/[A-Za-z]:", path):      # file:///c%3A/... -> c:/...
                path = path[1:]
            chat = os.path.join(os.path.dirname(ws), "chatSessions")
            if _same_path(path, repo_abs) and os.path.isdir(chat):
                found.append(chat)
    return found


def find_transcripts(repo: str, explicit_dir: str | None) -> list[str]:
    candidates = []
    if explicit_dir:
        for ext in ("jsonl", "json", "md", "txt", "log"):
            candidates += glob.glob(os.path.join(explicit_dir, "**", f"*.{ext}"), recursive=True)
        return sorted(set(candidates))

    for cc in (claude_code_project_dir(repo), _legacy_claude_code_project_dir(repo)):
        candidates += glob.glob(os.path.join(cc, "*.jsonl"))

    for chat in vscode_chat_dirs(repo):
        candidates += glob.glob(os.path.join(chat, "*.json")) + glob.glob(os.path.join(chat, "*.jsonl"))

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


_PATH_KEYS = ("file_path", "filePath", "path", "file", "uri")
_CMD_KEYS = ("command", "cmd", "commandLine", "script")
_PAT_KEYS = ("pattern", "query", "regex", "searchString", "glob")
_NAME_KEYS = ("name", "toolName", "tool_name", "tool", "function")
_ARG_KEYS = ("input", "arguments", "args", "parameters", "params")


def _generic_tool_calls(obj, depth=0):
    """Walk any JSON event and yield (tool_name, args_dict) for anything that
    looks like a tool call. Format-agnostic fallback for non-Claude agents
    (GitHub Copilot CLI events.jsonl, Cursor, Codex, exported logs...)."""
    if depth > 8:
        return
    if isinstance(obj, dict):
        name = next((obj[k] for k in _NAME_KEYS if isinstance(obj.get(k), str)), None)
        args = next((obj[k] for k in _ARG_KEYS if isinstance(obj.get(k), (dict, str))), None)
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = None
        if name and isinstance(args, dict):
            yield name, args
        for v in obj.values():
            yield from _generic_tool_calls(v, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            yield from _generic_tool_calls(v, depth + 1)


def _classify(name: str, inp: dict, repo: str, out: dict) -> bool:
    """Route one tool call into reads/searches/commands. Returns True if used."""
    lname = name.lower()
    cmd = next((inp[k] for k in _CMD_KEYS if isinstance(inp.get(k), str)), None)
    pat = next((inp[k] for k in _PAT_KEYS if isinstance(inp.get(k), str)), None)
    path = next((inp[k] for k in _PATH_KEYS if isinstance(inp.get(k), str)), None)
    if cmd and (name in SHELL_TOOLS or any(k in lname for k in ("bash", "shell", "terminal", "command", "powershell", "exec"))):
        out["commands"].append(norm_cmd(cmd)); return True
    if pat and (name in SEARCH_TOOLS or any(k in lname for k in ("grep", "glob", "search", "find"))):
        out["searches"].append(f"{name}: {norm_cmd(pat)}"); return True
    if path and (name in READ_TOOLS or any(k in lname for k in ("read", "view", "open", "cat"))):
        out["reads"].append(norm_path(path, repo)); return True
    if cmd:
        out["commands"].append(norm_cmd(cmd)); return True
    return False


def _maybe_question(text, out):
    if not isinstance(text, str):
        return
    q = text.strip()
    if 8 < len(q) < 300 and not q.startswith("<") and (
        "?" in q or q.lower().startswith(("how", "what", "where", "which", "why", "does", "is ", "can "))
    ):
        out["questions"].append(norm_cmd(q))


def _extract_claude_shape(ev, repo: str, out: dict) -> bool:
    """Claude Code transcript shape: {type, message:{role, content:[{type:tool_use,...}]}}."""
    msg = ev.get("message", ev) if isinstance(ev, dict) else None
    if not isinstance(msg, dict):
        return False
    role = msg.get("role") or ev.get("type")
    content = msg.get("content")
    if role == "user" and isinstance(content, str):
        _maybe_question(content, out)
    if not isinstance(content, list):
        return False
    used = False
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        used = _classify(block.get("name", ""), block.get("input", {}) or {}, repo, out) or used
    return used


def _extract_generic(ev, repo: str, out: dict):
    """Any other agent's JSON: walk for tool-call-like dicts and user text."""
    for name, args in _generic_tool_calls(ev):
        _classify(name, args, repo, out)
    if isinstance(ev, dict):
        role = str(ev.get("role") or ev.get("type") or ev.get("kind") or "").lower()
        data = ev.get("data") if isinstance(ev.get("data"), dict) else {}
        txt = ev.get("content") or ev.get("text") or ev.get("prompt") or data.get("content") or data.get("text")
        if "user" in role:
            _maybe_question(txt, out)
        _vscode_questions(ev, out)


def _vscode_questions(obj, out, depth=0):
    """VS Code chat sessions keep each turn in a `requests` list with the user's
    prompt at request.message.text (no role field). Shape unverified across
    releases; harmless if absent."""
    if depth > 4:
        return
    if isinstance(obj, dict):
        reqs = obj.get("requests")
        if isinstance(reqs, list):
            for r in reqs:
                msg = r.get("message") if isinstance(r, dict) else None
                if isinstance(msg, dict):
                    _maybe_question(msg.get("text"), out)
            return
        for v in obj.values():
            if isinstance(v, (dict, list)):
                _vscode_questions(v, out, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            _vscode_questions(v, out, depth + 1)


def extract_from_json_transcript(path: str, repo: str, out: dict):
    """Pull tool calls and user questions out of a transcript. Tries the Claude
    Code shape first, then a format-agnostic walk (Copilot CLI events.jsonl etc.)."""
    for ev in iter_json_events(path):
        if not _extract_claude_shape(ev, repo, out):
            _extract_generic(ev, repo, out)


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
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")   # Windows consoles (cp1252) can't print every character

    files = find_transcripts(args.repo, args.transcripts)
    if not files:
        msg = {"error": "no transcripts found",
               "looked_in": [claude_code_project_dir(args.repo), "VS Code workspaceStorage/*/chatSessions",
                             "~/.copilot/session-state"] + ([args.transcripts] if args.transcripts else []),
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
    # Transcripts found but almost nothing extracted: likely an unknown format
    # (VS Code chat sessions often store tool calls without their arguments).
    extracted = sum(len(d[k]) for d in per_session.values() for k in ("commands", "reads", "searches"))
    low_yield = extracted < 3 * max(1, len(files))
    hint = ("transcripts found but few tool calls extracted; the format may not be "
            "parseable. Use the manual probe (references/manual-probe.md) and treat "
            "this report as a hint only.") if low_yield else None

    if args.json:
        print(json.dumps({"files": len(files), "sessions": len(per_session), "min_sessions": min_sessions,
                          "report": report, "suggested_subcommands": ideas, "warning": hint}, indent=2))
    else:
        if hint:
            print(f"WARNING: {hint}\n")
        if min_sessions == 1:
            print(f"(only {len(per_session)} usable session(s) found - showing within-session repeats)\n")
        print_text(report, ideas, len(per_session), len(files))


if __name__ == "__main__":
    main()
