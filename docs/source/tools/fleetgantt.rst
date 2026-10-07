fleetgantt
==========

.. tooldoc:: fleetgantt

The page
--------

A standalone HTML file with no network access and no libraries, in light and dark
themes. One lane per role, grouped by fleet group; one track per transcript from its
first record to its last; overlapping transcripts of one role are stacked.

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - mark
     - means
   * - solid ticks on a track
     - 15-minute stretches in which the transcript wrote any timestamped record
   * - filled square at the start
     - launched fresh
   * - ring at the start
     - started by ``/clear`` (a ``/clear`` among its first three user records)
   * - diamond
     - context compacted (records within 10 minutes count once)
   * - short vertical bar
     - renamed (its ``agent-name`` changed)
   * - dashed, faded track
     - placement is an inference: a renamed-away name, or no name and placed by
       directory
   * - amber rule / slate rule
     - declared event / derived event; a shaded day for a date without a time
   * - triangles on the top row
     - a claude version reaching a second role

Hovering a track shows its span, active time, messages sent and received,
compactions, first and last claude version, renames, how it was attributed, and its
working directory.

Identity
--------

One row per **transcript uuid**: a uuid is a session, so a transcript found under
two project directories is drawn once. That happens when a working directory is
renamed — Claude Code opens a project directory for the new path and the old one
keeps its copy — and the surviving row is the one under a directory a role owns.
Before 2026-10-07, ``--all`` drew three such sessions twice.

Roles are the sessions in the last :doc:`fleetsnap` manifest plus ``[parked]`` and
``[retired]`` entries (:doc:`../configuration`). Each transcript is assigned by
``fleet.identity``, the rules :doc:`fleetlog` also uses:

1. its own last name record, if that is a role;
2. if that name was later changed to a role's in another transcript, that role
   (inferred);
3. if it recorded no name, the role whose working directory it ran in — unless
   several roles share that directory, when it is not placed (inferred);
4. otherwise, when it ran in some role's directory, the **unattached** lane under its
   recorded name; when it ran in no role's directory, it is counted in the page's
   notes and not drawn (``--all`` draws it).

A transcript that recorded a name which is not a role — a remote session's title, a
one-off — is not placed by directory: it has said who it is.

Rule 2 needs **this** transcript to have recorded both names. A rename known only
from another transcript places nothing here, because a lane states an identity and
that evidence cannot tell a real rename from two sessions that shared a name
(2026-09-22). :doc:`fleetlog` keeps such a mapping, labelled *from another
transcript*, because a message graph has no lane to mislabel.

So the unattached lane holds transcripts this chart **declined to place**, which
is not the same as transcripts that never held a role: a session's earlier name
lands here whenever no single transcript records the change. The lane is headed
*NOT PLACED IN A LANE* for that reason — it previously read *NOT A ROLE*, which
was false about six transcripts that had held two of them (reported 2026-10-07).

A parked or retired role keeps its lane in the right group, and its unnamed
transcripts in place, only if its entry has ``group`` and ``cwd``;
:doc:`fleetretire` prints both.

Events
------

**Declared** events come from ``<config>/events.toml``:

.. code-block:: toml

   [[event]]
   date   = "2026-09-09"
   time   = "10:01"            # optional, in the display zone
   label  = "Reboot and restore"
   detail = "fleetrestore rebuilds the fleet"

**Derived** events are park and retire dates from ``fleet.toml``, and each claude
version at the moment a second role ran it. ``--no-derived`` omits them.

Time zone
---------

``[human] timezone_file`` (read on every run, for a human who travels), else
``[human] timezone``, else UTC. The page states which zone and where it came from.

Output
------

``<state>/gantt/fleet-gantt-YYYYMMDD-HHMM.html`` and a copy at
``<state>/gantt/latest.html``, unless ``--out`` is given. ``--json`` prints the lane
data instead and writes nothing.
