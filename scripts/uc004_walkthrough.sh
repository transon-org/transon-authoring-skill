#!/usr/bin/env bash
# UC-004 walkthrough helper — A5 distribution-verification ladder, step 4 (macOS).
#
# Runs the mechanizable half of the fresh-user path from the PUBLISHED artifacts
# and prompts for the half only a human can do (activation in real Claude Code
# and real Cursor). Emits a report block to paste into the CHANGELOG entry.
#
# Deliberately refuses to run inside a checkout: the point of UC-004 is the
# repo-free path, and a checkout would let the host fall back on repo files.
#
# Default installs PROJECT scope into a throwaway workspace, so nothing under
# your home directory is touched. `--personal` additionally exercises the
# personal-scope destinations, which are real paths under ~ — see the guard.
#
# Usage:  bash uc004_walkthrough.sh [--personal] [--version X.Y.Z] [--keep]

set -euo pipefail

SCOPE_PERSONAL=0
KEEP=0
VERSION=""
while [ $# -gt 0 ]; do
  case "$1" in
    --personal) SCOPE_PERSONAL=1 ;;
    --keep)     KEEP=1 ;;
    --version)  shift; VERSION="${1:-}" ;;
    -h|--help)  sed -n '2,17p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

SKILL_DIR="transon-authoring"
REPO="transon-org/transon-authoring-skill"
say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
ok()   { printf '  \033[32mok\033[0m   %s\n' "$*"; }
bad()  { printf '  \033[31mFAIL\033[0m %s\n' "$*"; }
note() { printf '       %s\n' "$*"; }

# ── Preflight ───────────────────────────────────────────────────────────────
say "Preflight"
[ "$(uname -s)" = "Darwin" ] || { bad "this script targets macOS"; exit 2; }
command -v python3 >/dev/null || { bad "python3 not found"; exit 2; }

# Refuse to run from inside the project checkout (UC-004 is the repo-free path).
probe="$PWD"
while [ "$probe" != "/" ]; do
  if [ -f "$probe/pyproject.toml" ] && grep -q '^name = "transon-authoring"' "$probe/pyproject.toml" 2>/dev/null; then
    bad "running inside the transon-authoring checkout ($probe)"
    note "UC-004 must run on a machine/directory without the repo. cd elsewhere (e.g. ~) and re-run."
    exit 2
  fi
  probe="$(dirname "$probe")"
done
ok "not inside a transon-authoring checkout"

OS_VER="$(sw_vers -productVersion)"
OS_BUILD="$(sw_vers -buildVersion)"
ARCH="$(uname -m)"
PY_VER="$(python3 -c 'import platform;print(platform.python_version())')"
ok "macOS ${OS_VER} (${OS_BUILD}), ${ARCH}, python ${PY_VER}"

_tmp="${TMPDIR:-/tmp}"; WORK="$(mktemp -d "${_tmp%/}/uc004.XXXXXX")"
cleanup() { [ "$KEEP" = "1" ] && { note "kept: $WORK"; return; }; rm -rf "$WORK"; }
trap cleanup EXIT
ok "workspace $WORK"

# ── 1. Install the runtime from PyPI ────────────────────────────────────────
say "1. pip install transon-authoring (production PyPI)"
python3 -m venv "$WORK/venv"
PY="$WORK/venv/bin/python"
"$PY" -m pip install --quiet --upgrade pip
if [ -n "$VERSION" ]; then
  "$PY" -m pip install --quiet "transon-authoring==${VERSION}"
else
  "$PY" -m pip install --quiet transon-authoring
fi
TA_VER="$("$PY" -m pip show transon-authoring | awk '/^Version:/{print $2}')"
ENGINE_VER="$("$PY" -m pip show transon | awk '/^Version:/{print $2}')"
ok "transon-authoring ${TA_VER}, transon ${ENGINE_VER} (resolved transitively)"

