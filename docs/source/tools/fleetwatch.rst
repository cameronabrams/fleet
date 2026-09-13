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
