fleet
=====

.. |docs| image:: https://readthedocs.org/projects/fleet/badge/?version=latest
   :target: https://fleet.readthedocs.io/en/latest/
   :alt: Documentation status

|docs|

**fleet** is a set of tools and skills for running a *fleet* of long-lived
`Claude Code <https://claude.com/claude-code>`_ sessions: each session owns one
repository, compute campaign or shared resource, and a coordinator session routes
between them.

A session in a pane looks like typing ``claude`` in a terminal. Keeping a dozen of
them useful for weeks is not: each needs a role it can re-read after a restart, a
place in a recovery snapshot, a name nothing else answers to, and watchers that
survive — or are known not to survive — an upgrade. fleet supplies the mechanical
parts of that and records the judgement parts as skills.

What it gives you:

- **Recovery.** :doc:`tools/fleetsnap` records which pane resumes which transcript
  while the fleet is healthy; :doc:`tools/fleetrestore` rebuilds tmux, labels and
  sessions after a power cycle.
- **Safe upgrades.** :doc:`tools/fleetupgrade` finds sessions on a stale binary and
  who would lose runtime state on restart.
- **Watched cluster work.** :doc:`tools/fleetwatch` derives which scheduler jobs
  have a live watcher, from the scheduler and ``/proc`` rather than from notes.
- **Onboarding.** :doc:`tools/fleetspawn` brings one new session in — pane, labels,
  launch, verification — and never answers the folder-trust prompt.
- **Visibility.** :doc:`tools/fleetlog`, :doc:`tools/fleetcost` and
  :doc:`tools/fleetwaiting` reconstruct who talks to whom, what it costs, and who is
  blocked on the human.

Design rules that run through all of it:

- **Derive, don't record.** Anything observable at runtime is computed from the live
  system. Hand-kept copies of observed state rot, and nothing announces that they
  have.
- **Stdlib only.** The tools are the recovery path after a disk loss; a recovery tool
  that needs a package installed first fails exactly when it is needed.
- **Read-only by default.** Anything that changes tmux or launches a session prints a
  plan unless given ``--go``.
- **Authority stays with the human.** No session, the coordinator included, holds it.

New here? Read :doc:`concepts`, then :doc:`installation`, then the
:doc:`fleet-bootstrap skill <skills/fleet-bootstrap>`.

Contents
--------

.. toctree::
   :maxdepth: 2

   concepts
   installation
   configuration
   tools/index
   skills/index
   templates
   checks-that-reassure
   testing
   API <api/API>
