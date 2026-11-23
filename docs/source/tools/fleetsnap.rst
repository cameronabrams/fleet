fleetsnap
=========

.. tooldoc:: fleetsnap

Run it with no arguments while the fleet is healthy, and **before** anything that
risks tmux: the pane-to-transcript mapping exists only in live process arguments.

What it records, per session
----------------------------

- tmux position (session, window, pane index and id, size) and the ``@agent``
  label
- working directory, claude version, pid and start time
- ``kind`` — what the session's own brief declares on its ``Kind:`` line
  (``repo``, ``production``, ``coordinator``, …), or null where the brief does not
  say. The brief is the only place a session's role is written down, so it is the
  only thing a tool can read it from
- ``resume_uuid`` and ``resume_uuid_source`` — how the handle was resolved. A
  handle reading ``verified:`` came from process arguments (corrected for a
  ``/clear`` since launch), from a descendant running in the session's scratchpad,
  or from the transcript's own name record. Anything else is ``corroborated:`` or
  ``UNVERIFIED:`` and must be checked before a restore relies on it.
- durable files to re-read after a restart: the session's brief, then
  ``CLAUDE.md``, ``ROADMAP.md``, ``CHECKPOINT.md``, ``SESSION-RESTART-STATE.md`` if
  present in its directory
- declared and live color, and any **membership problems**: no brief, no
  ``[colors]`` entry, a live color that differs from the declared one, or a
  ``[parked]``/``[retired]`` entry that lists its transcript (it would not be
  restored) or its name with another transcript. ``known`` is false when the live
  color cannot be read — no transcript resolved, or a pane running
  ``claude attach <id>`` (a background session, whose ``/color`` is not recorded
  anywhere a tool can read) — and then no color mismatch is raised

Plus, fleet-wide: exact tmux window layouts, the installed claude version,
``~/.tmux.conf`` presence, systemd user units (flagging transient ones, which die at
reboot), the ``[authority]`` table from configuration, and ``coordinator``.

Who the coordinator is
----------------------

``coordinator`` is the label of the one session whose brief declares
``Kind: coordinator``, and it is null when none does or when several do.
``fleetrestore`` prints it at the top of a restore; ``index.md`` names it.

Null rather than a pick, because the two absences need opposite repairs — write
the line into a brief, or take it out of all but one — and a tool that chose the
first of several would answer in pane order and hide the mistake. Both are said
out loud: the index says which absence it is, and a run with more than one
claimant prints the names.

**It used to be read off the session's name.** The lookup asked for
``kind == "coordinator"`` before any session record carried a ``kind``, so it
never matched, and a fallback behind it took whichever session was literally
called ``coord``. That agreed with the brief for as long as nobody renamed
anything, and would have handed the role to whatever took the old name on the day
somebody did — a check on what a session is *called* standing in for a check on
what it *is*. Worse, the key it fed stopped being written on 2026-10-01 with the
removal of the per-fleet sub-manifests, so ``fleetrestore`` printed
``coordinator: ?`` on every run for six weeks. The ``?`` was correct — absence is
rendered ``?``, never as a pass — and correct is exactly why nobody looked. Both
halves fixed 2026-11-12; see ``docs/checks-that-reassure.md``.

Pane labels
-----------

The ``@agent`` label is hand-set and can go stale on a rename. When the pane title
differs, fleetsnap takes the title as the session's name **only** on positive
evidence — the process was launched ``--name <title>``, or a transcript in its
project self-reports that name — and notes the correction. A shell's
``user@host:path`` title, or a bare hostname while a session sits at the trust
prompt, never renames a session.

Window names
------------

Where tmux's ``automatic-rename`` is on for a window that holds a session, the name
tmux reports is the running command, not a name. If the previous manifest holds a
real name for that window, fleetsnap keeps it and says so in
``window_name_notes``.

Furniture: the panes in a fleet window that are not sessions
------------------------------------------------------------

