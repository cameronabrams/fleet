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
