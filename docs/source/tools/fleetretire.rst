fleetretire
===========

.. tooldoc:: fleetretire

Usage
-----

.. code-block:: text

   fleetretire NAME --park|--retire [--go] [--allow-dirty] [--allow-references]
               [--note TEXT] [--wait SECONDS]

**Park** when the role continues later; **retire** when it is finished. The
:doc:`fleet-bootstrap skill <../skills/fleet-bootstrap>` (section 4) covers the
decision and the steps around the tool.

Preflight
---------

Blocks, and changes nothing, on any of:

- no claude process launched ``--name NAME``, or more than one
- a resume uuid that is not ``verified:`` (resolved as :doc:`fleetsnap` does)
- the session's transcript already listed in ``[parked]`` or ``[retired]``
- the pane busy (``esc to interrupt`` in its footer), at the folder-trust prompt,
  or at the background-work dialog
- child processes of the claude process
- a live registered watcher for the session (:doc:`fleetregister`)
- cluster work the session owns or watches, or a failed cluster query
  (:doc:`fleetwatch`); skipped, with a note, when no cluster is configured
- uncommitted or unpushed work in its git working directory, unless
  ``--allow-dirty`` — or reported only, when another session shares the directory
- **retire only:** other briefs naming the session as a whole word, unless
  ``--allow-references``
- the session being the one running the tool

With ``--go``
-------------

1. Writes the resume recipe — ``cd <dir> && [spawn].env claude --name NAME
   --resume <uuid>``, and the ``fleetspawn --resume`` form — to
   ``<state>/rearm/NAME.md`` (park) or ``<state>/rearm/retired/NAME.md`` (retire),
   keeping the previous ledger's content below it. It confirms the file holds the
   uuid **before** anything is stopped.
2. Types ``/exit`` into the pane without Enter, checks that the input line reads
   exactly ``/exit`` (a terminal reply can corrupt keys; if it does not, the line is
   cleared and nothing is sent), then sends Enter.
3. Waits for the process to exit — same pid and start time gone.
4. Closes the pane, unless it is the only pane in its window.
5. Prints the ``fleet.toml`` entry for the configuration owner.

Exit codes
----------

.. list-table::
   :widths: 10 90

   * - ``0``
     - done, or a plan with no blocks
   * - ``2``
     - blocked by preflight
   * - ``3``
     - stopped at an unexpected screen: a corrupted input line, or the
       background-work dialog (the session is still running)
   * - ``4``
     - the process did not exit within ``--wait`` seconds

Afterwards
----------

Add the printed ``[parked.NAME]`` or ``[retired.NAME]`` entry to ``fleet.toml``
(:doc:`../configuration`). From then on :doc:`fleetrestore` will not relaunch that
transcript and :doc:`fleetspawn` refuses the name except ``--resume`` with the
recorded uuid. Run :doc:`fleetsnap`: the layout changed.

A parked session comes back with ``fleetspawn NAME DIR --fleet GROUP --beside PANE
--resume UUID --go``; then delete its ``[parked]`` entry.
