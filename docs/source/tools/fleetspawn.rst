fleetspawn
==========

.. tooldoc:: fleetspawn

Usage
-----

.. code-block:: text

   fleetspawn NAME DIR --beside PANE [--split v|h] [--go]
   fleetspawn NAME DIR --window TITLE [--go]
   fleetspawn --check NAME DIR
   fleetspawn NAME DIR --beside PANE --resume UUID [--go]

``--socket NAME`` builds on the tmux server at that socket instead of the default
one, and ``$TMUX`` is never inherited so a run from inside a pane cannot silently
build on that pane's server. With ``TMUX_TMPDIR`` pointed at a scratch directory
the whole run is isolated — **which is how to try this tool out without spawning
into the live fleet.** Without it, exercising ``--go`` by hand put two real
sessions into a fleet they did not belong to, where every other tool counted them
as members.

Scaffolding, so the refusals become offers
------------------------------------------

Preflight already names every missing piece precisely and then refuses. These
make it offer instead:

``--color C``
   declares ``NAME = "C"`` under ``[colors]`` if it is not declared yet. The human
   still chooses — they typed it here — and the tool only writes it where the
   declaration lives. **Appended and verified, never rewritten**: see
   ``fleet.config.declare``, which refuses a file that does not already parse,
   refuses unless exactly one line is exactly ``[colors]``, refuses to change a
   declaration that exists, and proves the result parses in a temporary file
   before it replaces anything. A duplicate key would otherwise stop every tool at
   once, since each parses this file when it runs.

``--create-dir``
   creates ``DIR``. The folder-trust prompt still stops the spawn afterwards, so
   the grant stays the human's.

``--brief-from-example``
   copies the brief template into place and **stops**. It does not spawn.
   ``[spawn].first_prompt`` tells a session to read its brief and follow it, so a
   template brief is a session told that its role is to fill itself in — and that
   fails *quietly*, as a session behaving plausibly and owning nothing in
   particular, where a missing brief fails loudly at preflight. **Scaffolding the
   file is a kindness; writing its content is the thing the refusal exists to
   force.**

Scaffolding runs before preflight, so preflight judges what will exist rather than
what did — and every read of the color re-loads the configuration rather than using
the copy from import, because ``--color`` may have written it seconds earlier.

Other options: ``--brief PATH`` (default ``<config>/briefs/NAME.md``), ``--wait
SECONDS`` for startup (default 60), ``--color-wait SECONDS`` for the pane to go idle
before ``/color`` is typed (default 300), and ``--no-color`` to leave the color to
be typed by hand.

Preflight
---------

Blocks, and changes nothing, on any of: a missing directory, a missing brief, no
``[colors]`` entry for the name, no tmux server, a live claude already answering to
``NAME``, a pane already labeled ``@agent=NAME``, or a nonexistent
``--beside`` pane. Fix the cause; do not work around it.

A live claude answers to the name in its transcript's last ``agent-name`` record,
else to ``--name`` in its process arguments: ``/rename`` changes the first and not
the second. ``--check`` matches the same way.

It also blocks on a name in ``[retired]`` (remove the entry to reuse the name for a
new session), on a name in ``[parked]`` unless ``--resume`` gives its recorded
uuid, and on ``--resume`` with a transcript recorded for a different name.

``--resume UUID`` launches ``claude --name NAME --resume UUID`` with no first
prompt — the way a parked session (:doc:`fleetretire`) comes back. Delete its
``[parked]`` entry afterwards.

With ``--go``
-------------

Creates the pane (split beside ``PANE``, or a new window with automatic-rename
off), sets ``@agent`` and the pane title, and types
``[spawn].env claude --name NAME '<first prompt>'``. It then watches until a
process with that name runs in ``DIR`` **and** the session is up, or the
folder-trust prompt appears.

Two things count as "up", and either will do:

* the session is listed by ``claude agents`` — the structured source, which keeps
  saying so for as long as it is true;
* the version banner is on the pane — drawn only once a session is running.

The banner was the only signal until 2026-10-07, and it is drawn **once**: the
session's own first output scrolls it away. So the signal is destroyed by the very
thing it reports, and a session that starts and gets to work *faster* is more
likely to be reported as never having started. A fresh spawn usually wins that
race, because it sits idle while its first prompt is read. A ``--resume`` always
loses it — replaying the conversation fills the pane before the first poll — so
every unpark reported ``TIMED OUT`` while being up and correct. Raising ``--wait``
could not help, and 180 s failed where 60 s had succeeded: **a marker that is
already gone does not arrive by waiting.**

