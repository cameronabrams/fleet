fleetrestore
============

.. tooldoc:: fleetrestore

Usage
-----

.. code-block:: text

   fleetrestore                  list the fleets in the state directory
   fleetrestore <fleet>          plan one fleet (tiled layout)
   fleetrestore --all            plan everything, with each window's exact layout
   ... --go                      build it
   ... --brief                   write RECOVERY.md into each session's directory (with --go)
   ... --stagger SECONDS         pause between launches (default 3)

**Run it without** ``--go`` **first and read the plan.** A stale manifest rebuilds a
fleet that no longer exists, and the rebuilt sessions look right.

Behavior
--------

- Sessions whose ``@repo`` label is already on a live pane are skipped.
- Unverified resume handles are listed before the plan.
- Windows are created in manifest order, the real window index is read back from
  tmux, and panes are addressed using tmux's ``pane-base-index`` — both assumptions
  once sent every session one pane too high.
- Each window is named and ``automatic-rename`` turned off, so the next snapshot
  records the real name. A recorded name of ``claude`` is warned about, not applied.
- Each pane gets ``@repo`` and ``@fleet`` and is sent
  ``[spawn].env claude --name <label> --resume <uuid>``.

It does not restart compute. Local jobs died with the machine; whether to rerun them
is a judgement, not a recovery step.

``--all`` is the power-cycle path. A partial restore of a fleet whose sessions span
several windows names each of those windows after the fleet.

After a restore, verify the fleet — per pane, argv against cwd against the manifest
— not just the snapshot (:doc:`../skills/fleet-snapshot`).
