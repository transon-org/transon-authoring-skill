# Cursor adapter

Run `python3 install/cursor.py` to install the skill. The installer copies the canonical
`SKILL.md` from the repository root into Cursor's skill directory and writes
`.install-manifest.json` there, recording every file it created. Re-running the installer is an
idempotent replace of those files; `python3 install/cursor.py --uninstall` removes only the paths
listed in the manifest.

Files land in `<repo>/.cursor/skills/transon-authoring/` — project scope only; Cursor has no
personal skill scope in v1.
