.. _testing:

Testing and contributing
========================

Run the tests from the repository root:

.. code-block:: bash

   $ python3 -m unittest discover -s tests -t .

The suite uses only the standard library, like the tools. Tools in ``bin/`` have no
``.py`` extension; ``tests/support.py`` loads them as modules with ``FLEET_CONFIG``
pointed at a throwaway configuration. No test reads or writes the real
configuration, the real state directory, or a real tmux server — tests that need
tmux use ``TMUX_TMPDIR`` with a short path.

Rules for changes
-----------------

- **Stdlib only**, Python 3.11+. The tools are the recovery path; nothing may need a
  package installed first.
- **Read-only by default.** Anything that changes tmux or launches a session prints a
  plan unless given ``--go``. Never answer the folder-trust prompt, in code or by
  hand.
- **A test for a bug must fail on the code before the fix.** When a new test passes
  the first time, break the guard it covers and confirm it fails. Do that with
  ``PYTHONDONTWRITEBYTECODE=1`` and no ``__pycache__``: a cached module can outlive
  an edit-and-revert made within the same second. See
  :doc:`checks-that-reassure` for why.
- **Nothing personal in the repository** — no people, hosts, accounts or project
  sessions. Those belong in configuration.

Continuous integration
----------------------

``.github/workflows/tests.yml`` runs the same command on Python 3.11, 3.12 and 3.13 for
every push to ``main`` and every pull request. The matrix is the "Python 3.11+" claim,
checked rather than asserted; 3.11 is the floor because the tools read TOML with
``tomllib``.

Nothing is installed with ``pip``. If a step ever needs a package, that is the finding,
not a fix. ``tmux`` is installed explicitly rather than taken from the runner image, so
the suite does not quietly change shape when that image does.

One step runs **before** the tests and refuses to report a pass below 300 discovered
tests:

.. code-block:: python

   n = unittest.defaultTestLoader.discover("tests", top_level_dir=".").countTestCases()
   if n < 300:
       sys.exit(f"only {n} tests discovered: refusing to report a pass")

A green badge over no tests is the shape :doc:`checks-that-reassure` is about — a check
whose wrong answer is the reassuring one. It is not hypothetical: over an empty suite
``unittest discover`` exits **0 on 3.11** and 5 on 3.12 and 3.13 (measured 2026-09-20,
the same empty suite each time), so on the floor version of this matrix, and only there,
an empty suite passes. The floor also catches what no exit code catches — a suite that
still runs but has *shrunk*. It is a lower bound rather than a recorded count, so it can
only go stale in the safe direction.

Releasing
---------

.. code-block:: bash

   $ ./scripts/release.sh 0.2.0

There is no package to build and no build step: ``./install`` symlinks the working
tree, so a release names a **commit**, not an artifact. That is still worth having
once other people can clone it — ``git pull`` is the update path, and without a tag
nobody can say which fleet they are running, or pin one.

The script refuses to proceed on a dirty tree, a branch other than ``main``, a
``main`` that differs from ``origin/main``, a tag that already exists, an empty
``[Unreleased]`` section, or a failing suite. Then it rotates the changelog, writes
``__version__``, commits, tags and pushes.

**Pushing the tag is what publishes**, which is why it is the one step that needs a
person rather than a session.

The version is written in exactly one place, ``fleet/__init__.py``.
``docs/source/conf.py`` imports it and ``tests/test_version.py`` checks it against
the newest entry in ``CHANGELOG.md``: a version bumped in one place and not the
other imports fine, passes everything, and leaves the docs and the tag quietly
disagreeing — so the two are tied together by a test rather than by care.

The pushed tag triggers ``.github/workflows/release.yaml``, which re-runs the suite
on all three Pythons, refuses a tag that disagrees with ``fleet.__version__``, and
creates the GitHub Release with that version's changelog section as its notes. The
extractor exits non-zero on a missing or empty section instead of printing nothing:
an empty release body reads as "this release changed nothing", not as "the script
broke".

Building these docs
-------------------

.. code-block:: bash

   $ pip install -r docs/requirements.txt
   $ cd docs && make html        # output in docs/build/html

Read the Docs builds with warnings as errors (``.readthedocs.yaml``).
