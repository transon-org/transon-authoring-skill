# Claude Code adapter

Run `python3 install/claude.py` to install the skill. The installer copies the canonical
`SKILL.md` from `skills/transon-authoring/` into Claude Code's skill directory and writes
`.install-manifest.json` there, recording every file it created. Re-running the installer is an
idempotent replace of those files; `python3 install/claude.py --uninstall` removes only the paths
listed in the manifest.

Files land in `<repo>/.claude/skills/transon-authoring/` for the project scope, or in
`~/.claude/skills/transon-authoring/` for the personal scope.
