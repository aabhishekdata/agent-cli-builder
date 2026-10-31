# HANDOFF — agent-cli-builder

Context for whoever (or whichever agent) picks this up next. Written 2026-11-01
from the Claude chat session in which this repo was built. Read this first, then
`SKILL.md`.

## One-paragraph summary

Abhishek saw a tweet by Jean-Michel Lemieux (31 Oct 2026) describing a prompt that
makes a coding agent mine its own session transcripts for repeated lookups and build
`./bin/agent-cli`, a tiny dependency-free CLI that answers those lookups in one call
(orientation dropped from ~40k tokens / 6 file reads / 30s to ~2k tokens / 1 command / 5s).
He asked for an explanation and an implementation he could carry to a work machine he
cannot access from the chat. The result is this repo: a portable `SKILL.md` skill plus a
stdlib-only transcript analyzer and a CLI template with a drift-detecting `doctor`
subcommand. Target environment is **GitHub Copilot in VS Code** (Claude models, no
Claude Code). Refresh cadence was changed from weekly to **daily with a quiet-day gate**.

## State of the repo

- `main` at `8b13eeb` (public, github.com/aabhishekdata/agent-cli-builder).
- Files: `SKILL.md`, `README.md`, `scripts/analyze_transcripts.py`,
  `assets/agent-cli.template.py`, `references/{design-rules,manual-probe,refresh-prompt}.md`,
  `.gitignore`, this file.
- Tested: analyzer parses Claude Code JSONL (real file) and a synthetic Copilot-CLI-style
  `events.jsonl`. CLI template runs; `doctor` exits 1 on TODOs as intended.
- Not yet tested: a real Copilot CLI transcript; the full skill end-to-end in VS Code
  agent mode on a real repo.

## Install / use (the version Abhishek needs)

```bash
git clone https://github.com/aabhishekdata/agent-cli-builder ~/.copilot/skills/agent-cli-builder
```
Then, in Copilot Chat (agent mode) inside the target repo:
> Use the agent-cli-builder skill on this repo.

Afterwards nothing is manual: Copilot reads `AGENTS.md` at session start and runs
`./bin/agent-cli` on its own. Daily: `./bin/agent-cli doctor` in the terminal; if red,
tell Copilot "doctor is failing, fix agent-cli".

## Decisions made, and why

| Decision | Reason |
|---|---|
| Deliver as a skill, not a one-shot prompt | Needed guard-rails the tweet lacks: drift checks, no-transcript fallback, cleanup pass; portable folder for a machine not reachable from chat |
| Python 3 stdlib only | Zero install on a locked-down enterprise machine; "no new dependencies" is the tweet's own rule |
| Compute facts at run time wherever possible | Computed facts cannot drift; hard-coding is reserved for purposes/traps/FAQ |
| `doctor` subcommand, exit 1 on failure | Addresses the thread's main objection: a drifted CLI "still looks authoritative" |
| Daily refresh, not weekly | Abhishek's repos change daily. Gate added so quiet days are a one-line no-op with zero edits |
| Removal of unused subcommands is proposed, never performed | A quiet fortnight must not delete something real; monthly hand review |
| Prefer `AGENTS.md` over `CLAUDE.md` | Both Copilot and Claude Code read `AGENTS.md`; pointer line in `CLAUDE.md`/`copilot-instructions.md` if present |
| Format-agnostic transcript parser as fallback | Copilot CLI `events.jsonl` shape differs from Claude Code's; generic walker finds tool-call-like dicts |
| Repo made public | Matches Abhishek's other skill repos (codeflow-map etc.). Session could not create the repo itself; Abhishek created it empty, session pushed |

## Open items / next steps

1. First real run on a work repo in VS Code. Expect the **manual-probe path** (VS Code
   agent mode keeps no readable transcript). Check that the two user questions get asked
   and that only `bin/agent-cli` + `AGENTS.md` change.
2. Validate the generic parser against a real `~/.copilot/session-state/*/events.jsonl`
   if Copilot CLI is ever available; adjust `_NAME_KEYS`/`_ARG_KEYS` in the analyzer if
   tool calls are missed.
3. Optional later: a `SessionStart`-style hook (Claude Code) or equivalent so the CLI
   runs mechanically rather than by instruction. Deferred until the CLI has stabilised.
4. Optional: port `agent-cli.template.py` to Node for repos where Python is not guaranteed.
5. Consider a `.github/skills/` install in a work repo so the team inherits it.

---

## Conversation log (questions and answers, condensed)

### Q1. Explain the tweet thread, and how do I implement it? Make a skill I can import on an enterprise machine I don't have access to.

