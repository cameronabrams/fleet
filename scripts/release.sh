#!/usr/bin/env bash
# Release fleet at a given version.
#
# Usage: ./scripts/release.sh <version>
# Example: ./scripts/release.sh 0.1.0
#
# Prerequisites (checked automatically):
#   - Working tree clean, on main, in sync with origin
#   - CHANGELOG.md has an "## [Unreleased]" section with something under it
#   - The tag does not already exist, locally or on origin
#   - The full test suite passes here
#
# What it does:
#   1. Rotates CHANGELOG.md: [Unreleased] -> [<version>] - <date>, and inserts a
#      fresh empty [Unreleased] above it
#   2. Writes __version__ in fleet/__init__.py
#   3. Commits both as "Release v<version>"
#   4. Creates tag v<version>
#   5. Pushes the commit and the tag to origin
#
# The pushed tag triggers .github/workflows/release.yaml, which re-runs the suite
# and creates a GitHub Release with the notes for that version. PUSHING THE TAG
# IS WHAT PUBLISHES: it is the step that needs a human's decision, not a session's.
#
# Unlike the other repositories in this group there is no package to build. fleet
# is installed by `./install`, which symlinks the working tree, so a tag names a
# commit rather than an artifact. That is the whole point of one: `git pull` is
# the update path, and without a tag nobody outside can say which fleet they run.

set -euo pipefail

VERSION="${1:?Usage: scripts/release.sh <version>  (e.g. 0.1.0)}"
VERSION="${VERSION#v}"
TODAY="$(date +%Y-%m-%d)"

if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([-.][0-9A-Za-z.]+)?$ ]]; then
    echo "ERROR: '$VERSION' is not a semantic version (e.g. 0.1.0)" >&2
    exit 1
fi

# ── Preconditions ─────────────────────────────────────────────────────────────

cd "$(git rev-parse --show-toplevel)"

if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "ERROR: working tree has uncommitted changes — commit or stash them first" >&2
    exit 1
fi

BRANCH="$(git branch --show-current)"
if [ "$BRANCH" != "main" ]; then
    echo "ERROR: must be on main branch (currently on '$BRANCH')" >&2
    exit 1
fi

git fetch --quiet origin main
if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]; then
    echo "ERROR: main and origin/main differ — push or pull first, so the tag names" >&2
    echo "       a commit that exists on origin" >&2
    exit 1
fi

if ! grep -q "^## \[Unreleased\]" CHANGELOG.md; then
    echo "ERROR: no '## [Unreleased]' section found in CHANGELOG.md" >&2
    exit 1
fi

if git rev-parse "v$VERSION" >/dev/null 2>&1; then
    echo "ERROR: tag v$VERSION already exists locally" >&2
    exit 1
fi

if git ls-remote --tags origin "refs/tags/v$VERSION" | grep -q .; then
    echo "ERROR: tag v$VERSION already exists on origin" >&2
    exit 1
fi

# ── Tests ─────────────────────────────────────────────────────────────────────
# CI runs these too, but CI runs them AFTER the tag is pushed, and a tag is the
# one thing here that cannot be taken back quietly. Stdlib only, ~8 seconds.
#   - Skip (you have decided a failure is not a blocker): SKIP_TESTS=1
if [ "${SKIP_TESTS:-0}" != "1" ]; then
    echo "Running the test suite (skip with SKIP_TESTS=1)..."
    if ! PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -t . >/dev/null; then
        echo "ERROR: tests failed; not releasing." >&2
        exit 1
    fi
fi

# ── CHANGELOG rotation ────────────────────────────────────────────────────────

# An [Unreleased] section with nothing under it produces a release whose notes are
# blank -- which reads as "this release changed nothing" rather than "the section
# was never written".
if ! python3 - "$VERSION" <<'PYEOF'
import sys
sys.path.insert(0, "scripts")
from changelog_notes import notes
body = notes(open("CHANGELOG.md").read(), "Unreleased")
if not (body or "").strip():
    sys.exit("ERROR: '## [Unreleased]' is empty — write the notes for this release first")
PYEOF
then
    exit 1
fi

echo "Rotating CHANGELOG.md: [Unreleased] -> [$VERSION] - $TODAY"
python3 - "$VERSION" "$TODAY" <<'PYEOF'
import sys
version, today = sys.argv[1], sys.argv[2]
p = "CHANGELOG.md"
s = open(p).read()
old = "## [Unreleased]"
assert s.count(old) == 1, f"expected exactly one '{old}' in {p}"
open(p, "w").write(s.replace(old, f"## [Unreleased]\n\n## [{version}] - {today}", 1))
PYEOF

# ── Version bump ──────────────────────────────────────────────────────────────

echo "Setting fleet/__init__.py __version__ to $VERSION"
python3 - "$VERSION" <<'PYEOF'
import re, sys
version = sys.argv[1]
p = "fleet/__init__.py"
s = open(p).read()
new, n = re.subn(r'^__version__ = ".*"$', f'__version__ = "{version}"', s, flags=re.M)
if n != 1:
    sys.exit(f"ERROR: expected exactly one __version__ line in {p}, found {n}")
open(p, "w").write(new)
PYEOF

ACTUAL="$(python3 -c 'import fleet; print(fleet.__version__)')"
if [ "$ACTUAL" != "$VERSION" ]; then
    echo "ERROR: fleet.__version__ is '$ACTUAL' after the bump — check the file" >&2
    git checkout fleet/__init__.py CHANGELOG.md
    exit 1
fi

# The guard that ties the two together, run after both edits rather than before.
if ! PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_version >/dev/null 2>&1; then
    echo "ERROR: tests/test_version.py fails after the bump — CHANGELOG and" >&2
    echo "       fleet.__version__ disagree. Nothing has been committed." >&2
    git checkout fleet/__init__.py CHANGELOG.md
    exit 1
fi

# ── Commit, tag, push ─────────────────────────────────────────────────────────

git add fleet/__init__.py CHANGELOG.md
git commit -m "Release v$VERSION"
git tag -a "v$VERSION" -m "fleet v$VERSION"

echo "Pushing commit and tag v$VERSION to origin..."
git push origin main
git push origin "v$VERSION"

echo ""
echo "Done. release.yaml will re-run the suite and create the GitHub Release."
echo "  https://github.com/cameronabrams/fleet/releases/tag/v$VERSION"
