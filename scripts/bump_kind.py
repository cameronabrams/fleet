#!/usr/bin/env python3
"""Which component changed between two versions: major, minor, patch or same.

Used by scripts/release.sh to name the bump before asking you to confirm it.
Knowing WHICH it is does not decide whether it is right -- that is the judgement
the confirmation exists for -- but a number shown beside the entries is harder to
pick absent-mindedly than one typed on a command line.
"""
import sys

def kind(old, new):
    def parts(v):
        p = [int(x) for x in v.split("+")[0].split("-")[0].split(".")[:3]]
        return (p + [0, 0, 0])[:3]
    o, n = parts(old), parts(new)
    if n[0] != o[0]:
        return "MAJOR"
    if n[1] != o[1]:
        return "MINOR"
    if n[2] != o[2]:
        return "PATCH"
    return "SAME"

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    print(kind(sys.argv[1], sys.argv[2]))
