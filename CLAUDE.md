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
- Run the suite once with no configuration before pushing a test change --
  `env -u FLEET_CONFIG HOME=<empty dir> python3 -m unittest discover -s tests -t .`
  A test that reads the real `~/.config/fleet` passes on a machine that has one
  and nowhere else, which is the environment the rule exists for.
- Read-only by default; anything that changes tmux or launches sessions previews
  unless `--go`. Never answer the folder-trust prompt, in code or by hand.
- Nothing personal in this repo: no people, hosts, accounts or project sessions.
  Those belong in configuration (`~/.config/fleet`), never here.
