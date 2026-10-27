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

Exit codes
----------

.. list-table::
   :widths: 8 92

   * - ``0``
     - registered, or everything cleared
   * - ``1``
     - **nothing happened, and that is a fact about the registry**: no
       registration matched the clear, or the pid being registered is not running
   * - ``2``
     - **the call could not run at all**: a usage error, or a state directory that
       could not be resolved from ``fleet.toml``
   * - ``3``
     - a partial clear — something was skipped because its watcher is still live

``1`` and ``2`` are kept apart on purpose. The arity used to be taken with
``${2:?session}``, which writes its complaint to **stderr** and exits ``1`` — and
``1`` is "no registration matched". A watcher whose exit path read

.. code-block:: bash

   fleetregister --clear "$SESSION" 2>/dev/null     # the arity is <session> <jobid>

discarded the only evidence and got back the code meaning "there was nothing to
clear". Of the two readings available to the caller, the comfortable one was
indistinguishable from the true one, and the registration it failed to remove
surfaced much later as a report about a watcher nobody could account for, with
nothing connecting it back. Reported 2026-10-27 by the session that had written
that line. Too *many* arguments is refused for the same reason: ``--clear`` used
to ignore a trailing note copied from the register call.

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
