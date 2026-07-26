# Release runbook

> **Non-normative operational guide.** The contract is [`SPEC.md`](SPEC.md) +
> [`ARCHITECTURE.md`](ARCHITECTURE.md) + [`ROADMAP.md`](ROADMAP.md); where this and they disagree,
> **they win**. NFR-008 defines what a release must record, AC-042 checks the version triplet, and
> ROADMAP §14 defines the A5 distribution-verification ladder. This file is the how-to; the outcome
> of every step is recorded in [`CHANGELOG.md`](../CHANGELOG.md).

Publishing is **irreversible**: a version number can never be reused on PyPI or TestPyPI, even
after deletion. Everything below is ordered so that anything recoverable fails *before* an upload.

---

## 0. One-time setup

Both are account-level actions a maintainer performs by hand; no automation touches them.

**Trusted Publishers (OIDC — no stored tokens).** On both `test.pypi.org` and `pypi.org`, under
Account → Publishing, register a publisher for project `transon-authoring`:

| Field | Value |
|---|---|
| Owner | `transon-org` |
| Repository | `transon-authoring-skill` |
| Workflow | `release.yml` |
| Environment | `testpypi` on TestPyPI · `pypi` on PyPI |

The identity is bound to *(owner, repo, workflow, environment)*, which is why `release.yml` has two
separate publish jobs — a job may declare only one environment. Before a project exists on an
index, the registration shows as a **pending publisher**; it converts to a normal one on the first
upload.

**GitHub environments.** `release.yml` references `testpypi` and `pypi`. GitHub auto-creates a
referenced environment at run time, but auto-created environments have **no protection rules** — so
if you want a human approval gate before production, create `pypi` in Settings → Environments and
add required reviewers *before* the first tag push.

---

## 1. Pre-flight

```bash
git checkout main && git pull
```

Confirm the version you intend to release, and that the working tree is clean:

```bash
grep '^version' pyproject.toml && git status --short
```