The banner is kept, because it still means what it meant and is the fallback when
``claude agents`` cannot be read. The directory is checked against the process, not
against ``claude agents``.

It **never answers the folder-trust prompt.** Trusting a directory grants an agent
read, edit and execute there; that is the human's decision.

The color
---------

It **applies the declared color itself**, and did not until 2026-10-13. The color
was declared in ``[colors]``, validated by preflight — which refuses to spawn
without it — and then left for someone to remember to type. A session that misses
it looks like somebody else's window on every board that reads the label.

claude has no ``--color`` flag, so the color can only be typed, and the old comment
gave a real reason not to: keys sent into a session still working its first prompt
arrive corrupted or land as prompt text (observed 2026-09-07). That hazard is now
**solved rather than avoided**. It waits for the pane to go idle by
``fleet.panes.screen_state`` — the same reader :doc:`fleetnudge` uses, so "idle"
means the same to both: not mid-turn, no dialog, no draft already in the input line
— and types through ``fleet.panes.type_line``, which reads the input line back and
confirms it holds exactly the intended text before Enter, clearing it if it does
not.

**Success is the session's own ``agent-color`` record**, the one :doc:`fleetsnap`
reads — not the keystrokes going out. Sending keys cannot fail, so it is not
evidence that anything was applied.

The handle for that record comes from the session's own registry entry
(``~/.claude/sessions/<pid>.json``), not from the scratchpad path of a child
process. A session has a live child only while it is mid-tool-call, which is
precisely what this has just waited for it *not* to be: measured across 14 live
sessions on 2026-10-13, the registry answered for all 14 and the descendant walk
for one — the only session doing work at that moment. The walk stays as the
fallback.

A color that will not apply is **reported with the line to type, and does not fail
the spawn**. The session is up, in the right directory, with the right brief; only
its label is wrong, and exiting non-zero invites a retry that would respawn a live
session. A session already carrying the declared color — a ``--resume`` carries it
forward — is not typed into at all.

After a ``/clear`` or a restart it is yours again: a ``/clear`` drops the live color
and keeps the name, and nothing goes back through ``fleetspawn`` at that point.
:doc:`fleetsnap` and :doc:`fleetupgrade` flag the difference and print the command.

Every launch is an adoption, and it is logged
---------------------------------------------

There is no version argument and none is wanted. The command is plain ``claude``,
so a spawn — and an **unpark** — puts a session onto whatever ``~/.local/bin/claude``
resolves to at that moment.

Until 2026-10-16 that happened invisibly, and it was not a rare path: the fleet's
entire version spread was unparks rather than rolls. The auto-roll log recorded
``rolled=none skipped=15`` at 09:50 that morning and a session went onto an
18-hour-old release at 09:51, by a route the log could not see.

So ``--go`` appends one line to ``<state>/autoroll.log``::

   2026-10-16T09:51:04-0400  installed=2.1.301 rolled=lib-repo from=parked to=2.1.301 note=unpark

It is the auto-roll's own log and not a new one, deliberately: a second file would
have said ``rolled=none`` twice. ``from`` is ``parked`` for an unpark and ``new``
for a fresh spawn — ``parked`` is honest rather than lazy, since a parked session
is not running and nothing here can know which binary it was on.

``to`` is read from the **running process**, not from what was installed when the
command was composed: a session takes up to ``--wait`` seconds to come up, and a
human can upgrade in between. An unreadable version is written ``?``.

**The adoption is recorded, not gated.** A park and unpark is a human act with its
own reasons, and making it wait on :doc:`fleetupgrade`'s on-disk window would be
the wrong trade. A log line that cannot be written is printed and does not fail the
spawn — the session is up, and the obvious repair for a failed spawn is to launch
again, which here would start a second one.

Exit codes
----------

.. list-table::
   :widths: 10 90

   * - ``0``
     - live (with ``--check``: one process, right directory)
   * - ``1``
     - ``--check``: not running, wrong directory, or several processes with the name
   * - ``2``
     - blocked by preflight
   * - ``3``
     - stopped at the folder-trust prompt (with ``--check``: the pane still shows it)
   * - ``4``
     - timed out waiting for startup
   * - ``5``
     - stopped at the resume-mode prompt (summary or full is the human's choice)

A process with the right name in the right directory exists *before* the trust
prompt is answered, so ``--check`` also reads the labeled pane for the prompt.
