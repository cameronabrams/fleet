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

Other options: ``--brief PATH`` (default ``<config>/briefs/NAME.md``) and ``--wait
SECONDS`` for startup (default 60).

Preflight
---------

Blocks, and changes nothing, on any of: a missing directory, a missing brief, no
``[colors]`` entry for the name, no tmux server, a live claude already answering to
``NAME``, a pane already labelled ``@agent=NAME``, or a nonexistent
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

It does not set the session's color either: the human types ``/color <c>`` in the
pane once the session is idle.

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
prompt is answered, so ``--check`` also reads the labelled pane for the prompt.
