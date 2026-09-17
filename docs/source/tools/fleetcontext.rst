fleetcontext
============

.. tooldoc:: fleetcontext

Usage
-----

.. code-block:: text

   fleetcontext [--json]
   fleetcontext --compact NAME [--go] [--saved] [--wait SECONDS]
   fleetcontext --color NAME [--go]

Context trimming is on demand only. Nothing here runs by itself: the report
recommends and the human chooses. The
:doc:`fleet-upgrade skill <../skills/fleet-upgrade>` runs the report as one step
of a roll, and only suggests trimming.

What it measures
----------------

A session's context is the last main-thread turn's ``input + cache_read +
cache_creation`` tokens in its own transcript. That is what the model was sent on
that turn. A compaction writes a ``system`` record with subtype
``compact_boundary`` into the same file. Until the next turn, the boundary's
``postTokens`` is the size.

Sessions are named and identified from ``claude agents --json``. A process that
list does not include is resolved from its transcript, as in
:doc:`fleetsnap`. A pane running ``claude attach <id>`` is not a session of its
own. It shows a background session, which is reported ``manual``.

``SINCE`` is the time since the last compaction, or since the transcript began.
``ACTIVE`` is the time since the transcript was last written. ``RUNTIME`` counts
child processes and live registered watchers (:doc:`fleetregister`).

Save first
----------

A session over ``compact_above`` is marked ``save-first`` when any of these hold:

- it holds runtime
- its brief says ``Kind: production`` or ``Kind: service``
- its working directory has uncommitted paths

Otherwise it is marked ``skip``. For a ``save-first`` session, ask it to write down
what it would not want summarized, and wait for it to confirm. Then pass
``--saved``. ``--compact`` refuses without it. ``--saved`` is also how the human
waives the step for one session.

Preflight
---------

``--compact`` and ``--color`` block, and type nothing, on any of:

- no live session with the name, or more than one
- the session running the tool
- a background session
- no tmux pane
- the folder-trust prompt, the background-work dialog, or a turn in progress
- text already in the input line. A dim prompt suggestion is not text: panes are
  captured with attributes (``capture-pane -p -e``), and dim (SGR 2) characters are ignored.
- no input line on screen

``--compact`` also blocks on:

- a session whose brief says ``Kind: coordinator``. The human types its
  ``/compact``.
- an unverified transcript. The compaction could not be confirmed.
- ``save-first`` without ``--saved``

``--color`` also blocks on a name with no ``[colors]`` entry, and does nothing if
the session already has its declared color.

With ``--go``
-------------

It types the command without Enter. It then reads the input line back from the
whole screen and presses Enter only if the line holds exactly that command. A
wrapped line is joined. On a mismatch it clears the line and exits 3. After Enter:

- ``--compact`` waits (``--wait``, default 600 s) for a new ``compact_boundary``
  record, then prints its ``preTokens -> postTokens``.
- ``--color`` waits for an ``agent-color`` record with the declared color.

Clearing a session
------------------

There is no ``--clear``. A ``clear?`` row is a candidate only: its size is over
``clear_above``, its kind is ``repo`` or ``writing``, its tree is clean and it holds
no runtime. Whether everything it needs is on disk is a judgement about that one
session. If the human chooses to clear it:

1. the session writes its state down and says so
2. the human types ``/clear`` in its pane
3. ``fleetcontext --color NAME --go``, since a clear drops the color
4. :doc:`fleetsnap`, since the transcript id changed
5. the session re-reads its brief

Exit codes
----------

.. list-table::
   :widths: 10 90

   * - ``0``
     - done, or a plan with no blocks
   * - ``2``
     - blocked by preflight
   * - ``3``
     - stopped: the input line did not read back, or the session exited
   * - ``4``
     - timed out waiting for the compaction boundary or the color record
