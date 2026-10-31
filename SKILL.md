---
name: agent-cli-builder
description: Build (or refresh) a repo-local `./bin/agent-cli` — a tiny, dependency-free CLI that answers the questions a coding agent keeps re-asking at the start of every session (stack, layout, how to run/test, where things live), so orientation drops from many file reads and ~40k tokens to one command and ~2k tokens. Use this skill whenever the user says "agent-cli", "build a CLI for the agent", "stop re-reading files every session", "speed up session startup", "reduce orientation tokens", "Lemieux CLI trick", or asks to refresh/regenerate an existing agent-cli. Also use it when a daily or weekly scheduled task says to re-run the agent-cli analysis.
---

# agent-cli builder

## What this is and why it works

Every fresh session, an agent re-orients: reads the README, the manifest, lists
directories, greps for the entry point, runs `git status`, guesses the test command.
Across sessions that is the same ~6 reads and ~40k tokens, every time, before any
real work starts.

The fix (from Jean-Michel Lemieux): mine the session transcripts for what gets
repeated, then collapse each repeated thing into a subcommand of one small CLI the
agent can call first. Output is terse and written for the agent, not a human.
`--json` on everything. No new dependencies. Then tell the agent, in its
instructions file, to prefer the CLI over re-reading or guessing.

The one real risk, raised in the thread: a CLI that has drifted from the repo is
*worse* than six file reads because it still looks authoritative. So the CLI must
(a) compute facts from the repo at run time wherever it can rather than hard-coding
them, (b) carry a `doctor` subcommand that probes every hard-coded fact, and (c) get
re-generated on a cadence. Build all three or do not build it.

## Workflow

Work in the repo root. Keep a short task list; this is a 6-step job.

### 1. Mine the transcripts

Run the bundled analyzer (stdlib only, read-only):

```bash
python3 <skill-dir>/scripts/analyze_transcripts.py --repo . --top 30
python3 <skill-dir>/scripts/analyze_transcripts.py --repo . --json > /tmp/repeats.json
```

On Windows, use `python` (or `py`) instead of `python3`, and write the JSON to a
path that exists there (e.g. `%TEMP%\repeats.json`).

It auto-detects Claude Code transcripts (`~/.claude/projects/<encoded-cwd>/*.jsonl`),
GitHub Copilot CLI sessions (`~/.copilot/session-state/*/events.jsonl`) and GitHub
Copilot Chat sessions saved by VS Code for this folder
(`<VS Code user dir>/workspaceStorage/<hash>/chatSessions/`). For other agents or
exported logs pass `--transcripts DIR` (jsonl/json/md/txt; the parser is
format-agnostic, so sanity-check counts on a format it has not seen).
VS Code's chat format is undocumented and often omits tool-call arguments, so the
analyzer usually extracts little from it and prints a low-yield warning. When it
does, use the manual probe and treat the report as a hint.
It reports commands, file reads, searches and user questions that recur **across
sessions**, plus a first guess at subcommand clusters.

If no transcripts exist (new machine, agent that does not persist sessions, or an
enterprise policy that wipes them), do not stall. Fall back to the manual probe in
`references/manual-probe.md`: you orient on the repo yourself, *while noting every
read and command you make*. That list is your repeated-items list.

### 2. Confirm the list with the user, briefly

Show the repeated-items list (the "before"). Ask one question at most: anything to
add or drop? Lemieux's answer to "did you tell it the questions?" was "it worked out
from session history and a bit of my probing" — the user's probing is the part you
cannot mine.

### 3. Build `./bin/agent-cli`

Copy `assets/agent-cli.template.py` to `./bin/agent-cli`, `chmod +x`, and fill it.
On Windows there is no shebang or `chmod`: the CLI runs as `python bin/agent-cli`,
so use that form everywhere you write the command (AGENTS.md block included).
Read `references/design-rules.md` first; the rules there are what make the output
useful to an agent rather than another README.

Pick the runtime the repo already has. The template is Python 3 stdlib. If the repo
is Node-only and Python is not guaranteed, port the same structure to a `#!/usr/bin/env node`
script — same subcommand names, same `--json` contract. Never add a dependency; the
whole point is zero install.

Default subcommands (drop any the repeated-items list does not justify, add any it
does):

| subcommand | replaces |
|---|---|
| `info` | re-reading manifests to learn stack, scripts, entry points, run/test/build |
| `map` | `ls` / `tree` walks; one-line purpose per top-level dir |
| `status` | the `git status` + `git log` + branch dance |
| `where <term>` | repeated greps; knows which dirs to skip |
| `test [--only]` | guessing the test runner and its flags |
| `orient` | the 20-line cold-start digest that replaces 6 doc reads |
| `faq [q]` | questions the user kept asking |
| `doctor` | validates the CLI against the repo; exit 1 on drift |

Every hard-coded fact in `info`, `orient`, `faq` gets a probe in `doctor`. Record
the commit sha and date you generated against in `GENERATED_FROM`.

### 4. Wire it into the agent's instructions

Append to `AGENTS.md` (create it if absent). Both Claude Code and GitHub Copilot
read it. If the repo also has `CLAUDE.md` or `.github/copilot-instructions.md`, add
a one-line pointer there rather than duplicating the block:

```markdown
## agent-cli
Run `./bin/agent-cli` first in every session. Prefer it over re-reading files or
guessing commands. `--json` on all subcommands. If `./bin/agent-cli doctor` fails,
fix the CLI before trusting its other output. Add a subcommand when you catch
yourself repeating a lookup; refresh with the agent-cli-builder skill.
```

On a repo developed on Windows, write the commands as `python bin/agent-cli`
(and `python bin/agent-cli doctor`); if the team is mixed, give both forms.

### 5. Validate, then clean up after yourself

- `./bin/agent-cli doctor` must exit 0 with no `--allow-todo`.
- Run every subcommand once with and without `--json`; `--json` output must be
  valid JSON on one line.
- Time a cold orientation using only the CLI; note tokens/time for the "after".
- Lemieux's warning: the build leaves "crap and comments" in files. Do a cleanup
  pass — remove scaffolding comments, stray debug prints, TODO stubs you decided
  not to fill, and any edits you made to repo files other than `bin/agent-cli`,
  `AGENTS.md`/`CLAUDE.md`.

### 6. Report before vs after

End with a small table: the repeated items (count, sessions) on the left, the
subcommand that replaces each on the right, and the orientation cost before/after
(file reads, approximate tokens, seconds). This is what the user asked to see.

## Keeping it honest over time

Offer, do not impose, a refresh cadence:

- **On demand**: when a session adds a tool or script the agent used twice, add a
  subcommand in the same session.
- **Scheduled (daily by default)**: a task that runs `doctor`, re-mines transcripts,
  and edits the CLI only if something changed; on quiet days it prints one line
  and touches nothing, so daily costs almost nothing. The prompt is in
  `references/refresh-prompt.md`; drop to weekly if the one-liners become noise.
  Lemieux's experience: it churns for the first few runs, then stabilises once
  setup, end-to-end test and the probe tools are nailed down.

## When not to use this

A repo the agent touches once. A monorepo with no stable layout (build per-package
instead). A repo where transcripts are forbidden *and* the user will not sit for a
10-minute probe — a CLI built from guesses is the drift problem on day one.