Run the gates locally (CI runs them too, but a red gate here saves a round trip):

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/check_install.py && .venv/bin/python scripts/check_parity.py && .venv/bin/python scripts/check_snapshot.py
python3 harness/scripts/check_traceability.py && python3 harness/scripts/check_append_only_ids.py
```

`check_install` includes AC-042: the topmost `CHANGELOG.md` release entry must already name this
version, the engine pin, and the snapshot hash. Fix the record *before* publishing, not after.

**Version bump.** If this release needs a new version, change it in `pyproject.toml` **and**
`.claude-plugin/plugin.json` in the same commit — AC-040 requires they match, and `release.yml`
requires the git tag to match too.

---

## 2. TestPyPI rehearsal

A `workflow_dispatch` run publishes to **TestPyPI only**; production is unreachable this way
(guarded on `event_name == 'push'`, so a manual run that selects a tag ref still cannot reach PyPI).

```bash
gh workflow run release.yml --ref main
```

The build job rebuilds the wheel and sdist, installs the **wheel** into a fresh venv, asserts the
bundled `resources/` are present inside it, and exercises the §11.6 surface offline — all before
the upload. Watch it:

```bash
gh run watch "$(gh run list --workflow=release.yml --limit 1 --json databaseId -q '.[0].databaseId')"
```

Verify the artifact landed (the JSON API lags; the simple index is fresher):

```bash
curl -fsS https://test.pypi.org/simple/transon-authoring/ | grep -oE 'transon_authoring-[^"#<]+\.(whl|tar\.gz)' | sort -u
```

Then verify the **published artifact**, not the checkout, in a throwaway venv. The
`--extra-index-url` is required: `transon` resolves from real PyPI, not TestPyPI.

```bash
python3 -m venv /tmp/tpv && /tmp/tpv/bin/python -m pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ transon-authoring
/tmp/tpv/bin/python -m transon_authoring metadata > /dev/null && echo OK
```

---

## 3. UC-004 walkthrough (ladder step 4)

Irreducibly human, and **must run on a machine without this repository** — the point is to
experience the fresh-user path, which a checkout would short-circuit.

On macOS, `scripts/uc004_walkthrough.sh` does the mechanizable half and prompts for the rest. Copy
it to a repo-free directory (it refuses to run inside a checkout) and run it; it emits a report
block for the `CHANGELOG.md` entry:

```bash
bash uc004_walkthrough.sh --keep        # add --personal to exercise the ~ destinations too
```

It installs the runtime from PyPI into a throwaway venv, checks the module surface, unpacks the
release archive for the installed version, runs both installers into a throwaway project, asserts
the installed `SKILL.md` is byte-identical to canonical with a complete manifest, and drives
`check-samples` → `result` to a matched `AuthoringResult`. It then prints the workspace path and the
prompt to paste into each host. The manual steps below are what it cannot do for you.

1. Install the runtime — `pip install transon-authoring` (the project is on production PyPI; use
   the TestPyPI form from §2 only when rehearsing an unreleased version).
2. Obtain the skill files (a release archive or a clone) and run both installers:
   ```bash
   python3 install/claude.py --scope personal
   python3 install/cursor.py --scope personal
   ```
   Add `--target-root <dir>` for a project-scope install into a project other than the source.
3. Open **real Claude Code** and **real Cursor**, confirm the skill activates on its own, and author
   one template end to end to `assurance: "matched"`.
4. Record OS, host versions, the index used, and the outcome in `CHANGELOG.md`.

Uninstall removes only what the installer recorded in `.install-manifest.json`:

```bash
python3 install/claude.py --scope personal --uninstall
```

---

## 4. Production publish

Only a **pushed `v*` tag** reaches PyPI. The build job re-verifies the artifacts and refuses if the
tag disagrees with the project version.

```bash
git tag v0.1.0 && git push origin v0.1.0
```

Watch the run, then confirm:

```bash
curl -fsS https://pypi.org/simple/transon-authoring/ | grep -oE 'transon_authoring-[^"#<]+\.(whl|tar\.gz)' | sort -u
python3 -m pip download --no-deps -d /tmp/pypi-check transon-authoring==0.1.0
```

If the publish fails *after* upload has begun, do not retry the same version — bump the patch
version and release again.

---

## 5. Record the outcome

Fill the `_pending_` slots in the topmost `CHANGELOG.md` entry: run references for the deterministic
ladder steps, and date-plus-result for the credentialed and human ones (NFR-008). Then flip the
`NFR-008` row in [`traceability.md`](traceability.md) to `[x]` — but only once its cited tests are
green and citing the ID and `check_traceability` is consistent; a filled checklist alone does not
satisfy the row.

---

## How users install

Three independent channels. All of them ground through the same §11.6 module recipe — the skill
body is identical in every channel, and none of them bundles the runtime.

**Runtime (required by all three):**
```bash
pip install transon-authoring
```

**Skill files — installer scripts** (from a checkout or release archive), per §11.9:

| Tool | Project scope | Personal scope |
|---|---|---|
| Claude Code | `<target>/.claude/skills/transon-authoring/` | `~/.claude/skills/transon-authoring/` |
| Cursor | `<target>/.cursor/skills/transon-authoring/` | `~/.cursor/skills/transon-authoring/` |

**Skill files — Claude Code plugin marketplace.** This repo is both the plugin root and the
self-hosted marketplace, so users need no third-party catalog:

```
/plugin marketplace add transon-org/transon-authoring-skill
/plugin install transon-authoring@transon-authoring
```

The form is `<plugin>@<marketplace>`; both are named `transon-authoring` here. Users refresh with
`/plugin marketplace update`. The plugin's skills load from `skills/` under its `source` (`./`, the
repo root) by default, which is where the canonical body lives — no copy, no sync step.

---

## After PyPI: catalog submission (FR-037b)

Non-gating outreach that gates no milestone, and starts **only after** the PyPI publish — a listed
skill whose runtime is unpublished is inert. CI never claims catalog presence or host
discoverability. Submit to third-party agent-skill catalogs as adoption warrants.
