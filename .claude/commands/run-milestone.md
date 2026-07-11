---
description: Drive a SPEC milestone (e.g. A0) end-to-end for `transon-authoring`.
argument-hint: [milestone e.g. A0]
---

Run SPEC milestone **$ARGUMENTS** for `transon-authoring`.

The procedure is tool-neutral and lives in `harness/commands/run-milestone.md` — follow it exactly,
under the rules in `AGENTS.md`. Delegate planning to the `milestone-planner` subagent and
implementation of each cited FR/NFR/AC requirement to `requirement-implementer`; request a
`spec-reviewer` pass before merge.
