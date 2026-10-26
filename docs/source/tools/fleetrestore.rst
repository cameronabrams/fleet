fleetrestore
============

.. tooldoc:: fleetrestore

Usage
-----

.. code-block:: text

   fleetrestore                  plan the whole fleet, with each window's exact layout
   fleetrestore NAME...          plan only these sessions (tiled layout)
   ... --go                      build it
   ... --brief                   write a recovery brief per session
   ... --stagger SECONDS         pause between launches (default 3)

**Run it without** ``--go`` **first and read the plan.** A stale manifest rebuilds a
fleet that no longer exists, and the rebuilt sessions look right.

Behavior
--------

- Sessions whose resume uuid is listed in ``[parked]`` or ``[retired]`` are not
  relaunched, whatever manifest is read. A later session that reuses the name has a
  different uuid and restores normally.
- Sessions whose ``@agent`` label is already on a live pane **of this fleet**
  are skipped. Another fleet's session sharing a name with one of ours would
  otherwise read as ours being up, and this list exists to *suppress* work, so a
  false entry suppresses in silence.
- Unverified resume handles are listed before the plan.
- Windows are created in manifest order and the real window index is read back
  from tmux. Panes are addressed by the ``%N`` pane id tmux reports as each one is
  made — **not** by a computed ``<window>.<index + pane-base-index>``. Reading that
  setting was itself the 2026-09-30 failure: it was queried before the first
  ``new-session``, so on a machine with no server yet running it returned nothing
  and fell back to ``0`` while the config sets ``1``, and every session went one
  pane to the left. A pane id cannot be off by one, and survives renumbering.
- A pane tmux does not report an id for is never typed into, and before each
  launch the pane's directory is checked against the manifest.
- A manifest window whose name is **already open** is joined, not duplicated: the
  group's panes are split into the existing window and its name and layout are left
  alone. This is the ordinary case, because liveness filtering turns "one session
  died" into a partial restore while that session's window is still on screen
  holding its neighbors. If *two* windows already carry the name the restore stops
  for that group and names both, rather than placing a session beside the wrong
  neighbors. Windows named ``claude`` are never matched — ``automatic-rename``
  writes that over any window whose real name was lost, so it identifies nothing.
- Each window this tool creates is named and ``automatic-rename`` turned off, so the
  next snapshot records the real name. A recorded name of ``claude`` is warned
  about, not applied.
- Each pane gets ``@agent`` **and** ``@fleet`` and is sent
  ``[spawn].env claude --name <label> --resume <uuid>``.
- A name that the manifest does not hold is refused, rather than restoring the
  rest: a typo would otherwise read as a successful partial restore.

It does not restart compute. Local jobs died with the machine; whether to rerun them
is a judgement, not a recovery step.

The bare command is the power-cycle path. Each window's recorded layout is applied
only when every session in the manifest is being rebuilt — a named subset, or a run
where some sessions are already live, is tiled instead, because an exact layout
needs every pane that was in the window.

After a restore, verify the fleet — per pane, argv against cwd against the manifest
— not just the snapshot (:doc:`../skills/fleet-snapshot`).

A restore is the fleet's largest adoption
-----------------------------------------

Every session comes up on whatever ``claude`` resolves to now, which need not be
what the manifest recorded. That is the same hole as an unpark (see
:doc:`fleetspawn`) with a bigger blast radius — the whole fleet at once — so
``--go`` writes to the same ``<state>/autoroll.log``.

It writes **two** lines, and the first one is honest about being a guess::

   ...  rolled=15-sessions from=2.1.299 to=2.1.301 note=restore INTENT -- 15 planned, none verified yet
   ...  rolled=15-sessions from=restore to=2.1.301 note=restore DONE -- 15 of 15 panes match the manifest (pane label and directory; not a version check)

The first is written **before anything launches**, so it records intent: a restore
that half-fails will have claimed every session, and one that dies partway will
have claimed them all with none up. Before is still the right place, because a
line written after a run that never finishes does not exist — and the unfinished
restore is exactly the one worth having a record of. The second line completes it
when there is an outcome to report.

The outcome deliberately does **not** say a version was adopted. ``verify``
compares each pane's ``@agent`` label and directory against the manifest, counting
only panes of this fleet — a foreign pane with the right name in the right place
would otherwise report a session as restored that was never restored at all,
which is the one nobody looks at again. The comparison is
a different question from which binary came up, and a line claiming the stronger
fact would be the same overstatement one step along. When tmux cannot be listed at
all, ``verify`` returns a single row — counting that as one failed session would
log *14 of 15 matched* for a check that matched nothing, so it reads ``COULD NOT
CHECK`` instead.

``to=`` is **the release that was launched**, not the newest installed one. Those
are different every day under a pinned launch, and logging the wrong one put a
version into the fleet's only durable adoption record that never ran here
(2026-10-19: both lines said ``to=2.1.303`` while all 16 sessions came up on
``2.1.302``). When the pin falls back, ``to=`` is what bare ``claude`` gives,
because in that branch that is genuinely what the sessions come up on.

**Nothing is read per session and the launch loop is untouched.** Both lines use
``versions.installed(ask_binary=False)``, the form that will not run
``claude --version``: this is the recovery path, where nothing may need anything
else to work first. An unreadable version is written ``?``.
