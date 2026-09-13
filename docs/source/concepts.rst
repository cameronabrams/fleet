.. _concepts:

Concepts
========

Sessions, kinds and the coordinator
-----------------------------------

A **session** is one long-lived Claude Code process, launched ``claude --name
<name>`` in its own tmux pane and pinned to one working directory. Its **brief** —
a short file in configuration — says what it is for, what it may write, and who it
works with. The session re-reads it after every restart; a role reconstructed from
a transcript is an inference.

Every session has a **kind**:

.. list-table::
   :header-rows: 1
   :widths: 15 85

   * - kind
     - does
   * - repo
     - edits code in one repository; does not run production campaigns
   * - production
     - runs studies, sweeps or cluster jobs with released code, and reports bugs to
       the owning repo session instead of patching code itself
   * - service
     - owns a shared resource the fleet relies on — a database, a website, a record
       of results — answers and records for the fleet, and may maintain the tool
       behind it
   * - writing
     - manuscripts, talks, documentation
   * - coordinator
     - owns no directory or campaign; routes, measures, rolls upgrades, keeps
       snapshots and conventions

The split between *repo* and *production* is deliberate: production runs surface
bugs that tests do not, and a session that both runs and patches quietly patches
around them. The :doc:`fleet-bootstrap skill <skills/fleet-bootstrap>` covers role
design in full.

Sessions talk through Claude Code's cross-session messages. Because a message is
re-read on every later turn of its receiver, the conventions favor a *pointer* — a
file path plus a one-line conclusion — over a payload (:doc:`templates`).

Three layers, kept apart on purpose
-----------------------------------

.. list-table::
   :header-rows: 1

   * - layer
     - where
     - contents
     - versioned
   * - **application**
     - this repository
     - ``bin/`` tools, the ``fleet`` package, ``skills/``, ``docs/``
     - here, shareable
   * - **configuration**
     - ``~/.config/fleet/`` (or ``$FLEET_CONFIG``)
     - ``fleet.toml``, briefs, conventions, site skills
     - privately
   * - **state**
     - ``[paths].state``, default ``~/.local/state/fleet/``
     - manifests, watcher registrations, re-arm ledgers
     - never

Configuration is what a human **declares**: hosts, accounts, which working
directory belongs to which session, each member's color. State is what the tools
**observe**. Keeping them apart is not tidiness — a record of observed state kept
by hand is the specific thing that rots.

What a restart keeps, and what it does not
------------------------------------------

``claude --resume <uuid>`` restores a session's whole transcript. It does **not**
restore Monitors, background jobs or cross-session subscriptions, and the resumed
transcript still shows the session creating them, with no seam. A session cannot
tell from inside that its runtime is gone.

fleet answers that from two sides:

- a **re-arm ledger** per session (``<state>/rearm/<name>.md``), written *before* a
  restart, holding the recipe to re-arm each watcher and why it matters;
- **watcher registration** (:doc:`tools/fleetregister`), so the *inventory* of live
  watchers is derived from processes that can be checked, not claimed in prose.

A session that should stop is **parked** (its role continues later) or **retired**
(its role is finished) with :doc:`tools/fleetretire`, which records how to resume
it before stopping it; ``fleet.toml`` then keeps restores from relaunching it.

The resume handle itself moves: a ``/clear`` rolls a session onto a new transcript
while its process arguments still name the old one. :doc:`tools/fleetsnap` and
:doc:`tools/fleetupgrade` detect that and resolve the live transcript.

Identity
--------

A name is not an identity; a transcript is. Names are reused and renamed, pane
labels go stale, pane titles outlive whoever set them. The tools resolve which
transcript a session writes to from, in order of strength:

1. ``--resume <uuid>`` in the live process arguments, corrected for a ``/clear``
   since launch;
2. a descendant process running from the session's own scratchpad path, which
   carries its session id;
3. the transcript's own ``agent-name`` records (the last one wins, since
   ``/rename`` writes mid-file).

Whatever the tools report, ``ListAgents`` inside a session is the authority on the
names sessions answer to.
