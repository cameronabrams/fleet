fleetregister
=============

.. tooldoc:: fleetregister

Usage
-----

.. code-block:: bash

   # at arm time, from the session that starts the watcher:
   fleetregister <session> <jobid> <watcher-pid> ["note"]

   # when the work is a local process rather than a cluster job:
   fleetregister --local <session> <name> <pid> ["note"]

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

``--local`` adds ``"work": "local"`` before ``armed``.

``starttime`` is field 22 of ``/proc/<pid>/stat``. The pair (pid, start time) is
the identity :doc:`fleetwatch` checks; a registration without a start time is read
as dead.

Registering a pid that is not running fails. ``--clear`` refuses while the
registered process is still alive (same pid and start time, not a zombie), and fails
if nothing is registered for that session and job. ``--local`` changes none of
that.

Local work
----------

``--local`` says the registered pid **is** the work — a local process, not a
poller of a job running on the cluster. :doc:`fleetwatch` then answers "is this
still live" from ``/proc`` alone and never asks the scheduler about a name it
cannot know.

Without it, every registration read as cluster work, so a watch on a local
process was tested against ``squeue``, found absent (as it must be), and reported
as a monitor whose job had died — while the process was running normally. See
:doc:`fleetwatch` for what each kind is reported as.

**A field rather than a naming convention.** A job called ``crawl`` is not
evidence of anything, and this registry's whole premise is that a watcher
*declares* itself instead of being inferred from text. For the same reason a
registration made *without* the flag declares nothing at all, rather than
defaulting to ``"work": "cluster"``: the one mistake this flag exists for is
local work registered without it, and a default would turn that into a claim that
the work is on the cluster. Undeclared is checked against ``job_id_re`` and, if
it cannot be an id of this cluster, reported as something nothing can speak for.
