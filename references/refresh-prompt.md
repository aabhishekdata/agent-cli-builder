# Refresh prompt — for a daily scheduled task or an on-demand re-run

Paste as the task prompt (Claude Code scheduled task, cron + `claude -p`, or
whatever runner is allowed on the machine). It is self-contained; every run starts
cold. Default cadence: **daily**, shaped to be a near-no-op on quiet days so the
cost is attention-free.

```
Use the agent-cli-builder skill to refresh ./bin/agent-cli in this repo.

Gate first, cheaply:
  a. Run `./bin/agent-cli doctor --json`.
  b. Run scripts/analyze_transcripts.py --repo . --json and compare the
     repeated-items list to the CLI's subcommands.
  c. Check whether HEAD moved since GENERATED_FROM.
If doctor passes, there are no new repeated items, and HEAD has not moved in a
way that touches files the CLI references: stop. Output exactly one line:
"agent-cli: no drift, no new repeats (<date>, HEAD <sha>)". Do not edit anything.

Otherwise:
1. Fix any failed doctor probe first; note what had drifted.
2. For each repeated item not yet covered: add or extend a subcommand, with a
   doctor probe for any hard-coded fact.
3. For each subcommand with no repeated use in the last 14 days: list it as a
   removal candidate. Do not remove.
4. Bump CLI_VERSION if subcommands changed; update GENERATED_FROM to today's
   date and HEAD sha.
5. Run every subcommand once with --json and once without; all must succeed.
6. Cleanup pass: only bin/agent-cli and AGENTS.md/CLAUDE.md may change.
7. Report in under 15 lines: drift found, subcommands added/changed, removal
   candidates, and today's orientation cost vs the recorded baseline.
```

## Cadence notes

- **Daily** suits repos that change every day. The gate keeps quiet days to one
  line and zero edits, so the only real cost is the agent's startup tokens.
- **Weekly** (Lemieux's cadence) suits slower repos or when daily reports become
  noise. Change nothing but the schedule; the prompt is the same.
- Expect the first few runs to change a lot and later runs to print the one-line
  no-op. That flattening is the signal the CLI has stabilised. If it never
  flattens, the CLI is hard-coding things it should compute; revisit
  design-rules.md.
- Also add subcommands opportunistically: when a working session uses a new
  script or tool twice, add it then, do not wait for the scheduled run.
- If the task runner can't write to the repo (read-only enterprise checkout), have
  it produce a patch file and a summary instead, for a human to apply.
- Removal candidates accumulate across runs; review them monthly by hand rather
  than letting the task prune.
