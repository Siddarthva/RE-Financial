# .claude — Claude Code project setup

`skills/` (monthly analysis and related skills), `commands/` (`/monthly-analysis`), `agents/` (`finance-reviewer`), `hooks/` (secret guard, post-edit tests) and `settings.json`. It must stay at the repo root for Claude Code to find it. See `02_skill/README.md`.

## Safety hooks (`.claude/settings.json`)

Two project hooks enforce rules from `CLAUDE.md`. The scripts are in `.claude/hooks/`.

| Hook | When | What it does |
|---|---|---|
| `guard_secrets.py` (PreToolUse on `Read`, `Grep`, `Bash`) | Before the call runs | Blocks any call naming a file called `.env`, `.env.*`, `*token*` or `*credential*` (`.env.example`, `.sample` and `.template` are allowed). Claude sees the block message and is told to ask you. |
| `test_after_edit.py` (PostToolUse on `Edit`, `Write`, `MultiEdit`) | After an edit to a `.py` file under `src/` | Runs `python -m unittest discover -s tests`. A failure goes back to Claude as feedback; edits elsewhere are ignored. |

**Proof.** `tests/test_hooks.py` covers the secret guard and the post-edit path filter. Both hooks were also run end-to-end through `claude -p` in a scratch project: `Read probe/.env` and `cat probe/credentials.json` were blocked by the hook, and changing a value in `src/` made the post-edit hook report the failing test.

**Limits.**
- The guard matches file names, not contents. In `Bash` it needs a path separator or an extension, so `grep token src` passes but `cat tokens` (no extension) and wildcards such as `cat .e*` do not trigger it.
- It is a safety net next to the `CLAUDE.md` rule, not a sandbox.
- The post-edit hook only fires for edits made through Claude's edit tools, not for files changed by a shell command.
