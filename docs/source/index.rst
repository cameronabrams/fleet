fleet
=====

.. |docs| image:: https://readthedocs.org/projects/fleet-of-agents/badge/?version=latest
   :target: https://fleet-of-agents.readthedocs.io/en/latest/
   :alt: Documentation status

.. |license| image:: https://img.shields.io/github/license/cameronabrams/fleet
   :target: https://github.com/cameronabrams/fleet/blob/main/LICENSE
   :alt: MIT licensed

.. |python| image:: https://img.shields.io/badge/python-3.11%2B-blue
   :target: installation.html#requirements
   :alt: Requires Python 3.11 or newer, for the stdlib tomllib

.. |deps| image:: https://img.shields.io/badge/dependencies-none-brightgreen
   :target: installation.html#requirements
   :alt: No Python packages beyond the standard library

.. |platform| image:: https://img.shields.io/badge/platform-linux-lightgrey
   :target: installation.html#requirements
   :alt: Linux only: the tools read /proc

.. rst-class:: badges

|docs| |license| |python| |deps| |platform|

.. image:: _static/img/fleet.png
   :alt: A robot orchestra: a conductor on a podium, its players at their stands
   :class: only-light banner
   :width: 100%

.. image:: _static/img/fleet-dark.png
   :alt: A robot orchestra: a conductor on a podium, its players at their stands
   :class: only-dark banner
   :width: 100%

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
- **Onboarding and spin-down.** :doc:`tools/fleetspawn` brings one new session in —
  pane, labels, launch, verification — and never answers the folder-trust prompt;
  :doc:`tools/fleetretire` parks or retires one, recording how to resume it first.
- **Context trimming.** :doc:`tools/fleetcontext` measures what each session
  carries and recommends; it compacts one session at a time, on the human's word,
  and confirms the compaction in the transcript.
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

New here? Read :doc:`concepts`, then :doc:`installation`, then
:doc:`first-fleet` — which takes you from an empty configuration to a fleet you can
leave running, and on to mail with someone else's.

Contents
--------

.. toctree::
   :maxdepth: 2

   concepts
   installation
   first-fleet
   configuration
   tools/index
   skills/index
   templates
   checks-that-reassure
   testing
   API <api/API>
