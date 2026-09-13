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

Building these docs
-------------------

.. code-block:: bash

   $ pip install -r docs/requirements.txt
   $ cd docs && make html        # output in docs/build/html

Read the Docs builds with warnings as errors (``.readthedocs.yaml``).
