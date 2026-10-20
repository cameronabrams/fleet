# Working on the fleet application

- Stdlib only, Python 3.11+ (`tomllib`). These tools are the recovery path after a
  power cycle; nothing may need a package installed first. That includes tests.
- Run the tests from the repo root:

      python3 -m unittest discover -s tests -t .

  Tools under `bin/` have no `.py` extension; `tests/support.py` loads them as
  modules with `FLEET_CONFIG` pointed at a throwaway configuration. No test may
  read or write the real configuration, the real state directory, or a real tmux
  server (use `TMUX_TMPDIR` with a short path; socket paths have a length limit).
- A test for a bug must fail on the code before the fix. When a new test passes
  first time, break the guard it covers and confirm it fails
  (`docs/checks-that-reassure.md`). Run those checks with
  `PYTHONDONTWRITEBYTECODE=1` and no `__pycache__` present: a cached module can
  outlive an edit-and-revert made within the same second.
- **Break the guard in a throwaway copy, never in the working tree.** These tools
  are normally installed as symlinks into the tree, and at least one is driven by
  a timer, so a file broken for the two seconds of a test run is the installed
  tool for those two seconds. Copy the working tree's own files AS THEY ARE:

      git ls-files -z --cached --others --exclude-standard \
        | tar --null -T - -cf - | tar -x -C <scratch>/breakroom

  then run the suite from there; it resolves `bin/` from wherever it is invoked.
  **Every flag earns its place, and two were learned by the copy being wrong.**
  Not `git archive HEAD`, which ships the committed tree when the change under
  test is the uncommitted one. And not `git ls-files` alone, which lists only
  TRACKED files -- so a brand-new test file is missing from the copy and the
  suite fails to import it. Both mistakes copy everything except the thing being
  proved.
- Run the suite BOTH ways before pushing a test change, because each way hides
  what the other catches:

      python3 -m unittest discover -s tests -t .                      # in place
      env -u FLEET_CONFIG HOME=<empty dir> python3 -m unittest discover -s tests -t .

  With the real `HOME`, a test that reads `~/.config/fleet` passes here and
  nowhere else. With an empty one, `~/.local/share/claude/versions` is empty too
  -- so every test of the version pinning fell back to bare `claude` and passed,
  **and so did CI, which has no claude installed at all.** Thirty-one tests were
  green in both places and red in the only one that runs the suite in place:
  `scripts/release.sh`, which refused the release. A test must say which binary
  it expects rather than inheriting the host's.
- Read-only by default; anything that changes tmux or launches sessions previews
  unless `--go`. Never answer the folder-trust prompt, in code or by hand.
- **Try a tool that creates panes or launches sessions on a throwaway tmux
  server, never the live one.** `fleetspawn` and `fleetrestore` take `--socket`,
  and with `TMUX_TMPDIR` pointed at a scratch directory the whole run is isolated
  -- which is how `tests/test_fleetrestore_e2e.py` builds a real fleet safely.
  Exercising `fleetspawn --go` by hand against the default server on 2026-10-20
  left two real sessions in the fleet, which every other tool then counted as
  members: `fleetsnap` demanded a brief and a colour for them and the auto-roll
  would have offered to roll one. `--go` previewing is not protection when the
  thing you are testing is what `--go` does.
- Nothing personal in this repo: no people, hosts, accounts or project sessions.
  Those belong in configuration (`~/.config/fleet`), never here. **This repository
  is public**, and it applies to tracked prose as much as to code -- a CHANGELOG
  entry, a docstring, a test fixture, an example log line. Writing a real session
  name because it makes a bug concrete is the trade the rule exists to forbid.
  Use the placeholder vocabulary the tests already use: `alpha`, `beta`, `gamma`
  for sessions, `-home-u-...` for project slugs, `198.51.100.23` (RFC 5737) for an
  address. Where a story needs two names, say what they were FOR -- `site-repo`,
  `sim-study`, `oldname` and `newname` for a rename -- never what they were.
  No automated check can catch this, because the repository must not contain the
  list of names it would check against; `git diff` before a push is the check.
