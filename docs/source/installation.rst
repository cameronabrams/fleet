.. _installation:

Installation
============

Requirements
------------

- Python 3.11 or newer (the tools read TOML with the stdlib ``tomllib``); no other
  Python packages
- `tmux <https://github.com/tmux/tmux>`_, with the human attached to the server the
  fleet runs in
- `Claude Code <https://claude.com/claude-code>`_ (``claude`` on ``PATH``)
- Linux: the tools read ``/proc``
- For :doc:`tools/fleetwatch`: non-interactive ``ssh`` to a SLURM cluster

fleet is not installed with ``pip``. Clone it and link it into place:

.. code-block:: bash

   $ git clone https://github.com/cameronabrams/fleet.git ~/Git/fleet
   $ cd ~/Git/fleet

Configure
---------

:doc:`tools/fleetinit` creates the directory and the file, so nothing has to be
copied or edited by hand first:

.. code-block:: bash

   $ bin/fleetinit --go                              # from the shipped example
   $ cp examples/conventions.example.md ~/.config/fleet/conventions.md

**If you already run a fleet somewhere**, take your own defaults from it instead —
your name, your clusters, your thresholds, with the other fleet's roster and
history left behind:

.. code-block:: bash

   $ bin/fleetinit --from /path/to/another/fleet.toml --go

That is the whole fresh-machine path: clone this repository, fetch the
configuration you keep privately, run one command. ``install`` refuses to run
without a ``fleet.toml`` and names these commands when it does.

See :doc:`configuration` for every setting. Put the configuration directory under
version control of its own — privately; it names your hosts, accounts and sessions
and does not belong in the application repository. Set ``FLEET_CONFIG`` to use a
directory other than ``~/.config/fleet``.

Link
----

.. code-block:: bash

   $ ./install          # shows the plan, changes nothing
   $ ./install --go     # links tools into ~/bin and skills into ~/.claude/skills

``install`` creates **symlinks**, not copies, so an edit in the repository is live
at once for every session. It also links any site skills found in
``<config>/skills/``. It never silently replaces a real file: anything in the way is
moved to ``~/.local/state/fleet/displaced-<stamp>/``.

Make sure ``~/bin`` is on ``PATH``.

Next steps
----------

- :doc:`first-fleet` — roles, configuration, the first session, and the habits that
  keep a fleet alive.
- To found a fleet or add a session from inside a session, follow the
  :doc:`fleet-bootstrap skill <skills/fleet-bootstrap>`.
