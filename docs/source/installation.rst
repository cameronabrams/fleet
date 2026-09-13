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

.. code-block:: bash

   $ mkdir -p ~/.config/fleet/briefs
   $ cp examples/fleet.example.toml ~/.config/fleet/fleet.toml        # then edit
   $ cp examples/conventions.example.md ~/.config/fleet/conventions.md

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

- Run :doc:`tools/fleetsnap` while your sessions are healthy, and check the result
  (the :doc:`fleet-snapshot skill <skills/fleet-snapshot>` says how).
- To found a fleet or add a session, follow the
  :doc:`fleet-bootstrap skill <skills/fleet-bootstrap>`.
