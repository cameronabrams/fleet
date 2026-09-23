#!/usr/bin/env python3
"""Print one version's section of CHANGELOG.md, for release notes.

    scripts/changelog_notes.py 0.1.0 [CHANGELOG.md]

Exits 2 when that version has no section, or when the section is empty. Both
matter: a release body built from a silently-empty extraction looks like a
release with no notes, not like a broken script, so it fails toward the
reassuring answer (docs/checks-that-reassure.md). Say so instead.
"""
import re, sys

def notes(text, version):
    """The body under `## [<version>] ...`, up to the next `## ` heading.

    Link-reference lines at the foot of the file (`[0.1.0]: https://...`) are not
    headings and would otherwise be swept into the last section."""
    lines = text.splitlines()
    start = None
    head = re.compile(r"^## \[" + re.escape(version) + r"\]")
    for i, line in enumerate(lines):
        if head.match(line):
            start = i + 1
            break
    if start is None:
        return None
    body = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        body.append(line)
    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()
    body = [l for l in body if not re.match(r"^\[[^\]]+\]:\s+https?://", l)]
    while body and not body[-1].strip():
        body.pop()
    return "\n".join(body)

def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    version = sys.argv[1].lstrip("v")
    path = sys.argv[2] if len(sys.argv) > 2 else "CHANGELOG.md"
    with open(path) as f:
        out = notes(f.read(), version)
    if out is None:
        print(f"{path}: no section for version {version}", file=sys.stderr)
        sys.exit(2)
    if not out.strip():
        print(f"{path}: the section for {version} is empty", file=sys.stderr)
        sys.exit(2)
    print(out)

if __name__ == "__main__":
    main()
