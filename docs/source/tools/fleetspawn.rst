fleetspawn
==========

.. tooldoc:: fleetspawn

Usage
-----

.. code-block:: text

   fleetspawn NAME DIR --fleet GROUP --beside PANE [--split v|h] [--go]
   fleetspawn NAME DIR --fleet GROUP --window TITLE [--go]
   fleetspawn --check NAME DIR
   fleetspawn NAME DIR --fleet GROUP --beside PANE --resume UUID [--go]

Other options: ``--brief PATH`` (default ``<config>/briefs/NAME.md``) and ``--wait
SECONDS`` for startup (default 60).

Preflight
---------

Blocks, and changes nothing, on any of: a missing directory, a missing brief, no
``[colors]`` entry for the name, no tmux server, a live claude already answering to
``NAME``, a pane already labelled ``@repo=NAME``, or a nonexistent
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
off), sets ``@repo``, ``@fleet`` and the pane title, and types
``[spawn].env claude --name NAME '<first prompt>'``. It then watches the pane until
the version banner is drawn and a process with that name runs in ``DIR``, or the
folder-trust prompt appears.

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
