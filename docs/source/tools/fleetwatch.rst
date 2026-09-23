fleetwatch
==========

.. tooldoc:: fleetwatch

Needs a ``[cluster.<name>]`` section and non-interactive ssh to it
(:doc:`../configuration`).

How it decides
--------------

**Live work** comes from one ssh round trip: ``squeue`` rows per array parent
(tasks, states, pending reasons) and each job's working directory from ``sacct``.
The remote command ends with a marker line; without it the query counts as
**failed**, never as "no work" — an ssh banner and an empty queue otherwise look
the same.

**Owner** is the first ``[owners]`` fragment found in the working directory, else
``UNATTRIBUTED``.

**Held** work — pending only for a reason in ``held_reasons`` — needs no watcher: it
cannot produce anything to observe. The moment the reason changes, it needs one.

**Watched** means a registration in ``<state>/watchers/`` whose process is alive:
same pid *and* same start time, and not a zombie (see :doc:`fleetregister`).
Command lines are only advisory — a child of a session counts as a *possible*
watcher only if it names the job id *and* shows a poll loop (``sleep <n>``), and the
tool's own process tree is excluded.

Report sections
---------------

``LIVE WORK WITH NO WATCHER``
   live, not held, no live registration
``WATCHER ON WORK THAT IS NO LONGER LIVE``
   a live registration for a job not in the queue
``looks like a watcher but is NOT REGISTERED``
   advisory inference, with the ``fleetregister`` command to fix it
``REGISTERED WATCHER IS DEAD``
   the registered process is gone while its job is still live, or ``sacct`` cannot
   show that the job ended
``finished``
   the registered process is gone and ``sacct`` shows only terminal states — the
   normal end of a watcher; clear it with ``fleetregister --clear``
``WorkDir not in [owners]``
   add a row to configuration
``held``
   nothing to watch

``fleetwatch <session>`` limits the report to work that session owns or watches.

Who can see the fleet
---------------------

Attaching to the tmux server hands a person every pane: sessions already past the
folder-trust prompt, weeks of context, and peers that treat a line from one of them
as a teammate's request. So the report ends by naming every attached client, where
it came from (from ``who``), and how long it has been idle.

``MORE THAN ONE CLIENT IS ATTACHED``
   normal is one. A second is not proof of anything — a second terminal of your own
   looks identical — but it is the one thing worth seeing without being asked.
``COULD NOT LIST TMUX CLIENTS``
   a failed query and an unattached server both produce no rows, and only one of
   them means what an empty list looks like.

**This reports; it does not guard, and a lock here would be close to theatre.**
Whoever can attach can equally read the Claude credentials, the ``gh`` token and the
ssh key — they sit in the same account and need no tmux — so authenticating this one
door defends nothing that is not already open. The boundary is the account, not the
fleet. What a second client genuinely changes is that the panes are *already*
trusted and *already* full of context, so the useful control is noticing, and then
tmux's own ``lock-after-time`` with a ``lock-command`` that actually exists on the
machine. Check that one by hand: a lock whose command is missing fails toward
unlocked.

Times are shown in the zone from ``[human]`` (:doc:`../configuration`) and labelled,
because an unlabelled time in the wrong zone reads as right.

Did the result reach the session?
---------------------------------

Watching is half the question. A watcher can run perfectly and its *result* still
never arrive: :doc:`fleetnudge` types the line into the session's pane, and when it
cannot, it falls back to the ``[notify]`` phone push — which ``mute_file``, when the
file exists, silences by design. Nobody is then told by any channel, and
``<state>/nudges.log`` is the only trace, while the job above reads as **watched**.
That is the reassuring direction, so the log is read here.

``NUDGE NEVER ARRIVED AND NO PUSH WENT OUT``
   the session was not told and neither was the phone. A record whose push result
   is anything but a 2xx counts here, and so does one with no push result at all:
   unknown is read as *not told*.
``not delivered, but the phone push did go out``
   a human was told out of band; the session still never got the line.
``FLEETNUDGE STOPPED MID-RETRY``
   the log ends on ``waiting`` for that session and job. ``fleetnudge`` always exits
   through an outcome, so it was killed before it could deliver, give up or push,
   and nothing else recorded the attempt. Only counted once the entry is older than
   two hours — a retry loop still running looks exactly the same.

Undelivered mail is covered by the same rows: :doc:`fleetmail` delivers through
``fleetnudge``, and the sender travels with the failure as well as the success.
Mail that never *became* a nudge — quarantined, or written to a drop and never
handed over — cannot appear in that log, so it is **counted** here with a pointer to
``fleetmail status``, which owns those rows. An empty section must not be readable
as "everything got through".

A hole is listed even when a later nudge to the same session and job did land: that
later line is named beside it, to be checked, because a different message about the
same job is not this message. The window is the last seven days; anything older is
counted, never dropped in silence. A **missing** log means no nudge was ever sent —
``fleetnudge`` creates it on first use — but an unreadable one, or a line that will
not parse, is reported as itself. "No rows" must never be something the check
produced by failing.
