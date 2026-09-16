fleetregister
=============

.. tooldoc:: fleetregister

Usage
-----

.. code-block:: bash

   # at arm time, from the session that starts the watcher:
   fleetregister <session> <jobid> <watcher-pid> ["note"]

   # when the job has ended and its result has been read:
   fleetregister --clear <session> <jobid>

From a watcher that runs as a ``systemd-run --user`` unit, call it by absolute path
(``$HOME/bin/fleetregister``, or wherever ``install`` linked it). A unit gets the
user manager's ``PATH``, which after a reboot is only the system directories, so a
bare ``fleetregister`` there fails with "command not found", even if the same unit
worked before the reboot.

A registration is ``<state>/watchers/<session>-<jobid>-<pid>.json``:

.. code-block:: json

   {"session": "...", "job": "...", "pid": 12345, "starttime": "...",
    "armed": "<ISO time>", "note": "..."}

``starttime`` is field 22 of ``/proc/<pid>/stat``. The pair (pid, start time) is
the identity :doc:`fleetwatch` checks; a registration without a start time is read
as dead.

Registering a pid that is not running fails. ``--clear`` refuses while the
registered process is still alive (same pid and start time, not a zombie), and fails
if nothing is registered for that session and job.
