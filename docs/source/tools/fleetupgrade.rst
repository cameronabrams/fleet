fleetupgrade
============

.. tooldoc:: fleetupgrade

Usage
-----

.. code-block:: text

   fleetupgrade           table + ordered plan
   fleetupgrade --json    the same, machine-readable
   fleetupgrade --eligible          who could be rolled right now, and why not
   fleetupgrade --eligible --json   the same, machine-readable
     --soak H   hours the installed binary must have been present (default 24)
     --lag N    releases behind before a roll is worth doing (default 2)

Columns
-------

``SESSION``
   the session's own last ``agent-name`` record, else the pane title
``VERSION`` / ``STALE``
   the binary the process runs, against the ``claude`` a new session would launch
   — ``shutil.which`` first, then the native ``~/.local/bin/claude``. Both install
   layouts are read: the native one names the version in the path, the npm one
   only in the ``package.json`` beside the binary. A binary replaced in place
   under a running session reads ``?``, because the package then describes the
   new binary and not the one that session is still running.
``LEDGER``
   whether ``<state>/rearm/<name>.md`` exists — existence only, not truth
``COLOR``
   the live color; ``LOST`` when a transcript was read and has none, ``?`` when no
   transcript could be resolved or the session is a background one (a ``/color``
   typed through ``claude attach`` is not recorded anywhere a tool can read)
``RESUME UUID``
   the transcript ``--resume`` should reopen

Warnings follow for colors that differ from ``[colors]`` (never for an unknown
color), pane titles that disagree
with the session's name record, handles that could not be resolved (another claude
outside tmux shares the directory — the tool refuses to guess), and names taken only
from a pane title.

The plan lists stale sessions with their relaunch commands, coordinator last. The
session running the tool cannot restart itself, so it gets a separate block with the
two commands to type — ``/exit``, then ``cd <dir> && [env] claude --name <name>
--resume <uuid>``, using the session id from its own environment.

A pane running ``claude attach <id>`` — a session ``/exit`` moved to the background,
reattached — is resolved through ``claude agents --json``, flagged as a background
session and left out of the plan. Background sessions that no pane shows are listed
too.

It restarts nothing. The :doc:`fleet-upgrade skill <../skills/fleet-upgrade>` drives
a roll.

``--eligible``: a computation, not a plan
-----------------------------------------

Answers one question per session — *would a restart be safe to start right now* —
and hands the answer to whoever is driving. It is the machine half of a roll that
nobody has to trigger; the other half, acting on it, stays with the
:doc:`fleet-upgrade skill <../skills/fleet-upgrade>`.

**Every gate is a refusal, and a gate that cannot be evaluated refuses.** An
unreadable ``claude agents``, a failed cluster query, an unreadable install time:
each is reported as a reason not to roll, never as clearance. That direction
matters more here than anywhere else in this repository. A board that fails toward
reassurance shows a wrong color; a roll that fails toward reassurance restarts a
session that was holding something.

A refusal is **not a failure**. Staying stale is a correct outcome of a skip, and
the report says so.

The gates, in the order they are reported:

.. list-table::
   :widths: 22 78
   :header-rows: 1

   * - gate
     - refuses when
   * - hold
     - ``<config>/no-roll`` exists (see below)
   * - self
     - the session's uuid is the asking session's — it cannot roll itself
   * - soak
     - the installed binary has been present for less than ``--soak`` hours
   * - lag
     - fewer than ``--lag`` releases behind, or already current
   * - background
     - ``/exit`` moved it to the background; resuming its old uuid would fork it
   * - handle
     - its resume uuid is unresolved or missing — never restart one on a guess
   * - idle
     - ``claude agents`` says busy, does not list it, or could not be read
   * - children
     - it has an exit-blocking child; **skipped, never killed**
   * - runtime
     - it holds live cluster work with no re-arm ledger, or the cluster is unknown

The last three of those are not in the spec this was built from. Each is something
the table above already warns a *human* about — and an unattended driver gets no
warnings.

**Counting releases.** Lag is a patch distance within one ``major.minor``; across a
minor or major it is reported as uncountable, which satisfies any lag. Uncountable
means *behind by more than this can count*, not *not behind*: reading it as zero
would hold back exactly the roll most worth making. The releases between two patch
numbers are not all installed locally — 2.1.297 and .298 never were here — so the
distance is a version distance, not an adoption count.

**Why a tool and not a script.** A restart needs to ask a session what it has
running that its ledger does not name, which needs ``SendMessage`` and therefore an
agent. Everything up to that question is computable, testable and belongs here;
the question itself, and the acting, do not. That is the whole of the split, and
it is why this prints a report and runs nothing but ``fleetwatch --json``.

The hold file
-------------

``<config>/no-roll`` is a standing refusal, written once, in place of a decision
taken again at every roll:

* **present and empty** — all rolling is held;
* **one version per line** (``#`` comments allowed) — those versions are refused as
  targets, which is "I do not trust 2.1.300" said once;
* **present but unreadable** — holds. It was put there to stop something, and a
  read error is not permission to proceed.
