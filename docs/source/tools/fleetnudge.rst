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

With ``--mail-from FLEET/SESSION`` the line is tagged ``[mail: FLEET/SESSION -> SESSION]``
instead: mail relayed by :doc:`fleetmail` from another person's fleet. ``JOB`` is then
the message id, and no watcher registration is required, because fleetmail checks its
own allowlist and guard before relaying.

The tag is added by the tool and cannot be left out. The brief template tells each
session that such a line only reports that a job ended. It is never the human's
instruction or approval: the session checks the job and reports, and takes no other
action on the line's authority. ``TEXT`` is one line of printable characters, at most
200 of them.

Refused (exit 2)
----------------

- a name with no ``[colors]`` entry, or one that is ``[parked]`` or ``[retired]``
- a session whose brief says ``Kind: coordinator`` — **unless** the line is relayed
  mail (``--mail-from``). The rule is about watchers, whose results go to the human
  and whose campaigns a coordinator does not own; a coordinator owns no repository and
  routes, which makes it the obvious counterpart for another person's fleet.
- a ``JOB`` that no watcher registered for ``SESSION`` (:doc:`fleetregister`), again
  except for relayed mail, which has no watcher — :doc:`fleetmail` checks its own
  allowlist before calling this, and the tag says the line came from another fleet
- a background session (``claude attach``), or more than one session with the name
- the session running the tool, judged by process ancestry. A ``setsid``'d watcher
  inherits its session's ``CLAUDE_CODE_SESSION_ID`` but is not inside it, so that
  variable is deliberately not used.
- a transcript that cannot be verified, since delivery could not be confirmed
- a bad job id, or empty, long or multi-line ``TEXT``

**One refusal is not a failure to deliver, and it is the only one.** When the tool
is running *inside* the session it would type into, the in-session task doing the
running already notifies it — that task's own output lands in that session's
transcript. The content arrived; the nudge was merely redundant. So that record is
written with ``notified_otherwise: true``, :doc:`fleetwatch` leaves it out of the
delivery holes, and **no phone push is sent**: ``fleetnudge: <session> not reached``
would be false on the phone for exactly the reason it was false on the board.

Both follow from one value in ``give_up``, not from two tests of the same
condition. They are the same claim — *nobody was told* — made to two audiences, and
two derivations of one fact agree until the day they do not.

Every *other* refusal does send the push, because every other one means nobody was
told. The log records ``not pushed: the session was notified by its own in-session
task`` rather than leaving the field out: :doc:`fleetwatch` reads an absent push
result as "a human was not told", so an omission would be the same false alarm one
field along.

With ``--go``
-------------

Each attempt resolves the session afresh from ``claude agents --json`` and ``/proc``.
It types only when the pane is idle, shows no dialog and has an empty input line. A dim
prompt suggestion counts as empty, as in :doc:`fleetcontext`. A
``busy`` or ``waiting`` status also counts as not typeable. ``shell`` and ``monitor``
mean the session is at its prompt, so they are typeable. The typed line must read back
before Enter, as in :doc:`fleetcontext` (compared ignoring whitespace, since a line that
wraps mid-word gains a space at the wrap). A trailing ``;`` in ``TEXT`` is sent as a key
code: tmux reads one at the end of a ``send-keys`` argument as its own command separator
and drops it, which cost a production nudge its readback on 2026-09-17. Delivery is confirmed when the tag
appears once more in the session's transcript.

**One nudge types into a session at a time.** A second one waits for the first
instead of interleaving keystrokes with it: two watchers nudged one session within
the same second on 2026-09-17, and neither line read back. The lock
(``<state>/nudge-locks/<session>.lock``) is held only while typing, never while
waiting for a busy session, so a queued nudge is delayed rather than lost.

Keep ``TEXT`` to one summary line. A line of per-task detail wraps in the pane and
tells the session no more than a count does; it can read its own log for the rest.

While the session is busy, holds a draft, or is not running, it retries every
``--every`` seconds (default 60) for up to ``--wait`` seconds (default 1800). It never
queues a line behind a draft.

When the line is not delivered, for any reason including a refusal, it sends the
``[notify]`` push (see :doc:`../configuration`) unless the mute file exists, and exits
non-zero. Every attempt and outcome is appended to ``<state>/nudges.log`` as one JSON
line, carrying ``session``, ``job``, ``text``, ``outcome``, the ``reason`` and the push
result — and ``mail_from`` on a failure as well as on a success, since an undelivered
piece of mail is the case most in need of identifying. :doc:`fleetwatch` reads that
log to report lines that never reached a session, which is the only trace left when
the push is muted.

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