# ── 2. The runtime surface the skill body prescribes ────────────────────────
say "2. Module surface"
surface_ok=1
for cmd in "metadata" "language --list-sections" "examples search join"; do
  # shellcheck disable=SC2086
  if "$PY" -m transon_authoring $cmd >/dev/null 2>&1; then ok "python -m transon_authoring $cmd"
  else bad "python -m transon_authoring $cmd"; surface_ok=0; fi
done

# ── 3. Skill files from the published release archive ───────────────────────
say "3. Install skill files from the release archive"
TAG="v${TA_VER}"
curl -fsSL "https://github.com/${REPO}/archive/refs/tags/${TAG}.tar.gz" -o "$WORK/rel.tgz"
tar -xzf "$WORK/rel.tgz" -C "$WORK"
SRC="$WORK/$(tar -tzf "$WORK/rel.tgz" | head -1 | cut -d/ -f1)"
ok "release archive ${TAG} extracted"

PROJECT="$WORK/demo-project"; mkdir -p "$PROJECT"
# Run the installers under the SYSTEM python, as a real user would. They copy
# files and never run pip (OQ-020), so if the runtime is absent from that
# interpreter they print a hint on stderr and still exit 0 — expected, not a
# failure; the checks below are what decide.
note "(a 'runtime is not importable' hint from an installer here is expected — OQ-020)"
python3 "$SRC/install/claude.py" --repo-root "$SRC" --scope project --target-root "$PROJECT" >/dev/null
python3 "$SRC/install/cursor.py" --repo-root "$SRC" --scope project --target-root "$PROJECT" >/dev/null

install_ok=1
for tool in claude cursor; do
  dest="$PROJECT/.${tool}/skills/${SKILL_DIR}"
  if [ -f "$dest/SKILL.md" ] && [ -f "$dest/.install-manifest.json" ]; then
    if cmp -s "$dest/SKILL.md" "$SRC/skills/${SKILL_DIR}/SKILL.md"; then
      ok "${tool}/project: SKILL.md byte-identical to canonical + manifest present"
    else bad "${tool}/project: installed SKILL.md differs from canonical"; install_ok=0; fi
  else bad "${tool}/project: missing SKILL.md or .install-manifest.json"; install_ok=0; fi
done
MANIFEST="$PROJECT/.claude/skills/${SKILL_DIR}/.install-manifest.json"
TRIPLET="$(python3 -c "
import json;d=json.load(open('$MANIFEST'))
print('skill_version=%s engine_pin=%s snapshot_sha256=%s' % (
  d.get('skill_version'), d.get('engine_pin'), (d.get('snapshot_sha256') or '')[:16]+'…'))")"
note "$TRIPLET"

if [ "$SCOPE_PERSONAL" = "1" ]; then
  say "3b. Personal scope (writes under \$HOME)"
  for tool in claude cursor; do
    if [ -e "$HOME/.${tool}/skills/${SKILL_DIR}" ]; then
      note "SKIP ${tool}: $HOME/.${tool}/skills/${SKILL_DIR} already exists — not overwriting."
      note "     Remove it yourself first if you want this exercised."
      continue
    fi
    python3 "$SRC/install/${tool}.py" --repo-root "$SRC" --scope personal >/dev/null
    if [ -f "$HOME/.${tool}/skills/${SKILL_DIR}/SKILL.md" ]; then
      ok "${tool}/personal installed at ~/.${tool}/skills/${SKILL_DIR}/"
      note "     uninstall: python3 $SRC/install/${tool}.py --scope personal --uninstall"
      note "     (keep --keep so the archive survives, or re-download it to uninstall)"
    else bad "${tool}/personal: SKILL.md not at the expected destination"; install_ok=0; fi
  done
fi

