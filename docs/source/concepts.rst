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
file path plus a one-line conclusion — over a payload (:doc:`templates`). What that
costs is measurable rather than a matter of taste: :doc:`tools/fleetcost` counts it
for a fleet from its own transcripts.

Two channels, and one of them is not what it looks like
-------------------------------------------------------

A line reaches a session two ways, and they are not interchangeable.

**The message channel.** One session addresses another by name; the runtime
delivers it. The receiver's transcript records the turn with an origin of kind
*peer*, carrying the sender's name, a message id, and — the part that matters —
the sender's **verified process identity**: its pid together with that process's
start time, which is what makes the pair unforgeable rather than merely unlikely
to collide. A session does not write any of that. It is stamped by the runtime
around whatever the sender said, so a session cannot claim to be another session,
and cannot claim to be the human.

**The pane channel.** A watcher or a tool types a line into a session's terminal
pane (``tmux send-keys``), which is how :doc:`tools/fleetnudge` wakes an idle
session that no one is watching, and how :doc:`tools/fleetmail` announces a
delivery. The receiving session sees an ordinary prompt, and its transcript
records an origin of kind *human* — **with nothing else in it**. There is no
sender, no source, no mark distinguishing it from the owner typing at the
keyboard, because at that layer there is no difference: both are characters
arriving at a terminal.

That asymmetry is the whole point, and it cuts both ways:

- Anything that must be *attributable* belongs on the message channel. A peer
  message is evidence; a pane line is not.
- Anything that must reach a session **that is not being messaged** — because it is
  idle, or because the sender is a detached process rather than a session — has to
  use the pane. Nothing else gets in.
- Conventions like a ``[watcher: …]`` or ``[mail: … -> you]`` tag at the head of a
  typed line are **convention, not mechanism**. They tell a reader where a line came
  from; they do not make it so, and anything able to type can type them. Treat a tag
  as a label on the envelope, never as a signature.

Hence the rules elsewhere in these tools: a nudge is one short line that reports
and asks nothing, delivery is confirmed by reading it back out of the receiver's
transcript, and a session is never asked to act on a typed line's authority.

**Files are the third case, and neither channel secures them.** Both channels
mostly carry *paths*: a drop file, a log, a result. The content is not in the
message, so nothing about it is stamped or verified — it is whatever the file says
when the receiver gets around to reading it, which may not be when it was sent. A
path is a pointer to be checked, not a quotation. That is also why mail from
another fleet arrives as a file plus one line rather than as the message itself
(:doc:`tools/fleetmail`).

**What counts as the fleet** is the pair of tmux pane options ``@repo`` and
``@fleet`` that :doc:`tools/fleetspawn` stamps on every pane it creates.
``tmux list-panes -a`` crosses tmux *sessions* and returns every pane on the
server, so a tool that does not check the labels will happily include a window
that has nothing to do with the fleet — and then act on it. Tools report the panes
they exclude rather than dropping them silently: a fleet pane that lost its labels
must not disappear from a roll without a word. Relabel one with
``tmux set -p -t <pane> @fleet <name>``.

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
