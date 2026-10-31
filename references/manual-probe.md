# Manual probe — when there are no transcripts to mine

You are about to orient on this repo the way any fresh session would. The only
difference: **log every read, listing, search and command as you go**, in a
scratch file, as one line each. That log *is* the repeated-items list — because
the next session would do exactly the same things.

## Procedure (10–15 minutes)

1. Open a scratch log (`/tmp/probe.log`, or the scratchpad directory). Append a
   line per action: `READ path`, `LS path`, `GREP pattern`, `RUN command`,
   `ASK question`.
2. Orient as you normally would, answering these for yourself:
   - What is this? (README / docs)
   - What stack, what version, what package manager? (manifest)
   - Where is the entry point? Where does real work live? (ls, grep)
   - How do I run it? Test it? Build it? Lint it? (scripts, Makefile, CI yaml)
   - What is generated vs hand-written? What must not be edited?
   - Env/config: what does it need to start? (`.env.example`, config dirs)
   - Branch, recent history, anything half-done? (git)
3. Ask the user two things only: *"What do you ask the agent about this repo
   most often?"* and *"What does the agent get wrong most often here?"* Each
   answer is a `faq` entry or a `doctor` probe.
4. Group the log into clusters; map each cluster to a subcommand from the table in
   SKILL.md. Anything done once and unlikely to recur: drop.

## Counting the "before"

Without transcripts you cannot measure the historical cost, so measure yours:
number of file reads, number of commands, wall-clock seconds, and approximate
tokens (sum of bytes read ÷ 4 is close enough). Report it as the "before" and say
it is a single-session estimate.

## Other agents' transcripts, if you can find them

Locations vary and change; check before claiming none exist. Common patterns:
a `sessions/`, `.sessions/` or `session-state/` directory under the agent's
dotfolder in `$HOME`; `.jsonl` or `.json` per session. Pass whatever you find to
`analyze_transcripts.py --transcripts DIR`. Its text parser is heuristic for
non-Claude formats, so sanity-check the counts before trusting them.
