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
   * - ``/proc`` + ``readlink``
     - 0 ms
     - which binary each session runs, and which one is installed

The two slow ones are cached under ``<state>/cache/board.json`` and shown **with
their age, never as current**: a value on this screen is evidence as of a time.

The directory column, and parked sessions
-----------------------------------------

Each row carries the session's working directory, from ``claude agents`` — the only
source here that knows it. ``$HOME`` shows as ``~``, and a path too long for the
column is cut from the **left**: paths are distinctive at the end, so a right-hand
cut would make the column widest exactly where it stops telling two sessions apart.
The width follows the terminal, between 14 and 42 characters.

Below the table, under a rule, are the sessions declared **parked** in
``[parked.<name>]`` (:doc:`../configuration`), with their directory and the date
they were parked. Parked is a *declaration*, not an observation, which is why it can
be shown for a session with no process and no pane — and why those rows sit under a
rule rather than at the bottom of the same list: they are a different kind of thing.

A parked row carries no state, version, context or work. Those are runtime and it
has none; printing ``?`` in them would say they were unknown, which is this page's
rule about ``?`` read backwards. **Retired** sessions are not listed at all — they
are not coming back, and a board is about what might.

A name that is both running and declared parked is marked ``ALSO RUNNING``. That is
two sources disagreeing, and drawing it in both places without a word would let an
undeclared unpark look like an ordinary board.

The configuration is **re-read on every draw**, not once at startup. ``--watch``
redraws for as long as the board is left up, and parking is a declaration a human
changes underneath it. Until 2026-10-09 a watcher held the configuration it was
started with: one 21h50m old still listed an unparked session under ``parked`` and
marked it ``ALSO RUNNING`` — a disagreement between a live reading of tmux and a
22-hour-old reading of a file, both of them the board's own. **A check that reports
its own staleness as the fleet's is worse than no check**, because it looks like
evidence about something else. The slow sources are cached on purpose and shown
with their age; a small TOML file is neither slow nor observed, so it gets neither
treatment. A configuration caught half-saved reads as unreadable and says so,
rather than taking the screen down.

The version column
------------------

The header states the **installed** version once; each row shows the version that
session is actually running, gently coloured when the two differ.

They differ more often than it looks like they should. A session keeps running the
binary it started with, so upgrading ``claude`` changes nothing for a session
already up — and there is no sign of that from inside the session, which is why it
belongs on a board rather than in anyone's memory. :doc:`fleetupgrade` plans the
restart; this only says who needs one.

"Installed" is the version ``claude`` would start **now**, read by resolving
``~/.local/bin/claude``. It is deliberately not the newest release published
upstream: that needs the network, and this board's contract is local sources. So
a row matching the header means "running what a restart would give it", not
"running the newest thing that exists".

Both facts come from ``fleet.versions``, which :doc:`fleetupgrade` and
:doc:`fleetsnap` also read. They each derived it for themselves until 2026-10-06,
and the two copies had already drifted in shape — a regex for the component after
``versions/``, against ``basename`` of the resolved symlink. Both answer
``2.1.292`` on today's layout, and only the first still does when the binary sits
one level deeper. ``fleetsnap``'s copy was the one that mattered: its answer goes
into the manifest a restore is rebuilt from.

An unknown version prints ``?`` and is **not** coloured. Colouring it would send
someone to upgrade a session over a source that failed, and an unreadable
installed version leaves every comparison unknown rather than marking the whole
fleet stale.

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
