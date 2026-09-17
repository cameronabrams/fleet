fleetnudge
==========

.. tooldoc:: fleetnudge

Usage
-----

.. code-block:: text

   fleetnudge SESSION JOB "TEXT" [--go] [--wait SECONDS] [--every SECONDS]

A detached watcher (a ``setsid`` loop or a ``systemd-run --user`` unit) cannot wake the
session that armed it, and a Claude Code Monitor that could expires after 30 minutes.
``fleetnudge`` closes that gap: the watcher calls it on a terminal state, and the session
receives one line in its own pane. The watcher recipe is in the
:doc:`fleet-upgrade skill <../skills/fleet-upgrade>`.

What it types
-------------

.. code-block:: text

   [watcher: SESSION job JOB] TEXT

The tag is added by the tool and cannot be left out. The brief template tells each
session that such a line only reports that a job ended. It is never the human's
instruction or approval: the session checks the job and reports, and takes no other
action on the line's authority. ``TEXT`` is one line of printable characters, at most
200 of them.

Refused (exit 2)
----------------

- a name with no ``[colors]`` entry, or one that is ``[parked]`` or ``[retired]``
- a session whose brief says ``Kind: coordinator``
- a ``JOB`` that no watcher registered for ``SESSION`` (:doc:`fleetregister`)
- a background session (``claude attach``), or more than one session with the name
- the session running the tool, judged by process ancestry. A ``setsid``'d watcher
  inherits its session's ``CLAUDE_CODE_SESSION_ID`` but is not inside it, so that
  variable is deliberately not used.
- a transcript that cannot be verified, since delivery could not be confirmed
- a bad job id, or empty, long or multi-line ``TEXT``

With ``--go``
-------------

Each attempt resolves the session afresh from ``claude agents --json`` and ``/proc``.
It types only when the pane is idle, shows no dialog and has an empty input line; a
``busy`` or ``waiting`` status also counts as not typeable. ``shell`` and ``monitor``
mean the session is at its prompt, so they are typeable. The typed line must read back
exactly before Enter, as in :doc:`fleetcontext`. Delivery is confirmed when the tag
appears once more in the session's transcript.

While the session is busy, holds a draft, or is not running, it retries every
``--every`` seconds (default 60) for up to ``--wait`` seconds (default 1800). It never
queues a line behind a draft.

When the line is not delivered, for any reason including a refusal, it sends the
``[notify]`` push (see :doc:`../configuration`) unless the mute file exists, and exits
non-zero. Every attempt and outcome is appended to ``<state>/nudges.log`` as one JSON
line.

Under a systemd unit
--------------------

Call it by absolute path (``$HOME/bin/fleetnudge``). A unit's ``PATH`` holds only the
system directories, so the tool puts ``~/.local/bin`` (where ``claude`` lives) in front
of its own ``PATH``. ``tmux`` is expected in the system directories.

Exit codes
----------

.. list-table::
   :widths: 10 90

   * - ``0``
     - delivered and seen in the transcript, or a plan with no blocks
   * - ``2``
     - refused
   * - ``3``
     - the typed line did not read back; the input line was cleared
   * - ``4``
     - not delivered in time: not typeable for the whole wait, or typed but never seen
       in the transcript