# ── 4. The authoring flow, from the installed runtime ───────────────────────
say "4. Authoring flow against the pinned engine"
cp "$SRC/tests/fixtures/offline/sample_set.json" "$PROJECT/samples.json"
cd "$PROJECT"
flow_ok=1
"$PY" -m transon_authoring check-samples --samples samples.json \
  | python3 -c "import json,sys;sys.exit(0 if json.load(sys.stdin).get('ok_for_verify') else 1)" \
  && ok "check-samples: ok_for_verify" || { bad "check-samples: not ok_for_verify"; flow_ok=0; }
printf '{"$":"attr","name":"x"}' > template.json
RESULT="$("$PY" -m transon_authoring result --template template.json --samples samples.json || true)"
if printf '%s' "$RESULT" | python3 -c "
import json,sys
d=json.load(sys.stdin)
sys.exit(0 if d.get('ok') and d.get('status')=='matched' and d.get('verdict',{}).get('assurance')=='matched' else 1)" 2>/dev/null; then
  ok "result: AuthoringResult ok=true status=matched assurance=matched"
else bad "result: no matched AuthoringResult"; flow_ok=0; fi

# ── 5. Human half ───────────────────────────────────────────────────────────
say "5. MANUAL — activation in the real hosts (only you can do this)"
cat <<EOF
  A workspace with both skills installed is at:
      $PROJECT
  (add --keep so it survives this script exiting)

  1) Open Claude Code in that directory:   cd "$PROJECT" && claude
  2) Open Cursor in that directory:        cursor "$PROJECT"
  3) In EACH host, paste this prompt verbatim — it deliberately does not name
     the skill, so activation has to happen on the skill's own description:

       Author a Transon template that returns the value of the top-level key
       "x". A confirmed SampleSet for this task is at samples.json in the
       current directory — use it as the samples path.

  4) Confirm each host activates the skill and returns an AuthoringResult with
     "status": "matched".

  NOTE: the venv above is only for this script. In the hosts, the agent needs
  \`python -m transon_authoring\` on its own PATH — install it into whatever
  interpreter those hosts use:  pip install transon-authoring
EOF

CLAUDE_RES="not-recorded"; CURSOR_RES="not-recorded"
if [ -t 0 ]; then
  printf '\n  Did the skill activate and return status=matched in Claude Code? [y/n/s=skip] '
  read -r a || a=s
  case "$a" in y|Y) CLAUDE_RES="activated, status=matched";; n|N) CLAUDE_RES="FAILED";; *) CLAUDE_RES="skipped";; esac
  printf '  Did the skill activate and return status=matched in Cursor?      [y/n/s=skip] '
  read -r b || b=s
  case "$b" in y|Y) CURSOR_RES="activated, status=matched";; n|N) CURSOR_RES="FAILED";; *) CURSOR_RES="skipped";; esac
fi

# ── Report ──────────────────────────────────────────────────────────────────
AUTO="PASS"; [ "$surface_ok" = "1" ] && [ "$install_ok" = "1" ] && [ "$flow_ok" = "1" ] || AUTO="FAIL"
say "REPORT — paste this back"
cat <<EOF
--------------------------------- UC-004 ---------------------------------
date:              $(date -u +%Y-%m-%dT%H:%MZ) (UTC)
machine:           macOS ${OS_VER} (${OS_BUILD}), ${ARCH}
python:            ${PY_VER}
index:             $( [ -n "$VERSION" ] && echo "PyPI (pinned ${VERSION})" || echo "PyPI (latest)" )
installed:         transon-authoring ${TA_VER}, transon ${ENGINE_VER}
manifest triplet:  ${TRIPLET}
automated checks:  ${AUTO}  (module surface, both installers, byte-identical
                   SKILL.md, manifest, check-samples, matched AuthoringResult)
personal scope:    $( [ "$SCOPE_PERSONAL" = "1" ] && echo "exercised" || echo "not exercised (project scope only)" )
Claude Code:       ${CLAUDE_RES}
Cursor:            ${CURSOR_RES}
---------------------------------------------------------------------------
EOF
[ "$AUTO" = "PASS" ] || exit 1
