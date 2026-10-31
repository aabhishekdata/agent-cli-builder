# Design rules for an agent-facing CLI

The audience is a language model with a token budget, not a developer with a
terminal. Everything below follows from that.

## Output

- **Terse.** No banners, no colour, no progress bars, no blank-line padding. A
  subcommand's default output should fit in ~30 lines; `--json` can be longer but
  must be one line.
- **`--json` on every subcommand**, same shape every time. The agent will parse it;
  humans will not read it.
- **Name the source of every hard-coded fact.** `faq` answers carry `"source":
  "docs/db.md"`. If the agent needs more, it knows exactly which single file to open.
- **Silence is a result.** `where` with no hits prints `(no hits)`, not a paragraph.
- **Never print the thing it replaces.** `orient` is a 20-line digest, not `cat README.md`.
  If a digest grows past ~25 lines, split it or push facts into `info`/`map`.

## Facts

- **Compute, don't transcribe.** Scripts from `package.json`, branch from git,
  directory listing from the filesystem. Computed facts cannot drift.
- **Hard-code only what cannot be computed** — purposes, traps, conventions — and
  give each one a `doctor` probe (the file it refers to still exists; the command it
  names still resolves).
- **Record provenance.** `GENERATED_FROM = "2026-10-31 @ abc1234"`. Bump
  `CLI_VERSION` when subcommands change. Both show in `--version` and `doctor`.

## Scope

- One file, one runtime, zero dependencies. If it needs `pip install` or `npm i`,
  it has failed.
- Subcommands earn their place by appearing in the repeated-items list or the
  user's probing. Do not add "useful" ones speculatively; each is a drift surface.
- Read-only by default. A subcommand that mutates the repo (`test` may write
  caches; fine) must say so in its docstring.
- Fast. Every subcommand returns in under ~3s on a cold cache, except `test`.

## Trust

- `doctor` exits non-zero on any failed probe. The AGENTS.md block tells the
  agent to fix the CLI before trusting the rest. This is what lets the agent skip
  file reads with a clear conscience (pwguler's question in the thread).
- When the agent discovers the CLI was wrong, the fix is to the CLI, not a
  workaround in the session.

## Cleanup

Generation tends to leave scaffolding behind: TODO comments, explanatory
docstrings written for the generator, debug prints, test files in the repo root,
edits to files that were only being read. Before declaring done, `git status` and
`git diff` — only `bin/agent-cli`, `AGENTS.md`/`CLAUDE.md` should have changed,
unless the user asked for more.
