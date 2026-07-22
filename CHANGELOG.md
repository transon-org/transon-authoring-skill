# Changelog

Release record for `transon-authoring` (NFR-008). Every release gets one entry, headed by the
released skill version, stating the **version triplet** — skill version, engine pin, snapshot
hash — and the outcome of each distribution-verification ladder step (ROADMAP §14 A5).
`scripts/check_install.py` (AC-042) verifies the triplet in the topmost release entry against its
sources of truth: `pyproject.toml` and `resources/metadata-snapshot.md`. The ladder outcomes below
are maintainer-recorded prose; nothing here is mechanically verified, so anything not yet run is
written as pending, never as a result.

Dates are UTC. Run references are GitHub Actions run URLs or ids.

## 0.1.0 — prepared 2026-07-22, not yet published

Status: **release record prepared; the artifacts are not published.** The version triplet below is
current; the ladder is partially complete (steps 2, 3, 4 and the PyPI publish are pending). This
entry is amended in place — with run references and dates — as those steps complete, and it is not
a claim that release 0.1.0 has shipped.

### Version triplet

- Skill version: `0.1.0` (the `pyproject.toml` project version)
- Engine pin: `transon==0.2.3` (as read textually from `pyproject.toml`)
- Snapshot hash (`snapshot_sha256` from `resources/metadata-snapshot.md`):
  `d4452b950617057a920bfb90101a9806a4aced2b9744766fc82951534cb37a8c`

### Distribution-verification ladder (ROADMAP §14 A5)

1. **Dist smoke (CI job)** — *implemented and running.* The `dist-smoke` job in
   `.github/workflows/ci.yml` builds the wheel and sdist, installs the **wheel** into a fresh venv
   (never editable), asserts the bundled `resources/` shipped inside the wheel, and runs the §11.6
   surface offline against the committed fixtures. `.github/workflows/release.yml` re-runs the same
   verification on the built release artifacts before either publish job. Green on the runs that
   introduced it (29881245086 on `ci-dist-smoke-and-pypi-release`, 29901744596 on `main`) and on
   `a5-release` (run 29961121196, PR #28 — the `dist-smoke` job green).
   - Release-commit CI run reference: _pending — to be filled when the release tag is pushed._
2. **Distribution-faithful eval provisioning** — **validated.** The §11.8 harness workspace is
   provisioned by `install/claude.py --target-root <workspace>` from the staged file subset, and a
   provisioning failure classifies as `infra_error` rather than scoring as a fixture failure. No
   full gate run under this provisioning is required (see the eval baseline note below).
   - Outcome: targeted `--only` probe, 2026-07-22, run 29961198852 on `a5-release` —
     `seed-matched-flatten-orders` ×3: majority `pass`, all three episodes `submitted`,
     **zero `infra_error`**, authoring rate 1.0, $0.49. The zero is the result that matters: the
     installer-provisioned workspace auto-activated the shipped skill against a real host. The job
     exits 1 by construction (a single matched fixture leaves the adversarial bucket empty, which
     `check_evals` reports as a hard red); the pass criterion is the per-fixture majority.
3. **Cursor headless activation smoke (credentialed dispatch tier, OQ-008)** — **not yet
   performed.** No `cursor-agent -p` run against a `install/cursor.py --target-root` workspace has
   been executed. Non-gating when it is run.
   - Outcome: _pending — run reference or date, result._
4. **UC-004 human walkthrough (release checklist)** — **not yet performed.** No walkthrough on a
   repo-free machine (`pip install transon-authoring` from TestPyPI, then PyPI; both installers;
   activation in real Claude Code and real Cursor; one authored template) has been done.
   - Outcome: _pending — date, machine/OS, index used, result._
5. **Plugin packaging (FR-037a, offline deterministic)** — *implemented and gated.* The §11.9
   plugin layout (`.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`,
   `skills/transon-authoring/SKILL.md`, the canonical body) is
   checked by `check_install` (AC-040) on every CI run. Structural packaging integrity only — no
   published package, no catalog claim.
   - Release-commit CI run reference: _pending — to be filled when the release tag is pushed._

### Eval baseline

`evals/baseline.json` holds the 54 majority-passers of the green real-host gate of 2026-07-20
(run 29782513843, 54 fixtures ×3, authoring 1.000 / adversarial 1.000 / correction 1.000). That run
is the AD-007 repin's pin+corpus baseline reset and satisfies the A5 entry condition.

**The baseline predates one edit to the shipped body**: commit `9be1f66` added a five-line paragraph
naming the runtime prerequisite (`pip install transon-authoring`) for agents that hit
`No module named transon_authoring`. It is additive and defensive, and it fires no §11.8 reset
trigger — pin, corpus, gate model and harness `kind`/`version` are all unchanged — so the corpus was
deliberately not re-measured for this release. The scores above therefore reflect the shipped body
minus that paragraph. Three fixtures passed that run 2/3 (`ec2-flatten-inventory`,
`refuse-recursive-flatten`, `seed-refuse-nonexistent-mode`) and remain future-flake candidates.

### Publication

- **TestPyPI:** `transon-authoring 0.0.1` (sdist + wheel) was uploaded 2026-07-22 from
  `.github/workflows/release.yml` on `main`, run 29915374804 — a validation of the publish path,
  at the pre-bump version. Nothing at `0.1.0` has been uploaded to any index.
- **PyPI (OQ-020): not yet published.** No upload to the production index has been made. The
  production job requires a pushed `v*` tag, and no tag exists.
  - Outcome: _pending — tag, run reference, date, result._
- FR-037b external catalog submission: not started; it gates nothing and begins only after the
  PyPI publish.

### Notes

- No production release exists; this is the first entry. The `0.0.1` artifacts on TestPyPI above
  are a publish-path validation, not a release.
