# Changelog

Release record for `transon-authoring` (NFR-008). Every release gets one entry, headed by the
released skill version, stating the **version triplet** — skill version, engine pin, snapshot
hash — and the outcome of each distribution-verification ladder step (ROADMAP §14 A5).
`scripts/check_install.py` (AC-042) verifies the triplet in the topmost release entry against its
sources of truth: `pyproject.toml` and `resources/metadata-snapshot.md`. The ladder outcomes below
are maintainer-recorded prose; nothing here is mechanically verified, so anything not yet run is
written as pending, never as a result.

Dates are UTC. Run references are GitHub Actions run URLs or ids.

## 0.1.0 — published 2026-07-25

First production release: `transon-authoring 0.1.0` is on PyPI (tag `v0.1.0`, run 30180068652).
Ladder steps 1, 2, 3 and 5 are green; **step 4 (the UC-004 human walkthrough) has not been
performed** and is the last outstanding gating item. This entry is amended in place as it
completes.

### Version triplet

- Skill version: `0.1.0` (the `pyproject.toml` project version)
- Engine pin: `transon==0.2.3` (as read textually from `pyproject.toml`)
- Snapshot hash — the sha256 of `resources/metadata-snapshot.json`, as recorded in the
  `snapshot_sha256` field of its provenance file `resources/metadata-snapshot.md` (which is what
  `check_install` reads):
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
3. **Cursor headless activation smoke (credentialed dispatch tier, OQ-008)** — **GREEN.**
   Non-gating. Carries an **unresolved credential-exposure risk** the platform prevents closing:
   the job runs an unverifiable `curl | bash` Cursor binary with `CURSOR_API_KEY` present (Cursor
   ships no pinnable artifact and no key-proxy). Bounded, not closed — the job refuses to run
   without `accept_unverified_cli_risk=yes`, a dedicated revocable key is mandatory, and **egress
   is denied except a derived allowlist** (`*.cursor.sh`, `registry.npmjs.org`, GitHub infra;
   OQ-027f(iii)). The block bounds where a leaked key could go but cannot eliminate the path, since
   Cursor's own API is necessarily reachable. See the workflow header.
   - Egress tightened `audit` → `block` and **verified green under it** (run 30196218752, same
     matched envelope, no blocked-host annotations). The allowlist was derived from what the
     audit-tier runs observed, not guessed — it includes `registry.npmjs.org`, which the CLI
     contacts at runtime in a job that installs nothing; a hand-written list would have blocked it.
   - Outcome, 2026-07-26, run 30182409724 (`main`): `cursor-agent` **exit 0**, secret scan clean,
     and the episode emitted a **schema-valid `AuthoringResult` at `assurance: "matched"`**
     (template `{"$":"attr","name":"x"}`, `repair_count` 0) — **from a prompt that never named the
     skill**, in an ephemeral workspace holding only installer-provisioned files plus the task's
     SampleSet. `verdict`/`assurance`/`repair_count` are produced by the module running against the
     pinned engine, so the envelope cannot be narrated into existence. Reproduced identically on the
     preceding run 30182303844. Per OQ-008 this is **not** a claim about the host's internal skill
     routing, which no credential-free command exposes.
   - Getting here took four dispatches, each a real defect in the harness rather than the skill,
     all fixed: 30181027384 (`--trust` — the CLI refuses an untrusted directory), 30181110829
     (`--force` — `--trust` clears the directory prompt but not command approval, so the agent hung
     silently for 20 minutes), 30181831690 (the prompt supplied no SampleSet, so the skill correctly
     stopped at the §3 gate per FR-002/AD-014 and made no module call), and 30182303844 (the
     assertion grepped for the module-recipe string, which a **correct** run never emits — §7
     mandates returning `result` stdout verbatim, and that stdout is pure JSON).
4. **UC-004 human walkthrough (release checklist)** — **not yet performed.** No walkthrough on a
   repo-free machine (`pip install transon-authoring`; both installers; activation in real Claude
   Code and real Cursor; one authored template) has been done. **This is the last outstanding
   gating item in the A5 Definition of Done.** `0.1.0` is on production PyPI, so the walkthrough
   now installs from the real index with no `--index-url` override.
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

**The baseline predates a few edits to the shipped body**, none of which fires a §11.8 reset
trigger — pin, corpus, gate model and harness `kind`/`version` are all unchanged — so the corpus was
deliberately not re-measured for this release, and the scores above reflect the body before these
edits: the runtime-prerequisite paragraph (`pip install transon-authoring` on
`No module named transon_authoring`); the §6 approve step now passing `--repair-count <N>` so an
approved success reports its true repair count; and §3 now requiring an explicit `--samples` path or
`init-config` in a non-interactive run rather than proceeding without a resolved location. All are
additive or clarifying — no operator, rule, or grounding behavior changed. Three fixtures passed the
baseline run 2/3 (`ec2-flatten-inventory`, `refuse-recursive-flatten`, `seed-refuse-nonexistent-mode`)
and remain future-flake candidates.

### Publication

- **TestPyPI: `0.1.0` published** 2026-07-25 (sdist + wheel, with provenance attestations) from
  `.github/workflows/release.yml` on `main`, run 30179949576. An earlier `0.0.1` upload
  (2026-07-22, run 29915374804) validated the publish path at the pre-bump version.
  - Post-publish verification of the **published artifact** (not the checkout): installed into a
    clean venv from TestPyPI, `transon==0.2.3` resolved transitively from PyPI, and `metadata`,
    `language --list-sections`, `examples search`, `check-samples` and `verify` all exit 0 with
    valid JSON. This is evidence the distribution is sound; it is **not** ladder step 4, which
    additionally requires a repo-free machine and real-host activation.
- **PyPI (OQ-020): `0.1.0` PUBLISHED** 2026-07-25 — the first production release. Tag `v0.1.0`
  (commit `fedbd19`) triggered `.github/workflows/release.yml`, run 30180068652; wheel + sdist
  uploaded via Trusted Publishing under the `pypi` environment. The build job re-verified the
  artifacts and the tag↔version agreement before upload.
  - Post-publish verification of the **published artifact**: `pip install transon-authoring` into a
    clean venv resolved `transon-authoring 0.1.0` with `transon==0.2.3` transitively, and
    `metadata`, `language --list-sections`, `examples search` and `verify` all exit 0.
- FR-037b external catalog submission: **now eligible** (the PyPI publish it waited on has
  happened) but not started. It gates nothing.

### Notes

- This is the first entry. The `0.0.1` artifacts on TestPyPI are a publish-path validation, not a
  release; `0.1.0` is the first version on production PyPI.
