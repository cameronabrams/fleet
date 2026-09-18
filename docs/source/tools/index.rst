.. _tools:

Tools
=====

Every tool is a single stdlib-only script in ``bin/``, linked into ``~/bin`` by
``install``. Each page shows the tool's own header text first — it is read from the
script at build time, so it cannot drift from the code.

.. list-table::
   :header-rows: 1
   :widths: 22 58 20

   * - tool
     - does
     - changes
   * - :doc:`fleetsnap`
     - snapshot enough to rebuild the fleet
     - writes state
   * - :doc:`fleetrestore`
     - rebuild the fleet from the last snapshot
     - tmux, with ``--go``
   * - :doc:`fleetupgrade`
     - which sessions run a stale binary; ordered restart plan
     - nothing
   * - :doc:`fleetspawn`
     - bring one new session in, or a parked one back
     - tmux, with ``--go``
   * - :doc:`fleetretire`
     - park or retire one session
     - tmux and state, with ``--go``
   * - :doc:`fleetwatch`
     - which cluster work has a live watcher
     - nothing
   * - :doc:`fleetregister`
     - a watcher registers itself at arm time
     - writes state
   * - :doc:`fleetwaiting`
     - which sessions appear blocked on the human
     - nothing
   * - :doc:`fleetlog`
     - reconstruct the cross-session message graph
     - nothing
   * - :doc:`fleetcost`
     - what inter-session messages cost in re-read tokens
     - nothing
   * - :doc:`fleetgantt`
     - every session's life as a Gantt chart
     - writes a page
   * - :doc:`fleetcontext`
     - context size per session; compact one, or reset its color
     - tmux, with ``--go``
   * - :doc:`fleetnudge`
     - a detached watcher wakes its idle session with one tagged line
     - tmux, with ``--go``
   * - :doc:`fleetmail`
     - messages between fleets owned by different people, through a git mailbox
     - the mailbox and tmux, with ``--go``

Most tools read ``~/.claude/projects/`` (transcripts), ``/proc`` and
``tmux list-panes``. All take their configuration from :doc:`../configuration`.

.. toctree::
   :maxdepth: 1
   :hidden:

   fleetsnap
   fleetrestore
   fleetupgrade
   fleetspawn
   fleetretire
   fleetwatch
   fleetregister
   fleetwaiting
   fleetlog
   fleetcost
   fleetgantt
   fleetcontext
   fleetnudge
   fleetmail
