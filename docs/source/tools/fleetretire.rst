fleetretire
===========

.. tooldoc:: fleetretire

Usage
-----

.. code-block:: text

   fleetretire NAME --park|--retire [--go] [--allow-dirty] [--allow-references]
               [--note TEXT] [--wait SECONDS]

**Park** when the role continues later; **retire** when it is finished. The
:doc:`fleet-bootstrap skill <../skills/fleet-bootstrap>` (section 4) covers the
decision and the steps around the tool.

Preflight
---------

Blocks, and changes nothing, on any of:

- no claude process answering to ``NAME``, or more than one. The name is the
  transcript's last ``agent-name`` record, else ``--name`` in the process arguments,
  so a session renamed with ``/rename`` is found under its new name; a process
  launched ``--name NAME`` but renamed since is not matched, and a note says so
- a resume uuid that is not ``verified:`` (resolved as :doc:`fleetsnap` does)
- the session's transcript already listed in ``[parked]`` or ``[retired]``
- the pane busy (``esc to interrupt`` in its footer), at the folder-trust prompt,
  at the background-work dialog, showing no input line at all, or **holding text
  somebody typed and has not sent** (see below)
- child processes of the claude process
- a live registered watcher for the session (:doc:`fleetregister`)
- cluster work the session owns or watches, or a failed cluster query
  (:doc:`fleetwatch`); skipped, with a note, when no cluster is configured
- uncommitted or unpushed work in its git working directory, unless
  ``--allow-dirty`` — or reported only, when another session shares the directory
- **retire only:** other briefs naming the session as a whole word, unless
  ``--allow-references``
- a background session already answering to the name (from ``claude agents --json``;
  if that cannot be read, a note says background sessions were not checked)
- the session being the one running the tool

A draft in the input line is somebody's unsent sentence
------------------------------------------------------

Until 2026-11-09 the pre-check read the pane with three substring searches of its
own — trust prompt, background dialog, busy footer — and had no branch for the
input line at all, while ``fleet.panes.screen_state`` answered the whole question
in six states and :doc:`fleetcontext` already used it.

So a draft passed the pre-check clean, and then step 2 below typed ``/exit`` onto
the end of it. The readback could not match, ``fleet.panes.clear_input`` sent
``C-u`` and up to 200 backspaces **over the human's own unsent text**, and the
message that came back blamed a terminal reply. The session was not stopped and
the resume recipe was left pending. It now blocks with exit ``2`` before a single
key is sent.

The pane is captured with ``capture-pane -p -e``, and the ``-e`` is the whole
difference between this check and a worse bug. Claude Code draws a **prompt
suggestion** in an empty input line as dim text (SGR 2); typed text is drawn at
normal intensity. Strip the attributes and a suggestion and a draft arrive as the
same string, so the same check on a plain capture would refuse to retire any
session with a suggestion on its prompt — which is how this was first reported,
from the other side, as a false block.

A running turn is still reported ahead of the draft under it. Both can be true at
once — somebody typing the next message while this one answers — and "wait until it
is idle" is the instruction that resolves that screen, where clearing the draft
would delete what they typed and leave the turn running.

With ``--go``
-------------

1. Writes the resume recipe — ``cd <dir> && [spawn].env claude --name NAME
   --resume <uuid>``, and the ``fleetspawn --resume`` form — keeping the previous
   ledger's content below it, to ``<ledger>.pending``, and confirms it holds the uuid
   **before** anything is stopped. Only once the stop is confirmed does it become
   ``<state>/rearm/NAME.md`` (park) or ``<state>/rearm/retired/NAME.md`` (retire); on
   any other outcome the ledger is left as it was.
2. Types ``/exit`` into the pane without Enter, checks that the input line reads
   exactly ``/exit`` (a terminal reply can corrupt keys; if it does not, the line is
   cleared and nothing is sent), then sends Enter.
3. Waits for the session to **stop**: the process exits (same pid and start time
   gone) *and* it did not move to the background. ``/exit`` can background a session
   instead of stopping it (observed on 2.1.272): the pane says ``backgrounded · <id>``
   and a fork carries on under a new pid. The tool checks the pane and
   ``claude agents --json``, and on either sign stops with exit ``3``.
4. Closes the pane, unless it is the only pane in its window.
5. Prints the ``fleet.toml`` entry for the configuration owner.

Exit codes
----------

.. list-table::
   :widths: 10 90

   * - ``0``
     - done, or a plan with no blocks
   * - ``2``
     - blocked by preflight
   * - ``3``
     - not stopped: a corrupted input line, the background-work dialog, or the
       session moved to the background (the session is still running)
   * - ``4``
     - the process did not exit within ``--wait`` seconds

Afterwards
----------

Add the printed ``[parked.NAME]`` or ``[retired.NAME]`` entry to ``fleet.toml``
(:doc:`../configuration`). From then on :doc:`fleetrestore` will not relaunch that
transcript and :doc:`fleetspawn` refuses the name except ``--resume`` with the
recorded uuid. Run :doc:`fleetsnap`: the layout changed.

A parked session comes back with ``fleetspawn NAME DIR --beside PANE
--resume UUID --go``; then delete its ``[parked]`` entry.
