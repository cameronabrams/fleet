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

The header stamp
----------------

The first line carries the **date and the time**, not the time alone::

   FLEET  2026-10-13 10:34 EDT   claude 2.1.296 installed

The board is normally read on a ``--watch`` pane that was started some time ago
and is glanced at in passing, and a bare clock cannot distinguish a board that
redrew a minute ago from one that stopped redrawing yesterday at the same hour.
That is not hypothetical here: a watcher 21h50m old presented a 22-hour-old
reading as a live fact about the fleet, and the stamp it carried was consistent
with both. The stamp is taken on each draw, for the same reason.

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
session is actually running, gently colored when the two differ.

They differ more often than it looks like they should. A session keeps running the
binary it started with, so upgrading ``claude`` changes nothing for a session
already up — and there is no sign of that from inside the session, which is why it
belongs on a board rather than in anyone's memory. :doc:`fleetupgrade` plans the
restart; this only says who needs one.

"Installed" is the version ``claude`` would start **now** — ``shutil.which`` first,
then the native ``~/.local/bin/claude``. It is deliberately not the newest release
published upstream: that needs the network, and this board's contract is local
sources. So a row matching the header means "running what a restart would give
it", not "running the newest thing that exists".

**Two install layouts, and only one names the version in a path.** The native
installer keeps versions side by side under ``.../versions/<v>/``; the npm install
puts one binary under ``node_modules/@anthropic-ai/claude-code/bin/`` and upgrades
it in place, so only the ``package.json`` beside it says which version it is. Both
are read, and a binary that answers neither way is asked directly
(``claude --version``), cached against its own size and mtime so a watched board
costs one ``stat`` per draw rather than one process launch. An in-place upgrade
changes both, so the cache invalidates exactly when it must.

A session whose binary was **replaced under it** reads ``?``. ``/proc/<pid>/exe``
says ``(deleted)``, and the package beside it now describes the new binary — so
reading it would draw a session still running the old one as already upgraded.
That is the single error this column must not make, and ``?`` is the board's word
for it. The native layout is unaffected: versions sit side by side, so a deleted
path still names the version it always named.

Both facts come from ``fleet.versions``, which :doc:`fleetupgrade` and
:doc:`fleetsnap` also read. They each derived it for themselves until 2026-10-06,
and the two copies had already drifted in shape — a regex for the component after
``versions/``, against ``basename`` of the resolved symlink. Both answer
``2.1.292`` on today's layout, and only the first still does when the binary sits
one level deeper. ``fleetsnap``'s copy was the one that mattered: its answer goes
into the manifest a restore is rebuilt from.

An unknown version prints ``?`` and is **not** colored. Coloring it would send
someone to upgrade a session over a source that failed, and an unreadable
installed version leaves every comparison unknown rather than marking the whole
fleet stale.

Pending software updates
------------------------

With an ``[updates]`` section in the configuration, the board reads a file that
some other program derives this machine's pending updates into — a root timer,
typically — and shows what it found. It **declares nothing and asks nothing**:
the same contract as every other source, and the reason a design where producers
push status was refused on 2026-10-03.

The path is configuration because it names a host, and nothing in the
application may::

   [updates]
   status = "/var/lib/<host>-updates/status.json"
   stale_hours = 36

With no such section the board says nothing about updates. That is the one
absence here which is not a failure — it was never asked for — and it is
distinguishable from a configured source that could not be read.

**Nothing renders as "up to date" except a check that ran and found nothing.**
A missing file, an unparseable one, a ``schema`` this board has not been taught,
a check that reported ``ok: false``, or one with no readable timestamp all read
as a problem. A check older than ``stale_hours`` still shows its numbers, marked
``STALE`` in words rather than left to a reader doing arithmetic on an age: a
checker that stopped running must not look like a quiet machine.

A file with **no** ``schema`` key is read as schema 1, which is the contract the
first producer was written to. Treating that absence as a mismatch would break
the feature on the day it arrived.

``reboot_needed`` is flagged in the **header**, beside the clock, rather than in
the footer with the aged sources. It is the one fact here that is true *now* and
is about the fleet rather than about a package list: a reboot ends every session
on the machine.

