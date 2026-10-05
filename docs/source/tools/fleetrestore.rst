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
- Sessions whose ``@agent`` label is already on a live pane are skipped.
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
- Each window is named and ``automatic-rename`` turned off, so the next snapshot
  records the real name. A recorded name of ``claude`` is warned about, not applied.
- Each pane gets ``@agent`` and is sent
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
