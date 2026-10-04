fleetboard
==========

.. tooldoc:: fleetboard

Usage
-----

.. code-block:: text

   fleetboard                 local sources only (~0.2 s)
   fleetboard --full          also refresh cluster work and context sizes (~6 s)
   fleetboard --watch [N]     redraw every N seconds (default 15)

One screen: every session, its window, busy or idle, context size, cluster work,
and what is wrong.

What it is, and is not
----------------------

It **renders** state the fleet already derives. It declares nothing, registers no
probe, and keeps no status of its own. A design in which sessions maintain and
publish their own status was considered and refused on 2026-10-03, on the ground
that a second copy of state kept by hand inherits the defect it exists to fix —
the same reason :doc:`fleetretire`'s ledgers may assert only immutable facts.
This tool exists because that argument leaves room for exactly one thing: a
reader.

Sources, and what each costs:

.. list-table::
   :header-rows: 1

   * - source
     - cost
     - what it gives
   * - ``tmux``
     - 9 ms
     - panes, windows, the silence flag
   * - ``claude agents``
     - 177 ms
     - name, status, pid, cwd — the authority on names
   * - :doc:`fleetwatch` ``--json``
     - 3.6 s
     - cluster work, watcher liveness, delivery holes
   * - :doc:`fleetcontext` ``--json``
     - 2.2 s
     - context size per session

The two slow ones are cached under ``<state>/cache/board.json`` and shown **with
their age, never as current**: a value on this screen is evidence as of a time.

Absence is rendered ``?``, never as a pass
------------------------------------------

A board that shows green because a source failed is worse than no board, and this
one has broken that rule twice — both found after it was written, neither by its
author.

**A failed cluster query is unknown work, not no work.** ``fleetwatch`` prints a
banner and exits ``0`` when its ssh query fails. Until 2026-10-04 this tool read
``fleetwatch``'s *display table* by column position, so a failed query produced no
rows that began with a digit, and the board recorded an empty job list and drew a
blank work column for every session. An unreachable cluster looked like a calm
fleet. It now reads ``--json``, where ``cluster_ok`` is a field; a banner is not.
The same change replaced two other column parses, one of which was the only way a
job that **ended badly** reached the screen.

**A missing cache is unknown, not empty.** ``None`` means "did not ask"; ``{}``
would mean "asked, and there is nothing". Only the first is true when a cache is
absent or will not parse, and only the first draws ``?``.

Under ``--watch`` the slow sources are re-run whenever the cache is older than ten
minutes. Without that, a watched board shows one measurement forever and merely
ages it in the footer — which is how it survived its own data loss for an hour on
2026-10-03 (see below) without anyone noticing.

Why it lives here
-----------------

It was written outside this repository, in the configuration directory, and moved
in on 2026-10-04. The configuration directory holds declared things — ``fleet.toml``,
briefs, colours — and this is code that reads this app's state layout and calls two
of its tools.

The split had a cost that was paid before it was fixed. On 2026-10-03
``fleetsnap``'s housekeeping globbed ``<state>/*.json`` and renamed this tool's
cache; every value on the board went to ``?`` and stayed there for an hour. Nothing
could have caught it: the dependency crossed a repository boundary and only one
side had CI. Both halves are now in one place with a test across the seam, and the
cache owns a subdirectory rather than sitting in a shared root.