It is raised **even when the check itself failed**. The producer derives it
independently of the package preview — from the running kernel and ``zypper
needs-rebooting``, outside the branch that can fail — precisely so that it
survives one. Withholding it on ``ok: false`` would hide a true, current,
fleet-ending fact at exactly the moment the other half of the check broke. Only
an *unknown* source withholds it, because there the document could not be
interpreted at all.

The kernel is read live, not from that document
-----------------------------------------------

``fleet.kernels`` compares the running kernel against the newest one installed,
on every draw, from the filesystem and with no subprocess. The reason is timing
rather than purity. The update document is written by a **daily timer**, while
this fact flips the moment a ``zypper dup`` unpacks a kernel: on the machine this
was written for a kernel landed at 08:42 with the next check due at 06:21 the
following morning — twenty-two hours in which a board reading only the document
would have said nothing. It is also the direction a stale document gets wrong in
the *reassuring* sense once the reboot finally happens, and an alarm nothing can
clear is how a true one gets missed.

When they differ, the header carries both releases and how long the wait has run:

.. code-block:: text

   REBOOT NEEDED (kernel 7.2.11 -> 7.2.14, waiting 72h)

Only the part that **differs**. The releases are ``7.2.11-1-default`` and
``7.2.14-1-default``; the shared tail carries nothing, and this header is already
long enough to wrap a narrow pane — a reminder that wraps is a reminder read as
noise. Shared components only, never a fixed number of them: when the *flavor*
differs, as in ``7.2.11-1-default`` against ``7.2.11-1-rt``, that is the whole
point of the line and both releases print in full.

The wait is the number that actually decides something. An owner reading this
already knows a reboot is owed; what they do not know is how long they have been
putting it off — and the reboot usually waits on whatever the fleet is in the
middle of, so it is owed in days rather than minutes.

**An installed kernel is a directory under** ``/lib/modules`` **that contains a
kernel image.** The directory alone will not do:
``/lib/modules/7.0.3-1-default`` on this machine is owned by no package at all
(checked with ``rpm -qf``), left behind when its kernel went. A
newest-directory-wins scan reads a leftover as installed, and the dangerous
leftover is a *newer* one — it produces a permanent warning about a reboot that
would change nothing, which is the kind of alarm that trains an owner to ignore
the real one. Requiring the image costs one ``stat`` and no knowledge of the
package manager.

A running kernel that is **not installed at all** also reads as pending: it has
been removed from under the machine, and a reboot is equally the answer.
Unreadable is ``kernel: ?`` in the header, never silence — this is read locally,
so failing means something odd about the machine itself, and omitting it reads
exactly like a machine with nothing to report.

Whose fleet a pane is in
------------------------

Two fleets can share a machine. A pane labeled with **another** fleet's
``@fleet`` is listed separately as *not this fleet* and takes no part in anything
else the board says. Since 2026-10-20 a pane with **no** ``@fleet`` is treated the
same way: a pane no tool has stamped is a pane no tool is known to own.

That is the opposite of how it shipped, and the order mattered more than the
answer. Zero panes carried ``@fleet`` when the label landed, so excluding the
unlabeled would have emptied every tool at once — ``fleetsnap`` seeing no fleet,
``fleetupgrade`` nothing to roll. The permissive rule shipped first, every pane
was stamped by :doc:`fleetinit` ``--label-panes``, and the flip came after, on a
precondition checked against the **configured** name rather than against the panes
alone: 15 of 15 labeled, 0 unlabeled, and ``[fleet].name`` equal to the label they
all carried. Unanimous panes still vanish if the configuration disagrees with all
of them.

With no name of its own, a fleet counts everything as its own: one that has never
been named cannot say which panes are not its, and guessing in the excluding
direction would hide real members. That is the one branch that still fails toward
inclusion, and it is reachable only before :doc:`fleetinit` has run.

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
briefs, colors — and this is code that reads this app's state layout and calls two
of its tools.

The split had a cost that was paid before it was fixed. On 2026-10-03
``fleetsnap``'s housekeeping globbed ``<state>/*.json`` and renamed this tool's
cache; every value on the board went to ``?`` and stayed there for an hour. Nothing
could have caught it: the dependency crossed a repository boundary and only one
side had CI. Both halves are now in one place with a test across the seam, and the
cache owns a subdirectory rather than sitting in a shared root.
