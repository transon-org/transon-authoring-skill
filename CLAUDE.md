# CLAUDE.md

Read [`AGENTS.md`](AGENTS.md) and follow it — it is the canonical, tool-neutral operating contract
for this repo. The product contract is [`docs/SPEC.md`](docs/SPEC.md).

Tool-neutral harness bodies (commands, agent roles, gates) live in `harness/`; the files under
`.claude/` are thin adapters that point there. Never copy a body into `.claude/` — reference it.
