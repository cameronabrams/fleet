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
- Read-only by default; anything that changes tmux or launches sessions previews
  unless `--go`. Never answer the folder-trust prompt, in code or by hand.
- Nothing personal in this repo: no people, hosts, accounts or project sessions.
  Those belong in configuration (`~/.config/fleet`), never here.
