# CLAUDE.md

Read [`AGENTS.md`](AGENTS.md) and follow it — it is the canonical, tool-neutral operating contract
for this repo. The product contract spans three documents: [`docs/SPEC.md`](docs/SPEC.md)
(requirements, normative contracts, governance, traceability),
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) (architecture, decision records, package layout),
and [`docs/ROADMAP.md`](docs/ROADMAP.md) (milestones, open questions, risks, readiness).
Section numbers are global and unique across all three.

Tool-neutral harness bodies (commands, agent roles, gates) live in `harness/`; the files under
`.claude/` are thin adapters that point there. Never copy a body into `.claude/` — reference it.