A window can hold panes that no agent lives in — a ``fleetboard --watch``, a
shell the human keeps beside his agents. They carry neither ``@agent`` nor
``@fleet``, so they are not sessions and never appear in ``sessions``: a session
has a brief, a declared color, a re-arm ledger and a restore obligation, and
handing those to a shell would make every membership count wrong.

They are recorded anyway, beside the window's layout, because of what their
absence does to the geometry::

   "window_layouts": {
     "0:1": {
       "name": "deps",
       "layout": "...",
       "furniture": [
         {"pane_index": 1, "pane_id": "%22", "cwd": "/home/u",
          "start_command": "/home/u/bin/fleetboard --watch"}
       ]
     }
   }

**A layout string describes every pane the window had, and**
``tmux select-layout`` **given one that describes more panes than the window
holds exits 0, prints nothing, and leaves the default split.** Measured
2026-11-23 on a throwaway server: a 4-pane layout applied to a 2-pane window.
So a window of two agents and two pieces of furniture came back at the default
split on every restore, however it had been hand-sized, and nothing in the
snapshot, the plan, the run or the report said so. The record is what lets
:doc:`fleetrestore` rebuild the pane count, and therefore the sizes.

``start_command`` is ``#{pane_start_command}`` — the command the pane was
created with, and **empty for a plain shell**, which is recorded as an empty
string rather than guessed at. ``#{pane_current_command}`` is not the fallback:
it reads ``python3`` for a running board, which is not a command anything can
relaunch. It is the last field of the pane row and is joined rather than
indexed, because it is the one column that can contain a tab of its own.

Only windows that hold at least one fleet session are considered, the same
scoping the window-name guard uses. A scratch window is unlabeled by design, and
recording every pane in one is how a record gets trained into noise. An
unlabeled pane anywhere else is still reported as somebody else's, which is what
``list-panes -a`` crossing tmux sessions shows.

A pane carrying ``@agent`` but no ``@fleet`` is **not** furniture. That is the
ours-but-stamped-by-an-older-tool case, and it needs a human rather than a pane
rebuilt from a recorded command.

The snapshot says out loud that a restore will run these commands, because that
is the one thing ``fleetrestore`` does that is not launching ``claude`` from a
versioned path.

Files written
-------------

In the state directory:

``manifest.json``
   everything above, machine-readable
``manifest.md``
   human-readable, for rebuilding by hand when nothing is running. Its opening
   snippet names **the tmux session this capture came from**, and says how to
   attach to it. That was a literal ``0`` until 2026-11-13, which was right only
   for as long as nobody renamed the session — a reader following a stale snippet
   would have built a second session beside the real one and found it empty. A
   capture spanning two tmux sessions writes ``<session>`` rather than picking.
``index.md``
   the sessions and where they sit

There is one fleet, so there is one manifest. ``<fleet>.json`` files, one per
``@fleet`` group, were written until 2026-10-01, and any left on disk were moved
aside as ``<name>.json.stale`` by the snapshots that followed.

``manifest.json`` and ``manifest.md`` are copied to ``.bak-<stamp>`` before each
write; the newest 10 are kept.

.. note::

   **The state directory is shared, and ``fleetsnap`` touches only its own files
   there.** The cleanup that cleared the ``<fleet>.json`` residue did not: it
   matched ``<state>/*.json`` and moved aside everything not named after a live
   fleet, which is the whole namespace rather than the manifests it named. On
   2026-10-03 it renamed another tool's cache, and that tool rendered the missing
   values as *unknown* — correct behavior, and therefore no alarm. A value that
   used to be there is a different event from one that never arrived, and only the
   second is what ``unknown`` is designed to report.

   The cleanup was removed rather than narrowed, because nothing writes
   ``<fleet>.json`` any more and a migration that cannot have work left is only a
   blast radius. A tool that needs its own files in the state directory should own
   a subdirectory, as the watcher registry does with ``watchers/``.

See the :doc:`fleet-snapshot skill <../skills/fleet-snapshot>` for verifying a
snapshot — a count of captured sessions is not a validation.
