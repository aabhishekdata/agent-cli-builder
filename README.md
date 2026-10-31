# agent-cli-builder (skill)

Turns a coding agent's repeated session-startup work into a repo-local
`./bin/agent-cli`. Zero dependencies; the analyzer and the CLI template are
Python 3 standard library only.

## Install on another machine

Copy this folder, unchanged, into a skills directory the agent reads:

| Agent | Per-repo (committed, team-visible) | Per-user |
|---|---|---|
| Claude Code | `<repo>/.claude/skills/agent-cli-builder/` | `~/.claude/skills/agent-cli-builder/` |
| Other agents that read `SKILL.md` folders | their documented skills dir | — |

If the agent does not load skills at all, open `SKILL.md` and paste its Workflow
section as the prompt; copy `scripts/` and `assets/` next to the repo and adjust
paths.

## Use

In the repo you want to speed up, start a session and say:

> Use the agent-cli-builder skill on this repo.

or run the original one-shot prompt (works without the skill, with less guard-rail):

```
Review all session transcripts for this repo. List the questions, lookups, file
reads, and commands you repeated across sessions.

Then build ./bin/agent-cli — a tiny CLI that answers those questions from one
place. Every script, tool, or command you ran more than once becomes a subcommand
with its own --help. Terse output, written for you not humans, with a --json flag.
No new dependencies.

Add a line to agents.md: use agent-cli first, prefer it over re-reading files or
guessing commands.

Show me the repeated-items list with before and after CLI to see how much it
sped you up.
```

## Contents

```
agent-cli-builder/
├── SKILL.md                      # the workflow the agent follows
├── scripts/analyze_transcripts.py  # mines transcripts for repeated items (stdlib)
├── assets/agent-cli.template.py    # starter CLI with doctor/self-check (stdlib)
└── references/
    ├── design-rules.md           # what makes output useful to an agent
    ├── manual-probe.md           # fallback when there are no transcripts
    └── refresh-prompt.md         # weekly regeneration prompt
```

## Enterprise notes

- Nothing phones home; no installs. Safe to run on a locked-down machine with
  Python 3.8+.
- Transcripts are read, never modified or copied out.
- Only `bin/agent-cli` and `AGENTS.md`/`CLAUDE.md` are meant to change in the repo.
- If the checkout is read-only, the skill produces a patch instead.
