fleetsnap
=========

.. tooldoc:: fleetsnap

Run it with no arguments while the fleet is healthy, and **before** anything that
risks tmux: the pane-to-transcript mapping exists only in live process arguments.

What it records, per session
----------------------------

- tmux position (session, window, pane index and id, size), the ``@repo`` label and
  ``@fleet`` group
- working directory, claude version, pid and start time
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
  restored) or its name with another transcript

Plus, fleet-wide: exact tmux window layouts, the installed claude version,
``~/.tmux.conf`` presence, systemd user units (flagging transient ones, which die at
reboot), and the ``[authority]`` table from configuration.

Pane labels
-----------

The ``@repo`` label is hand-set and can go stale on a rename. When the pane title
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

Files written
-------------

In the state directory:

``manifest.json``
   everything above, machine-readable
``manifest.md``
   human-readable, for rebuilding by hand when nothing is running
``<fleet>.json``
   one manifest per ``@fleet`` group, used by ``fleetrestore <fleet>``
``index.md``
   the fleets and their members

``manifest.json`` and ``manifest.md`` are copied to ``.bak-<stamp>`` before each
write; the newest 10 are kept.

See the :doc:`fleet-snapshot skill <../skills/fleet-snapshot>` for verifying a
snapshot — a count of captured sessions is not a validation.