**Thread explained.** Every fresh agent session re-orients: README, manifest, `ls`,
grep for entry point, `git status`, guess the test command. Lemieux measured ~6 reads,
~40k tokens, 30s each time. His fix: have the agent mine its session transcripts for
what it repeats, build `./bin/agent-cli` with one subcommand per repeated lookup,
terse `--json` output written for the agent, no dependencies, and one line in
`AGENTS.md` saying "run agent-cli first". Result: 1 command, 2k tokens, 5s.
Replies: (a) he did not hand it the questions, it inferred them from history plus his
probing; (b) drift concern: stale CLI is worse than six reads because it looks
authoritative, answered by on-demand additions plus a weekly re-run, stabilising after
setup/e2e/probes are nailed; (c) the agent does skip reads afterwards, after a cleanup
pass on junk comments the build left behind.

**Implementation.** Built `agent-cli-builder` skill: 6-step workflow (mine → confirm →
build → wire → validate+cleanup → before/after table); `scripts/analyze_transcripts.py`;
`assets/agent-cli.template.py` with `info/map/status/where/test/orient/faq/doctor`;
references for design rules, manual probe, refresh prompt. Delivered as `.skill` and `.zip`.

### Q2. How does the skill handle the drift you mentioned?

Four layers: (1) compute instead of hard-code; (2) every hard-coded fact has a `doctor`
probe, exit 1 on failure, refuses to pass while TODOs remain; (3) `AGENTS.md` tells the
agent to run `doctor` first and fix the CLI rather than work around it; (4) scheduled
refresh re-mines, adds subcommands, proposes removals, bumps version/provenance. Not
caught: a hard-coded fact with no probe, or semantic drift (dir exists but changed
purpose); the re-mining is the backstop because the agent re-reading a "covered" file
shows up as a repeated item again.

### Q3. Weekly is too infrequent for my work; daily? Overhead?

Compute overhead negligible (sub-second analyzer, trivial `doctor`); the cost is
attention and churn. Changed default to daily with a gate: run `doctor`, re-mine,
check HEAD vs `GENERATED_FROM`; if all clean, print one line and edit nothing.
Unused-window shortened to 14 days; removals still proposed only. Re-delivered files.

### Q4. Push this to my GitHub in a new repo.

Session cannot create repos (public creation denied by policy; private creation
blocked because the session is bound to attached repos). Local commit prepared;
asked Abhishek to create an empty repo. He created `aabhishekdata/agent-cli-builder`;
session attached it with push access and pushed `main` (`9d40e9f`).

### Q5. What are the main git commands I need to run?

Clone into skills dir → check `python3 --version` → optional analyzer preview →
run the skill via the agent → verify `./bin/agent-cli`, `doctor`, `info --json`,
`git status` → commit `bin/agent-cli` + `AGENTS.md` in the work repo → `git pull` the
skill when updated. Offline fallback: download zip, copy, unzip to same path.

### Q6. Once it has run, how does it work? Do I need to do anything? Does it refer to the CLI automatically?

Nothing changes for the user. The agent reads the instructions file at session start,
runs `./bin/agent-cli` first, uses `where`/`test` etc. mid-task instead of grep/guessing,
adds subcommands when it repeats itself. Caveat: instruction, not mechanism, so
occasional fallbacks to file reads early on. A `SessionStart` hook would make it
mechanical, deferred until stable.

### Q7. I don't have Claude Code, only GitHub Copilot with Claude models.

Verified against GitHub docs: Copilot loads `SKILL.md` folders from
`.github/skills`, `.claude/skills`, `.agents/skills` (repo) or `~/.copilot/skills`,
`~/.agents/skills` (personal); supported in CLI, VS Code agent mode, coding agent;
bundled scripts runnable with confirmation. Copilot reads `AGENTS.md`. Copilot CLI
transcripts live at `~/.copilot/session-state/<id>/events.jsonl`; VS Code agent mode
has none readable → manual probe. Updated analyzer with a format-agnostic walker,
updated docs, pushed `8b13eeb`.

### Q8. Simplify: I run this, ask the agent to use the skill, then run doctor daily?

Three steps, two owned by the user: clone once; run the skill once per repo; then
nothing, the agent runs the CLI itself. Daily `doctor` is either part of the agent's
startup line, scheduled, or a quick manual command when starting the day.

### Q9. To clarify, I use VS Code.

Same three steps. First run takes the manual-probe path (no readable transcripts);
the agent orients once while logging, asks two questions, builds. Daily check is
`./bin/agent-cli doctor` in the VS Code terminal; red → "doctor is failing, fix agent-cli".
Task Scheduler/cron optional, not required.

### Q10. Move this conversation to a Claude Code session?

Not possible from the chat; no handoff mechanism. The work is already in the repo;
this file carries the context. In Claude Code: clone, `claude`, "read HANDOFF.md and
continue."
